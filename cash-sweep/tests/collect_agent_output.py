#!/usr/bin/env python3
"""
Stage 1 (UNTRUSTED). Runs as the unprivileged `runner` user, under a
wall-clock timeout enforced by test.sh (`timeout` wraps this whole
script).

The candidate's decide() runs in a genuinely separate OS process (see
candidate_worker.py for exactly why -- the companion field-service-
dispatch bundle's cheat/frame_introspection/ documents the real exploit
this defends against). This script drives the real simulator
(sim.run_simulation) itself, in THIS process, and for every decision
point serializes only the documented SimState fields to the worker
process, waits for its answer, and feeds that back to the simulator --
so the worker never has more information than a fair policy is supposed
to have, structurally, not by convention.

A fresh worker process is spawned per sealed held-out scenario (there
are two, with deliberately different structure -- currency count, gadget
density, whether a mid-day credit lands -- so a policy tuned to only one
shape can't coast on the other): the instruction invites the candidate
to keep internal bookkeeping across decide() calls, and reusing one
process across both scenarios would let one scenario's state leak into
the other's grading run. Records the RAW decision trace (list of
(from_currency, to_currency, amount) triples decide() returned at each
call) per scenario to /work/trace.json. Makes no pass/fail judgment and
does not trust its own computed cost for grading purposes -- Stage 2
independently replays each trace through the trusted simulator from
scratch. This script never reads anything under tests/sealed/reference
(sealed 700/600 before this runs).

The raw scenario files under tests/sealed/inputs/ are NOT pre-sealed by
test.sh, because this script (running as the unprivileged `runner` user)
genuinely needs to read them once to drive the real simulator. But the
candidate's own worker process runs under that exact same UID -- process
isolation stops it from reading this process's live memory, but does
nothing about the filesystem, so without further action the candidate
could simply open() the same files directly and read every future
obligation, a much simpler shortcut than any introspection attack
process isolation was built to close. This is a lesson learned the hard
way on the field-service-dispatch bundle (see its cheat/sealed_input_
read/ for the full writeup), applied here from the start rather than
retrofitted: every scenario is read and then immediately chmod 000'd
(see _seal_scenario_dir) BEFORE any candidate code, including the very
first worker process, is ever spawned -- by the time any candidate code
runs, the data no longer exists on disk for `runner` (or anyone but
root) to read, regardless of how it asks. Stage 2 still reads these same
files later, as root, which bypasses permission bits entirely. For that
same reason -- chmod only takes effect for a file's owner (or root) --
test.sh chown's tests/sealed/inputs to `runner` before this script ever
runs, so this script's own chmod 000 call on files it does not create
still has the standing to succeed.

The rate/cutoff schedule itself is NOT read by the candidate from disk
at all, sealed or otherwise: it is baked into every SimState payload sent
over the queue (see environment/sim/simulator.py's SimState docstring),
so there is no separate "market data file" for a same-UID process to
reach for in the first place. Sealing tests/sealed/inputs/ still matters
because that is where the OBLIGATION schedule (arrival/due times) lives,
which -- like a field-service-dispatch job's arrival -- must stay hidden
until the simulator's own event loop reveals it.
"""
import csv
import json
import multiprocessing
import os
import queue
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import simulator as sim

ARTIFACT_PATH = "/app/outputs/policy.py"
SIM_PATH = os.path.join(os.path.dirname(__file__), "simulator.py")
WORKER_PATH = os.path.join(os.path.dirname(__file__), "candidate_worker.py")
SEALED_SCENARIO_DIRS = {
    "held_out_1": "/tests/sealed/inputs/held_out_1",
    "held_out_2": "/tests/sealed/inputs/held_out_2",
}
OUT_PATH = "/work/trace.json"
CALL_TIMEOUT_SEC = 90
READY_TIMEOUT_SEC = 60


def load_scenario(data_dir):
    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)

    spread_cheap, spread_expensive, cutoff_time = {}, {}, {}
    with open(os.path.join(data_dir, "rates.csv"), newline="") as f:
        for r in csv.DictReader(f):
            pair = (r["from_currency"], r["to_currency"])
            spread_cheap[pair] = float(r["cheap_rate"])
            spread_expensive[pair] = float(r["expensive_rate"])
            cutoff_time[pair] = int(r["cutoff_time"])

    obligations = []
    with open(os.path.join(data_dir, "obligations.csv"), newline="") as f:
        for r in csv.DictReader(f):
            obligations.append(sim.ObligationSpec(
                r["obligation_id"], r["currency"], float(r["amount"]),
                due_time=int(r["due_time"]), arrival_time=int(r["arrival_time"]),
            ))

    credits = []
    with open(os.path.join(data_dir, "credits.csv"), newline="") as f:
        for r in csv.DictReader(f):
            credits.append(sim.CreditSpec(r["credit_id"], r["currency"], float(r["amount"]), arrival_time=int(r["arrival_time"])))

    return cfg["currencies"], spread_cheap, spread_expensive, cutoff_time, cfg["starting_balances"], credits, obligations, cfg["horizon"]


def _seal_scenario_dir(data_dir):
    """Locks the raw scenario files (and the directory itself) to mode 000
    the moment this (trusted, in-this-process) read of them is done and
    BEFORE any candidate code -- including the isolated worker process --
    has run at all. See the module docstring for the full reasoning; in
    short, chmod 000 blocks every non-root reader, including this very
    process and the worker it is about to spawn, while leaving Stage 2
    (root) unaffected, since root bypasses permission bits entirely."""
    try:
        for entry in os.listdir(data_dir):
            os.chmod(os.path.join(data_dir, entry), 0o000)
        os.chmod(data_dir, 0o000)
    except OSError:
        pass


def _state_to_payload(state):
    return json.dumps({
        "current_time": state.current_time,
        "balances": [list(b) for b in state.balances],
        "pending_obligations": [
            {
                "obligation_id": o.obligation_id, "currency": o.currency, "amount": o.amount,
                "due_time": o.due_time, "arrival_time": o.arrival_time,
            }
            for o in state.pending_obligations
        ],
        "currencies": list(state.currencies),
        "spread_cheap": [list(r) for r in state.spread_cheap],
        "spread_expensive": [list(r) for r in state.spread_expensive],
        "cutoff_time": [list(r) for r in state.cutoff_time],
    })


class WorkerFailure(Exception):
    pass


_POLL_INTERVAL_SEC = 0.5


def _get_with_liveness_check(out_q, proc, timeout_sec):
    """Like out_q.get(timeout=...), but polls in short increments and
    bails out as soon as the worker process has died instead of always
    waiting the full timeout -- a candidate that kills its own process
    (os._exit, a fatal signal, etc.) should fail fast, not burn the
    entire per-call budget for no reason."""
    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            return out_q.get(timeout=_POLL_INTERVAL_SEC)
        except queue.Empty:
            if not proc.is_alive():
                raise WorkerFailure("candidate process exited without responding") from None
            if time.monotonic() >= deadline:
                raise
            continue


def _spawn_worker(ctx):
    in_q = ctx.Queue()
    out_q = ctx.Queue()
    proc = ctx.Process(target=_worker_entrypoint, args=(ARTIFACT_PATH, SIM_PATH, WORKER_PATH, in_q, out_q), daemon=True)
    proc.start()
    try:
        msg = json.loads(_get_with_liveness_check(out_q, proc, READY_TIMEOUT_SEC))
    except queue.Empty:
        _kill(proc)
        raise WorkerFailure("candidate process did not respond (timed out loading policy.py)")
    if "error" in msg:
        _kill(proc)
        raise WorkerFailure(msg["error"])
    return proc, in_q, out_q


def _worker_entrypoint(artifact_path, sim_path, worker_path, in_q, out_q):
    import importlib.util
    spec = importlib.util.spec_from_file_location("candidate_worker_mod", worker_path)
    candidate_worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate_worker)
    candidate_worker.run_worker(artifact_path, sim_path, in_q, out_q)


def _kill(proc):
    try:
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5)
    except Exception:  # noqa: BLE001
        pass


def main():
    out = {"status": "ok", "traces": {}, "error": None}

    if not os.path.exists(ARTIFACT_PATH):
        out["status"] = "missing"
        _write(out)
        return

    # Load every scenario's raw data AND seal every scenario directory
    # BEFORE spawning any candidate code at all -- including before the
    # first worker process for even the first scenario. This way no
    # candidate process, however it is scheduled, is ever running while
    # any scenario's files are still readable by a non-root user.
    loaded = {}
    for name, data_dir in SEALED_SCENARIO_DIRS.items():
        loaded[name] = load_scenario(data_dir)
    for data_dir in SEALED_SCENARIO_DIRS.values():
        _seal_scenario_dir(data_dir)

    ctx = multiprocessing.get_context("spawn")

    for name in SEALED_SCENARIO_DIRS:
        proc = in_q = out_q = None
        try:
            proc, in_q, out_q = _spawn_worker(ctx)  # raises WorkerFailure => "malformed"
        except WorkerFailure as e:
            out["status"] = "malformed" if out["status"] == "ok" else out["status"]
            out["error"] = f"{name}: {e}"
            out["traces"][name] = None
            continue

        def proxy_decide(state, in_q=in_q, out_q=out_q, proc=proc):
            in_q.put(_state_to_payload(state))
            try:
                msg = json.loads(_get_with_liveness_check(out_q, proc, CALL_TIMEOUT_SEC))
            except queue.Empty:
                raise RuntimeError("candidate process stopped responding") from None
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return [tuple(triple) for triple in msg["transfers"]]

        try:
            currencies, spread_cheap, spread_expensive, cutoff_time, starting_balances, credits, obligations, horizon = loaded[name]
            result = sim.run_simulation(
                currencies, spread_cheap, spread_expensive, cutoff_time,
                starting_balances, credits, obligations, horizon, proxy_decide,
            )
            out["traces"][name] = result.decision_trace
        except Exception as e:  # noqa: BLE001 - a runtime failure once loaded is "crashed", not "malformed"
            out["status"] = "crashed"
            out["error"] = f"{name}: {e}"
            out["traces"][name] = None
            # keep going -- still attempt the remaining scenario(s) so a
            # crash specific to one doesn't hide a result for the other
        finally:
            if proc is not None:
                _kill(proc)

    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f)
    print(f"collected -> {OUT_PATH}: status={out['status']} scenarios={list(out['traces'].keys())}")


if __name__ == "__main__":
    main()
