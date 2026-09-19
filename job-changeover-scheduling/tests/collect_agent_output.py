"""Stage 1 (untrusted): run the candidate's submitted scheduler.py against
each sealed held-out instance, once each, as a fresh subprocess with the
disclosed time budget. Writes one status/result record per dataset under
/work for Stage 2 to grade."""
from __future__ import annotations

import json
import os
import subprocess
import sys

SCHEDULER_PATH = "/app/outputs/scheduler.py"
SEALED_INPUTS_DIR = "/tests/sealed/inputs"
WORK_DIR = "/work"

TIME_BUDGET_SEC = 180.0
SUBPROCESS_KILL_TIMEOUT_SEC = 195.0  # small grace beyond the disclosed budget for process overhead


def run_one(dataset_name: str) -> dict:
    data_dir = os.path.join(SEALED_INPUTS_DIR, dataset_name)
    instance_path = os.path.join(data_dir, "instance.json")
    out_path = os.path.join(WORK_DIR, f"{dataset_name}_output.json")

    if not os.path.exists(SCHEDULER_PATH):
        return {"dataset": dataset_name, "status": "missing_submission"}

    cmd = [
        sys.executable, SCHEDULER_PATH,
        "--instance", instance_path,
        "--output", out_path,
        "--time-budget", str(TIME_BUDGET_SEC),
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SUBPROCESS_KILL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return {"dataset": dataset_name, "status": "timeout"}

    if proc.returncode != 0:
        return {
            "dataset": dataset_name, "status": "crashed",
            "stderr": proc.stderr[-4000:],
        }

    if not os.path.exists(out_path):
        return {"dataset": dataset_name, "status": "no_output_file"}

    try:
        with open(out_path) as f:
            payload = json.load(f)
    except Exception as e:
        return {"dataset": dataset_name, "status": "unparseable_output", "error": str(e)}

    if "sequence" not in payload or not isinstance(payload["sequence"], list):
        return {"dataset": dataset_name, "status": "malformed_output"}

    return {"dataset": dataset_name, "status": "ok", "output_path": out_path}


def main() -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    results = [run_one(name) for name in sorted(os.listdir(SEALED_INPUTS_DIR))]
    with open(os.path.join(WORK_DIR, "collection_results.json"), "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
