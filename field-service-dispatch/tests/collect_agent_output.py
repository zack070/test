#!/usr/bin/env python3
"""
Stage 1 (UNTRUSTED). Runs as the unprivileged `runner` user, under a
wall-clock timeout enforced by test.sh (`timeout` wraps this whole script).

Imports the candidate's submitted policy module FRESH for each sealed
held-out scenario (there are two, with deliberately different structure --
technician-pool size, skill scarcity, arrival cadence -- so a policy tuned
to only one shape can't coast on the other) and runs it via the real
simulator. A fresh module instance per scenario matters because the
instruction explicitly invites the candidate to keep internal bookkeeping
across decide() calls -- reusing one imported module across both shifts
would let shift-1 module-level state silently leak into shift-2's grading
run, an accidental failure mode with nothing to do with the task's actual
difficulty. Records the RAW decision trace (list of (tech_id, job_id)
pairs the candidate's decide() returned at each call) per scenario to
/work/trace.json. Makes no pass/fail judgment and does not trust its own
computed cost for grading purposes -- Stage 2 independently replays each
trace through the trusted simulator from scratch. This script never reads
anything under tests/sealed/reference (sealed 700/600 before this runs)
and the scenario input data it does read is not the answer to anything --
only the traces it produces matter downstream.
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import simulator as sim

ARTIFACT_PATH = "/app/outputs/policy.py"
SEALED_SCENARIO_DIRS = {
    "held_out_1": "/tests/sealed/inputs/held_out_1",
    "held_out_2": "/tests/sealed/inputs/held_out_2",
}
OUT_PATH = "/work/trace.json"


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


def _load_fresh_policy():
    """Executes the candidate's module into a brand-new namespace (never
    registered in sys.modules), so no global/module-level state can survive
    from a previous load. Returns the callable decide(state)."""
    spec = importlib.util.spec_from_file_location("candidate_policy", ARTIFACT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    decide = getattr(mod, "decide", None)
    if decide is None or not callable(decide):
        raise AttributeError("policy.py does not define a callable decide(state)")
    return decide


def main():
    out = {"status": "ok", "traces": {}, "error": None}

    if not os.path.exists(ARTIFACT_PATH):
        out["status"] = "missing"
        _write(out)
        return

    for name, data_dir in SEALED_SCENARIO_DIRS.items():
        try:
            decide = _load_fresh_policy()
        except Exception as e:  # noqa: BLE001 - untrusted import must never crash uncaught
            out["status"] = "malformed"
            out["error"] = f"{name}: failed to load policy.py: {e}"
            out["traces"][name] = None
            continue
        try:
            techs, jobs, shift_length = load_scenario(data_dir)
            result = sim.run_simulation(techs, jobs, shift_length, decide)
            out["traces"][name] = result.decision_trace
        except Exception as e:  # noqa: BLE001
            out["status"] = "crashed"
            out["error"] = f"{name}: {e}"
            out["traces"][name] = None
            # keep going -- still attempt the remaining scenario(s) so a
            # crash specific to one doesn't hide a result for the other

    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f)
    print(f"collected -> {OUT_PATH}: status={out['status']} scenarios={list(out['traces'].keys())}")


if __name__ == "__main__":
    main()
