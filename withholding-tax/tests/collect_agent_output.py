#!/usr/bin/env python3
"""
Stage 1 (UNTRUSTED). Runs as the unprivileged `runner` user, under a
wall-clock timeout enforced by test.sh (`timeout` wraps this whole
script).

The agent's deliverable is /app/outputs/engine.py: their fixed version
of the pipeline shipped at environment/pipeline/engine.py. This is a
one-shot batch computation (unlike the sibling field-service-dispatch
and cash-sweep bundles, there is no live decide()-per-event loop, no
incremental information revealed across calls, and nothing else running
that has secret state to introspect) so a plain subprocess invocation --
a genuinely separate OS process via `subprocess.run`, no shared Python
interpreter state -- is enough isolation: for each sealed held-out
dataset, this script runs `python3 /app/outputs/engine.py <data_dir>
<out_path>` as a fresh subprocess and does nothing else with the
candidate's code. Stage 2 never trusts anything this script decides --
it independently loads each subprocess's raw output file and re-checks
it against the sealed ground truth from scratch.

The raw scenario files under tests/sealed/inputs/ are intentionally NOT
sealed: the agent's own code has to read them to compute anything, the
same way the agent read them during its own turn against the visible
case/ dataset -- there is nothing secret about the inputs. What IS
sealed, before this script (or the agent's code) ever runs, is the
ground truth under tests/sealed/reference/ (test.sh chown+chmod's it to
root-only), so nothing running under this UID can read the correct
answer directly instead of computing it.
"""
import json
import os
import subprocess
import sys

ARTIFACT_PATH = "/app/outputs/engine.py"
SEALED_SCENARIO_DIRS = {
    "held_out_1": "/tests/sealed/inputs/held_out_1",
    "held_out_2": "/tests/sealed/inputs/held_out_2",
}
WORK_DIR = "/work"
PER_DATASET_TIMEOUT_SEC = 60


def main():
    out = {"status": "ok", "results": {}, "error": None}

    if not os.path.exists(ARTIFACT_PATH):
        out["status"] = "missing"
        _write(out)
        return

    for name, data_dir in SEALED_SCENARIO_DIRS.items():
        out_path = os.path.join(WORK_DIR, f"{name}_output.json")
        try:
            proc = subprocess.run(
                [sys.executable, ARTIFACT_PATH, data_dir, out_path],
                timeout=PER_DATASET_TIMEOUT_SEC,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            out["status"] = "crashed" if out["status"] == "ok" else out["status"]
            out["error"] = f"{name}: timed out after {PER_DATASET_TIMEOUT_SEC}s"
            out["results"][name] = None
            continue

        if proc.returncode != 0:
            out["status"] = "crashed" if out["status"] == "ok" else out["status"]
            out["error"] = f"{name}: exited {proc.returncode}: {proc.stderr[-2000:]}"
            out["results"][name] = None
            continue

        if not os.path.exists(out_path):
            out["status"] = "crashed" if out["status"] == "ok" else out["status"]
            out["error"] = f"{name}: no output file produced"
            out["results"][name] = None
            continue

        try:
            with open(out_path) as f:
                out["results"][name] = json.load(f)
        except json.JSONDecodeError as e:
            out["status"] = "crashed" if out["status"] == "ok" else out["status"]
            out["error"] = f"{name}: output is not valid JSON: {e}"
            out["results"][name] = None

    _write(out)


def _write(out):
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(os.path.join(WORK_DIR, "collected.json"), "w") as f:
        json.dump(out, f)
    print(f"collected -> {WORK_DIR}/collected.json: status={out['status']} datasets={list(out['results'].keys())}")


if __name__ == "__main__":
    main()
