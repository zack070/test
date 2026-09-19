"""Stage 2 (trusted): independently check Stage 1's collected output
against each sealed dataset's frozen reference. No candidate code runs
here. The frozen reference was computed from an independently-written
implementation (tests/lib/reference_engine.py) at build time, cross-
checked against the reference solution before being trusted."""
from __future__ import annotations

import json
import os

import pytest

WORK_DIR = "/work"
SEALED_INPUTS_DIR = "/tests/sealed/inputs"
SEALED_REFERENCE_DIR = "/tests/sealed/reference"

DATASETS = sorted(os.listdir(SEALED_INPUTS_DIR))
CENT = 0.005


def _load_collection_results():
    path = os.path.join(WORK_DIR, "collection_results.json")
    with open(path) as f:
        return {r["dataset"]: r for r in json.load(f)}


def test_engine_present_and_ran():
    results = _load_collection_results()
    for name in DATASETS:
        assert name in results, f"no collection result for {name}"
        assert results[name]["status"] == "ok", (
            f"[{name}] engine.py did not produce usable output: {results[name]}"
        )


@pytest.mark.parametrize("dataset_name", DATASETS)
def test_dataset_matches_reference(dataset_name):
    results = _load_collection_results()
    result = results[dataset_name]
    assert result["status"] == "ok", f"[{dataset_name}] {result}"

    with open(result["output_path"]) as f:
        payload = json.load(f)
    skus = payload["skus"]

    with open(os.path.join(SEALED_REFERENCE_DIR, f"{dataset_name}_reference.json")) as f:
        reference = json.load(f)["skus"]

    assert set(skus.keys()) == set(reference.keys()), (
        f"[{dataset_name}] output must cover exactly the skus in the reference "
        f"(missing: {sorted(set(reference) - set(skus))[:5]}, "
        f"extra: {sorted(set(skus) - set(reference))[:5]})"
    )

    for sku in sorted(reference.keys()):
        got, exp = skus[sku], reference[sku]
        assert "on_hand_qty" in got, f"[{dataset_name}] {sku} missing on_hand_qty"
        assert abs(float(got["on_hand_qty"]) - float(exp["on_hand_qty"])) <= CENT, (
            f"[{dataset_name}] {sku}.on_hand_qty: got {got.get('on_hand_qty')}, expected {exp['on_hand_qty']}"
        )
        assert "valuation" in got, f"[{dataset_name}] {sku} missing valuation"
        assert abs(float(got["valuation"]) - float(exp["valuation"])) <= CENT, (
            f"[{dataset_name}] {sku}.valuation: got {got.get('valuation')}, expected {exp['valuation']}"
        )
