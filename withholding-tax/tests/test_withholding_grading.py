"""
Verifier (TRUSTED, runs as root in its own container the agent never
sees). No candidate code executes here at all -- the agent's deliverable
is a data file (/app/outputs/report.json), not a program, so there is
nothing to run and nothing to isolate. This script only reads that
artifact and compares it against the sealed ground truth computed ahead
of time from environment/data/case (tests/sealed/reference/
ground_truth.json), with a small absolute tolerance to accommodate
legitimate floating-point implementation differences -- not to forgive
the two validated traps or any of the boundary conventions, which each
diverge from the ground truth by orders of magnitude more than this
tolerance (see cheat/README.md for the measured margins).
"""
import json
import os

import pytest

ARTIFACT_PATH = "/app/outputs/report.json"
GROUND_TRUTH_PATH = "/tests/sealed/reference/ground_truth.json"
LINE_TOLERANCE_USD = 0.02
TOTAL_TOLERANCE_USD = 0.05


@pytest.fixture(scope="session")
def ground_truth():
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def submitted():
    if not os.path.exists(ARTIFACT_PATH):
        pytest.fail(f"no artifact found at {ARTIFACT_PATH}")
    with open(ARTIFACT_PATH) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"artifact at {ARTIFACT_PATH} is not valid JSON: {e}")


def test_artifact_present_and_well_formed(submitted):
    assert isinstance(submitted, dict), "top-level artifact must be a JSON object"
    assert "payments" in submitted, "artifact missing required 'payments' key"
    assert "total_liability_usd" in submitted, "artifact missing required 'total_liability_usd' key"
    assert isinstance(submitted["payments"], list), "'payments' must be a list"


def test_every_payment_present(submitted, ground_truth):
    submitted_ids = {ln.get("payment_id") for ln in submitted["payments"] if isinstance(ln, dict)}
    expected_ids = {ln["payment_id"] for ln in ground_truth["payments"]}
    missing = expected_ids - submitted_ids
    extra = submitted_ids - expected_ids
    assert not missing, f"missing payment_id(s) in submitted report: {sorted(missing)[:10]}"
    assert not extra, f"unexpected payment_id(s) in submitted report: {sorted(extra)[:10]}"


def test_every_payment_final_withholding_correct(submitted, ground_truth):
    by_id = {ln["payment_id"]: ln for ln in submitted["payments"] if isinstance(ln, dict)}
    bad = []
    for exp in ground_truth["payments"]:
        pid = exp["payment_id"]
        got = by_id.get(pid, {})
        got_val = got.get("final_withholding_usd")
        if got_val is None or not isinstance(got_val, (int, float)):
            bad.append((pid, "missing or non-numeric final_withholding_usd"))
            continue
        if abs(got_val - exp["final_withholding_usd"]) > LINE_TOLERANCE_USD:
            bad.append((pid, f"expected {exp['final_withholding_usd']}, got {got_val}"))
    assert not bad, f"{len(bad)} payment(s) wrong (showing up to 10): {bad[:10]}"


def test_every_payment_true_up_correct(submitted, ground_truth):
    by_id = {ln["payment_id"]: ln for ln in submitted["payments"] if isinstance(ln, dict)}
    bad = []
    for exp in ground_truth["payments"]:
        pid = exp["payment_id"]
        got = by_id.get(pid, {})
        got_val = got.get("true_up_usd")
        if got_val is None or not isinstance(got_val, (int, float)):
            bad.append((pid, "missing or non-numeric true_up_usd"))
            continue
        if abs(got_val - exp["true_up_usd"]) > LINE_TOLERANCE_USD:
            bad.append((pid, f"expected {exp['true_up_usd']}, got {got_val}"))
    assert not bad, f"{len(bad)} payment(s) wrong true_up (showing up to 10): {bad[:10]}"


def test_grand_total_correct(submitted, ground_truth):
    got = submitted.get("total_liability_usd")
    assert isinstance(got, (int, float)), "total_liability_usd missing or non-numeric"
    assert abs(got - ground_truth["total_liability_usd"]) <= TOTAL_TOLERANCE_USD, (
        f"total_liability_usd: expected {ground_truth['total_liability_usd']}, got {got}"
    )
