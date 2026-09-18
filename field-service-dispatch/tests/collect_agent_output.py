#!/usr/bin/env python3
"""
Stage 1 (UNTRUSTED). Runs as the unprivileged `runner` user, under a
wall-clock timeout enforced by test.sh (`timeout` wraps this whole script).

The candidate's decide() runs in a genuinely separate OS process (see
candidate_worker.py for exactly why: same-process execution let a
submitted policy use ordinary introspection to read the real simulator's
hidden internal state, including jobs that hadn't "arrived" yet). This
script drives the real simulator (sim.run_simulation) itself, in THIS
process, and for every decision point serializes only the documented
SimState fields to the worker process, waits for its answer, and feeds
that back to the simulator -- so the worker never has more information
than a fair policy is supposed to have, structurally, not by convention.

A fresh worker process is spawned per sealed held-out scenario (there are
two, with deliberately different structure -- technician-pool size, skill
scarcity, arrival cadence -- so a policy tuned to only one shape can't
coast on the other): the instruction invites the candidate to keep
internal bookkeeping across decide() calls, and reusing one process
across both shifts would let shift-1 state leak into shift-2's grading
run. Records the RAW decision trace (list of (tech_id, job_id) pairs
decide() returned at each call) per scenario to /work/trace.json. Makes
no pass/fail judgment and does not trust its own computed cost for
grading purposes -- Stage 2 independently replays each trace through the
trusted simulator from scratch. This script never reads anything under
tests/sealed/reference (sealed 700/600 before this runs).

The raw scenario files under tests/sealed/inputs/ are NOT pre-sealed by
test.sh, because this script (running as the unprivileged `runner` user)
genuinely needs to read them once to drive the real simulator. But the
candidate's own worker process runs under that exact same UID -- process
isolation stops it from reading this process's live memory, but does
nothing about the filesystem, so without further action the candidate
could simply open() the same files directly and read every future
arrival, a much simpler shortcut than the introspection attack process
isolation was built to close. So every scenario is read and then
immediately chmod 000'd (see _seal_scenario_dir) BEFORE any candidate
code, including the very first worker process, is ever spawned -- by the
time any candidate code runs, the data no longer exists on disk for
`runner` (or anyone but root) to read, regardless of how it asks. Stage 2
still reads these same files later, as root, which bypasses permission
bits entirely.
"""
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
    import csv

    def read_csv(name):
        with open(os.path.join(data_dir, name), newline="") as f:
            return list(csv.DictReader(f))

    techs = [
        sim.TechnicianSpec(
            tech_id=r["tech_id"], skills=frozenset(r["skills"].split(";")),
            shift_end=int(r["shift_end"]), max_overtime=int(r["max_overtime"]),
        )
        for r in read_csv("technicians.csv")
    ]
    jobs = [
        sim.JobSpec(
            job_id=r["job_id"], required_skill=r["required_skill"], base_duration=int(r["base_duration"]),
            priority=r["priority"], deadline=int(r["deadline"]), arrival_time=int(r["arrival_time"]),
        )
        for r in read_csv("jobs.csv")
    ]
    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)
    return techs, jobs, cfg["shift_length"]


def _seal_scenario_dir(data_dir):
    """Locks the raw scenario files (and the directory itself) to mode 000
    the moment this (trusted, in-this-process) read of them is done and
    BEFORE any candidate code -- including the isolated worker process --
    has run at all. The candidate's own worker runs under this same
    `runner` UID (that is what process isolation actually buys: no shared
    MEMORY with the simulator, not a different UID), so a chmod on file
    permissions alone can't tell "this script's read" apart from "the
    candidate's read" by who is asking -- only by whether the data still
    exists to be read at all by the time anyone else asks. chmod 000
    blocks every non-root reader, including this very process and the
    worker it is about to spawn, while leaving Stage 2 (root) unaffected,
    since root bypasses permission bits entirely. The alternative
    (deleting the files) was rejected: Stage 2 runs later in the same
    container and needs to read this same data to recompute ground truth
    for replay, so it must still exist on disk, just inaccessible to
    anyone without root."""
    try:
        for entry in os.listdir(data_dir):
            os.chmod(os.path.join(data_dir, entry), 0o000)
        os.chmod(data_dir, 0o000)
    except OSError:
        pass


def _state_to_payload(state):
    return json.dumps({
        "current_time": state.current_time,
        "free_technicians": [
            {
                "tech_id": t.tech_id, "skills": sorted(t.skills), "continuous_work": t.continuous_work,
                "shift_end": t.shift_end, "overtime_used": t.overtime_used, "max_overtime": t.max_overtime,
            }
            for t in state.free_technicians
        ],
        "pending_jobs": [
            {
                "job_id": j.job_id, "required_skill": j.required_skill, "duration": j.duration,
                "priority": j.priority, "deadline": j.deadline, "arrival_time": j.arrival_time,
                "is_followup": j.is_followup,
            }
            for j in state.pending_jobs
        ],
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
            return [tuple(pair) for pair in msg["assignments"]]

        try:
            techs, jobs, shift_length = loaded[name]
            result = sim.run_simulation(techs, jobs, shift_length, proxy_decide)
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
