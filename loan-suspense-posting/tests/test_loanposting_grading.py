"""Stage 2 (trusted): independently check Stage 1's collected output
against each sealed dataset's frozen reference. No candidate code runs
here. Monetary fields compare to the cent (0.005 tolerance to absorb
floating point representation, never algorithmic slack); dates, buckets
and event labels compare exactly."""
from __future__ import annotations

import json
import os

import pytest

WORK_DIR = "/work"
SEALED_INPUTS_DIR = "/tests/sealed/inputs"
SEALED_REFERENCE_DIR = "/tests/sealed/reference"

DATASETS = sorted(os.listdir(SEALED_INPUTS_DIR))

MONEY_FIELDS = ("principal_balance", "accrued_interest", "escrow_balance", "suspense_balance")
FEE_BUCKETS = ("late", "nsf", "extension")
ALLOC_MONEY_FIELDS = (
    "cash_in", "released_from_suspense", "fee_late", "fee_nsf", "fee_extension",
    "escrow_shortage_paid", "interest_paid", "principal_paid", "held_in_suspense",
)
CENT = 0.005


def _load_collection_results():
    path = os.path.join(WORK_DIR, "collection_results.json")
    with open(path) as f:
        return {r["dataset"]: r for r in json.load(f)}


def test_poster_present_and_ran():
    results = _load_collection_results()
    for name in DATASETS:
        assert name in results, f"no collection result for {name}"
        assert results[name]["status"] == "ok", (
            f"[{name}] poster.py did not produce usable output: {results[name]}"
        )


@pytest.mark.parametrize("dataset_name", DATASETS)
def test_dataset_ledger_matches_reference(dataset_name):
    results = _load_collection_results()
    result = results[dataset_name]
    assert result["status"] == "ok", f"[{dataset_name}] {result}"

    with open(result["output_path"]) as f:
        payload = json.load(f)

    with open(os.path.join(SEALED_INPUTS_DIR, dataset_name, "loans.json")) as f:
        loan_ids = {lj["loan_id"] for lj in json.load(f)}

    with open(os.path.join(SEALED_REFERENCE_DIR, f"{dataset_name}_reference.json")) as f:
        reference = json.load(f)

    ledger = payload["final_ledger"]
    assert set(ledger.keys()) == loan_ids, (
        f"[{dataset_name}] final_ledger must cover exactly the loans in this dataset "
        f"(missing: {sorted(loan_ids - set(ledger.keys()))[:5]}, "
        f"extra: {sorted(set(ledger.keys()) - loan_ids)[:5]})"
    )

    ref_ledger = reference["final_ledger"]
    for lid in sorted(loan_ids):
        got, exp = ledger[lid], ref_ledger[lid]
        for field in MONEY_FIELDS:
            assert field in got, f"[{dataset_name}] {lid} missing field '{field}'"
            assert abs(float(got[field]) - float(exp[field])) <= CENT, (
                f"[{dataset_name}] {lid}.{field}: got {got[field]}, expected {exp[field]}"
            )
        assert "fees_owed" in got, f"[{dataset_name}] {lid} missing 'fees_owed'"
        for bucket in FEE_BUCKETS:
            g = float(got["fees_owed"].get(bucket, float("nan")))
            e = float(exp["fees_owed"][bucket])
            assert abs(g - e) <= CENT, (
                f"[{dataset_name}] {lid}.fees_owed.{bucket}: got {g}, expected {e}"
            )
        assert int(got["next_due_date"]) == int(exp["next_due_date"]), (
            f"[{dataset_name}] {lid}.next_due_date: got {got['next_due_date']}, "
            f"expected {exp['next_due_date']}"
        )
        assert int(got["days_past_due"]) == int(exp["days_past_due"]), (
            f"[{dataset_name}] {lid}.days_past_due: got {got['days_past_due']}, "
            f"expected {exp['days_past_due']}"
        )


@pytest.mark.parametrize("dataset_name", DATASETS)
def test_dataset_payment_allocations_match_reference(dataset_name):
    results = _load_collection_results()
    result = results[dataset_name]
    assert result["status"] == "ok", f"[{dataset_name}] {result}"

    with open(result["output_path"]) as f:
        payload = json.load(f)

    with open(os.path.join(SEALED_REFERENCE_DIR, f"{dataset_name}_reference.json")) as f:
        reference = json.load(f)

    got_allocs = payload.get("payment_allocations")
    assert isinstance(got_allocs, list), f"[{dataset_name}] payment_allocations must be a list"

    def keyed(records):
        out = {}
        for r in records:
            key = (r["loan_id"], int(r["posting_date"]))
            assert key not in out, (
                f"[{dataset_name}] duplicate payment_allocations entry for "
                f"loan={key[0]} day={key[1]}"
            )
            out[key] = r
        return out

    got_by_key = keyed(got_allocs)
    ref_by_key = keyed(reference["payment_allocations"])

    assert set(got_by_key.keys()) == set(ref_by_key.keys()), (
        f"[{dataset_name}] payment_allocations must have exactly one entry per "
        f"(loan, posting_date) with activity in the reference "
        f"(missing: {sorted(set(ref_by_key) - set(got_by_key))[:5]}, "
        f"extra: {sorted(set(got_by_key) - set(ref_by_key))[:5]})"
    )

    for key in sorted(ref_by_key.keys()):
        got, exp = got_by_key[key], ref_by_key[key]
        assert got.get("event") == exp["event"], (
            f"[{dataset_name}] {key}: event got {got.get('event')!r}, expected {exp['event']!r}"
        )
        for field in ALLOC_MONEY_FIELDS:
            g = float(got.get(field, float("nan")))
            e = float(exp[field])
            assert abs(g - e) <= CENT, (
                f"[{dataset_name}] {key}.{field}: got {got.get(field)}, expected {exp[field]}"
            )
