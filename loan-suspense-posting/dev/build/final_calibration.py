import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import naive_immediate
import naive_effdate

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEALED_DIR = os.path.join(ROOT, "tests", "sealed", "inputs", "case")
REF_PATH = os.path.join(ROOT, "tests", "sealed", "reference", "case_reference.json")

MONEY_FIELDS = ("principal_balance", "accrued_interest", "escrow_balance", "suspense_balance")


def compare(ref_ledger, other_ledger, label):
    n = len(ref_ledger)
    exact = 0
    total_abs_err = {f: 0.0 for f in MONEY_FIELDS}
    loans_with_any_mismatch = 0
    for lid in ref_ledger:
        r, o = ref_ledger[lid], other_ledger[lid]
        loan_mismatch = False
        for f in MONEY_FIELDS:
            d = abs(r[f] - o[f])
            total_abs_err[f] += d
            if d > 0.005:
                loan_mismatch = True
        if r["fees_owed"] != o["fees_owed"]:
            loan_mismatch = True
        if int(r["next_due_date"]) != int(o["next_due_date"]):
            loan_mismatch = True
        if int(r["days_past_due"]) != int(o["days_past_due"]):
            loan_mismatch = True
        if loan_mismatch:
            loans_with_any_mismatch += 1
        else:
            exact += 1
    print(f"--- {label} (80-loan, 75-day sealed portfolio) ---")
    print(f"loans exactly matching reference: {exact}/{n}")
    print(f"loans with at least one wrong field (would fail verifier): {loans_with_any_mismatch}/{n}")
    for f in MONEY_FIELDS:
        print(f"  total |{f} error|: ${total_abs_err[f]:,.2f}")
    print()


if __name__ == "__main__":
    with open(os.path.join(SEALED_DIR, "loans.json")) as f:
        loans_json = json.load(f)
    with open(os.path.join(SEALED_DIR, "payments.json")) as f:
        payments_json = json.load(f)
    with open(os.path.join(SEALED_DIR, "window.json")) as f:
        window_days = json.load(f)["window_days"]
    with open(REF_PATH) as f:
        reference = json.load(f)["final_ledger"]

    naive_final = naive_immediate.run(loans_json, payments_json, window_days)
    compare(reference, naive_final, "naive_immediate (no suspense)")

    effdate_final = naive_effdate.run(loans_json, payments_json, window_days)
    compare(reference, effdate_final, "naive_effdate (uses effective_date)")
