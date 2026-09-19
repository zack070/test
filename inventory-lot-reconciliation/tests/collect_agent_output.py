"""Stage 1 (untrusted): run the candidate's submitted engine.py against
each sealed held-out dataset, once each, as a fresh subprocess. Writes one
status/result record per dataset under /work for Stage 2 to grade."""
from __future__ import annotations

import json
import os
import subprocess
import sys

ENGINE_PATH = "/app/outputs/engine.py"
SEALED_INPUTS_DIR = "/tests/sealed/inputs"
WORK_DIR = "/work"
PER_DATASET_TIMEOUT_SEC = 60


def run_one(dataset_name: str) -> dict:
    data_dir = os.path.join(SEALED_INPUTS_DIR, dataset_name)
    out_path = os.path.join(WORK_DIR, f"{dataset_name}_output.json")

    if not os.path.exists(ENGINE_PATH):
        return {"dataset": dataset_name, "status": "missing_submission"}

    cmd = [sys.executable, ENGINE_PATH, data_dir, out_path]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=PER_DATASET_TIMEOUT_SEC,
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

    if "skus" not in payload or not isinstance(payload["skus"], dict):
        return {"dataset": dataset_name, "status": "malformed_output"}

    return {"dataset": dataset_name, "status": "ok", "output_path": out_path}


def main() -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    results = [run_one(name) for name in sorted(os.listdir(SEALED_INPUTS_DIR))]
    with open(os.path.join(WORK_DIR, "collection_results.json"), "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
