"""
Generates all data files for the bundle: environment/data/worked_example,
environment/data/case (practice, seed=4242), tests/sealed/inputs/case
(grading, seed=90909, DIFFERENT from practice), and freezes the sealed
reference answer computed with model_b (independent of solution/poster.py,
which is based on model_a).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import model_a
import model_b
from generator import make_portfolio, make_worked_example, WINDOW_DAYS

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

CASE_SEED = 4242
SEALED_SEED = 90909


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def main():
    # --- worked example ---
    loans, payments, wd = make_worked_example()
    dump(loans, os.path.join(ROOT, "environment/data/worked_example/loans.json"))
    dump(payments, os.path.join(ROOT, "environment/data/worked_example/payments.json"))
    dump({"window_days": wd}, os.path.join(ROOT, "environment/data/worked_example/window.json"))

    # --- practice case (visible to agent, NOT the graded data) ---
    loans, payments = make_portfolio(CASE_SEED, n_loans=80, window_days=WINDOW_DAYS)
    dump(loans, os.path.join(ROOT, "environment/data/case/loans.json"))
    dump(payments, os.path.join(ROOT, "environment/data/case/payments.json"))
    dump({"window_days": WINDOW_DAYS}, os.path.join(ROOT, "environment/data/case/window.json"))

    # --- sealed grading case (never shown to agent) ---
    s_loans, s_payments = make_portfolio(SEALED_SEED, n_loans=80, window_days=WINDOW_DAYS)
    dump(s_loans, os.path.join(ROOT, "tests/sealed/inputs/case/loans.json"))
    dump(s_payments, os.path.join(ROOT, "tests/sealed/inputs/case/payments.json"))
    dump({"window_days": WINDOW_DAYS}, os.path.join(ROOT, "tests/sealed/inputs/case/window.json"))

    # freeze sealed reference using model_b (independent of solution/poster.py's model_a lineage)
    final_b, breakdown_b = model_b.run(s_loans, s_payments, WINDOW_DAYS)
    # cross-check against model_a before freezing
    final_a, breakdown_a = model_a.run(s_loans, s_payments, WINDOW_DAYS)
    mism = 0
    for lid in final_a:
        for f in ("principal_balance", "accrued_interest", "escrow_balance", "suspense_balance",
                  "next_due_date", "days_past_due"):
            av, bv = final_a[lid][f], final_b[lid][f]
            if isinstance(av, float):
                if abs(av - bv) > 0.005:
                    mism += 1
            elif av != bv:
                mism += 1
        if final_a[lid]["fees_owed"] != final_b[lid]["fees_owed"]:
            mism += 1
    if mism:
        print(f"REFUSING TO FREEZE: {mism} mismatches between model_a and model_b on sealed data")
        sys.exit(1)

    sealed_reference = {"final_ledger": final_b, "payment_allocations": breakdown_b}
    dump(sealed_reference, os.path.join(ROOT, "tests/sealed/reference/case_reference.json"))
    print("Bundle data files written. Sealed reference frozen from model_b, cross-checked against model_a: 0 mismatches.")
    print(f"sealed payment events: {len(s_payments)}, allocation records: {len(breakdown_b)}")


if __name__ == "__main__":
    main()
