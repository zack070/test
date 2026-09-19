"""Stage 2 (trusted): independently re-check Stage 1's collected decisions
against each sealed dataset's own reference (RNG seed + pass bar), never
executing candidate code. Feasibility (budget cap) is checked mechanically
before any simulation runs."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, "/tests/lib")
from model import budget_used, is_feasible, objective  # noqa: E402
from portfolio_io import load_portfolio  # noqa: E402

WORK_DIR = "/work"
SEALED_INPUTS_DIR = "/tests/sealed/inputs"
SEALED_REFERENCE_DIR = "/tests/sealed/reference"

DATASETS = sorted(os.listdir(SEALED_INPUTS_DIR))


def _load_collection_results():
    path = os.path.join(WORK_DIR, "collection_results.json")
    with open(path) as f:
        return {r["dataset"]: r for r in json.load(f)}


def test_policy_present_and_ran():
    results = _load_collection_results()
    for name in DATASETS:
        assert name in results, f"no collection result for {name}"
        assert results[name]["status"] == "ok", (
            f"[{name}] policy did not produce usable output: {results[name]}"
        )


@pytest.mark.parametrize("dataset_name", DATASETS)
def test_dataset_meets_bar(dataset_name):
    results = _load_collection_results()
    result = results[dataset_name]
    assert result["status"] == "ok", f"[{dataset_name}] {result}"

    with open(result["decisions_path"]) as f:
        payload = json.load(f)
    raw_decisions = payload["decisions"]

    portfolio = load_portfolio(os.path.join(SEALED_INPUTS_DIR, dataset_name))
    claims, cfg = portfolio["claims"], portfolio["config"]
    claim_ids = {c.claim_id for c in claims}

    assert set(raw_decisions.keys()) == claim_ids, (
        f"[{dataset_name}] decisions must cover exactly the claims in this dataset "
        f"(missing: {sorted(claim_ids - set(raw_decisions.keys()))[:5]}, "
        f"extra: {sorted(set(raw_decisions.keys()) - claim_ids)[:5]})"
    )
    decisions = {}
    for cid, v in raw_decisions.items():
        assert v in (0, 1), f"[{dataset_name}] decision for {cid} must be 0 or 1, got {v!r}"
        decisions[cid] = int(v)

    used = budget_used(claims, decisions, cfg)
    assert is_feasible(claims, decisions, cfg), (
        f"[{dataset_name}] budget exceeded: used ${used:,.2f} > cap ${cfg.budget_usd:,.2f}"
    )

    with open(os.path.join(SEALED_REFERENCE_DIR, f"{dataset_name}_reference.json")) as f:
        reference = json.load(f)

    rng = np.random.default_rng(reference["eval_seed"])
    result_metrics = objective(claims, decisions, cfg, rng, reference["eval_n_paths"])

    assert result_metrics["objective"] <= reference["pass_bar_objective"], (
        f"[{dataset_name}] objective {result_metrics['objective']:,.0f} exceeds "
        f"pass bar {reference['pass_bar_objective']:,.0f} "
        f"(expected_cost={result_metrics['expected_cost']:,.0f}, "
        f"cvar={result_metrics['cvar']:,.0f})"
    )
