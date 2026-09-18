#!/usr/bin/env python3
"""
Stage 1 (UNTRUSTED). Runs as the unprivileged `runner` user, under a
wall-clock timeout enforced by test.sh (`timeout` wraps this whole script).

Imports the candidate's submitted policy module and runs it, via the real
simulator, against the sealed held-out scenario. Records the RAW decision
trace (list of (tech_id, job_id) pairs the candidate's decide() returned at
each call) to /work/trace.json. Makes no pass/fail judgment and does not
trust its own computed cost for grading purposes -- Stage 2 independently
replays the trace through the trusted simulator from scratch. This script
never reads anything under tests/sealed/reference (sealed 700/600 before
this runs) and the scenario input data it does read is not the answer to
anything -- only the trace it produces matters downstream.
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import simulator as sim

ARTIFACT_PATH = "/app/outputs/policy.py"
SEALED_SCENARIO_DIR = "/tests/sealed/inputs/held_out"
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


def main():
    out = {"status": "ok", "trace": None, "error": None}

    if not os.path.exists(ARTIFACT_PATH):
        out["status"] = "missing"
        _write(out)
        return

    try:
        spec = importlib.util.spec_from_file_location("candidate_policy", ARTIFACT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        decide = getattr(mod, "decide", None)
        if decide is None or not callable(decide):
            out["status"] = "malformed"
            out["error"] = "policy.py does not define a callable decide(state)"
            _write(out)
            return
    except Exception as e:  # noqa: BLE001 - untrusted import must never crash uncaught
        out["status"] = "malformed"
        out["error"] = f"failed to load policy.py: {e}"
        _write(out)
        return

    try:
        techs, jobs, shift_length = load_scenario(SEALED_SCENARIO_DIR)
        result = sim.run_simulation(techs, jobs, shift_length, decide)
        out["trace"] = result.decision_trace
    except Exception as e:  # noqa: BLE001
        out["status"] = "crashed"
        out["error"] = str(e)

    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f)
    print(f"collected -> {OUT_PATH}: status={out['status']}")


if __name__ == "__main__":
    main()
