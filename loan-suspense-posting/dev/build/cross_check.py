import json
import sys
import model_a
import model_b
from generator import make_portfolio, make_worked_example, WINDOW_DAYS


def diff(a, b, label):
    mism = 0
    for lid in a:
        for f in ("principal_balance", "accrued_interest", "escrow_balance", "suspense_balance",
                  "next_due_date", "days_past_due"):
            av, bv = a[lid][f], b[lid][f]
            if isinstance(av, float):
                if abs(av - bv) > 0.005:
                    print(f"  MISMATCH {label} {lid}.{f}: A={av} B={bv}")
                    mism += 1
            elif av != bv:
                print(f"  MISMATCH {label} {lid}.{f}: A={av} B={bv}")
                mism += 1
        if a[lid]["fees_owed"] != b[lid]["fees_owed"]:
            print(f"  MISMATCH {label} {lid}.fees_owed: A={a[lid]['fees_owed']} B={b[lid]['fees_owed']}")
            mism += 1
    print(f"{label}: {mism} field mismatches across {len(a)} loans")
    return mism


if __name__ == "__main__":
    total_mism = 0

    loans, payments, wd = make_worked_example()
    fa, ba = model_a.run(loans, payments, wd)
    fb, bb = model_b.run(loans, payments, wd)
    print("== worked_example ==")
    for lid in fa:
        print(lid, "A:", fa[lid])
        print(lid, "B:", fb[lid])
    total_mism += diff(fa, fb, "worked_example")

    for name, seed in (("case", 4242), ("sealed", 90909)):
        loans, payments = make_portfolio(seed, n_loans=80, window_days=WINDOW_DAYS)
        fa, ba = model_a.run(loans, payments, WINDOW_DAYS)
        fb, bb = model_b.run(loans, payments, WINDOW_DAYS)
        print(f"== {name} (seed {seed}) ==")
        total_mism += diff(fa, fb, name)

    print()
    if total_mism == 0:
        print("CROSS-CHECK PASSED: model_a and model_b agree everywhere.")
        sys.exit(0)
    else:
        print(f"CROSS-CHECK FAILED: {total_mism} mismatches. Debug before trusting either model.")
        sys.exit(1)
