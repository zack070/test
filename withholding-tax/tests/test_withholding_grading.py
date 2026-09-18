"""
Stage 2 (TRUSTED). Runs as root. Never imports or executes anything from
the candidate; takes the raw output JSON Stage 1 collected from running
the candidate's engine.py against each sealed held-out dataset, and
independently checks it against the ground truth computed ahead of time
from that same dataset (tests/sealed/reference/<name>_ground_truth.json).
Both held-out datasets must pass individually -- not an average -- so a
fix tuned to only one dataset's particular bug manifestations cannot
coast on the other.
"""
import json
import os

import pytest

COLLECTED_PATH = "/work/collected.json"
SEALED_BAR_DIR = "/tests/sealed/reference"
DATASET_NAMES = ["held_out_1", "held_out_2"]
LINE_TOLERANCE_USD = 0.02
TOTAL_TOLERANCE_USD = 0.05
RATE_TOLERANCE = 1e-6


@pytest.fixture(scope="session")
def collected():
    with open(COLLECTED_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def ground_truths():
    truths = {}
    for name in DATASET_NAMES:
        with open(os.path.join(SEALED_BAR_DIR, f"{name}_ground_truth.json")) as f:
            truths[name] = json.load(f)
    return truths


def test_policy_present_and_ran(collected):
    assert collected["status"] == "ok", collected


@pytest.mark.parametrize("dataset_name", DATASET_NAMES)
def test_dataset_correct(dataset_name, collected, ground_truths):
    if collected["status"] != "ok":
        pytest.fail(f"engine.py could not be run: status={collected['status']} error={collected.get('error')}")
    submitted = collected["results"].get(dataset_name)
    if submitted is None:
        pytest.fail(f"no output collected for {dataset_name}: status={collected['status']} error={collected.get('error')}")
    ground_truth = ground_truths[dataset_name]

    assert isinstance(submitted, dict), f"[{dataset_name}] top-level output must be a JSON object"
    assert "payments" in submitted, f"[{dataset_name}] output missing 'payments' key"
    assert "total_liability_usd" in submitted, f"[{dataset_name}] output missing 'total_liability_usd' key"
    assert isinstance(submitted["payments"], list), f"[{dataset_name}] 'payments' must be a list"

    submitted_ids = {ln.get("payment_id") for ln in submitted["payments"] if isinstance(ln, dict)}
    expected_ids = {ln["payment_id"] for ln in ground_truth["payments"]}
    missing = expected_ids - submitted_ids
    extra = submitted_ids - expected_ids
    assert not missing, f"[{dataset_name}] missing payment_id(s): {sorted(missing)[:10]}"
    assert not extra, f"[{dataset_name}] unexpected payment_id(s): {sorted(extra)[:10]}"

    by_id = {ln["payment_id"]: ln for ln in submitted["payments"] if isinstance(ln, dict)}
    bad = []
    for exp in ground_truth["payments"]:
        pid = exp["payment_id"]
        got = by_id.get(pid, {})
        for field, tol in (
            ("initial_rate", RATE_TOLERANCE),
            ("final_rate", RATE_TOLERANCE),
            ("initial_withholding_usd", LINE_TOLERANCE_USD),
            ("final_withholding_usd", LINE_TOLERANCE_USD),
            ("true_up_usd", LINE_TOLERANCE_USD),
        ):
            got_val = got.get(field)
            if got_val is None or not isinstance(got_val, (int, float)):
                bad.append((pid, f"missing or non-numeric {field}"))
                continue
            if abs(got_val - exp[field]) > tol:
                bad.append((pid, f"{field}: expected {exp[field]}, got {got_val}"))
    assert not bad, f"[{dataset_name}] {len(bad)} field(s) wrong (showing up to 10): {bad[:10]}"

    got_total = submitted.get("total_liability_usd")
    assert isinstance(got_total, (int, float)), f"[{dataset_name}] total_liability_usd missing or non-numeric"
    assert abs(got_total - ground_truth["total_liability_usd"]) <= TOTAL_TOLERANCE_USD, (
        f"[{dataset_name}] total_liability_usd: expected {ground_truth['total_liability_usd']}, got {got_total}"
    )
