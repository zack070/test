"""Stage 2 (trusted): independently re-check Stage 1's collected sequence
against each sealed instance's own frozen reference (objective + pass
bar), never executing candidate code. Structural checks (permutation
validity) run before any scoring, and are exact/deterministic."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, "/tests/lib")
from scorer import score_sequence  # noqa: E402

WORK_DIR = "/work"
SEALED_INPUTS_DIR = "/tests/sealed/inputs"
SEALED_REFERENCE_DIR = "/tests/sealed/reference"

DATASETS = sorted(os.listdir(SEALED_INPUTS_DIR))


def _load_collection_results():
    path = os.path.join(WORK_DIR, "collection_results.json")
    with open(path) as f:
        return {r["dataset"]: r for r in json.load(f)}


def test_scheduler_present_and_ran():
    results = _load_collection_results()
    for name in DATASETS:
        assert name in results, f"no collection result for {name}"
        assert results[name]["status"] == "ok", (
            f"[{name}] scheduler.py did not produce usable output: {results[name]}"
        )


@pytest.mark.parametrize("dataset_name", DATASETS)
def test_dataset_meets_bar(dataset_name):
    results = _load_collection_results()
    result = results[dataset_name]
    assert result["status"] == "ok", f"[{dataset_name}] {result}"

    with open(result["output_path"]) as f:
        payload = json.load(f)
    sequence = payload["sequence"]

    with open(os.path.join(SEALED_INPUTS_DIR, dataset_name, "instance.json")) as f:
        instance = json.load(f)
    jobs_by_id = {j["job_id"]: j for j in instance["jobs"]}
    all_ids = set(jobs_by_id.keys())

    assert len(sequence) == len(set(sequence)), f"[{dataset_name}] sequence has duplicate job_ids"
    assert set(sequence) == all_ids, (
        f"[{dataset_name}] sequence must be a permutation of every job_id "
        f"(missing: {sorted(all_ids - set(sequence))[:5]}, "
        f"extra: {sorted(set(sequence) - all_ids)[:5]})"
    )

    objective = score_sequence(sequence, jobs_by_id, instance["setup_matrix"], instance["initial_setup"])

    with open(os.path.join(SEALED_REFERENCE_DIR, f"{dataset_name}_reference.json")) as f:
        reference = json.load(f)

    assert objective <= reference["pass_bar"], (
        f"[{dataset_name}] objective {objective:,} exceeds pass bar {reference['pass_bar']:,} "
        f"(reference solution scored {reference['reference_objective']:,})"
    )
