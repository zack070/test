import copy
import sys
from generator import make_portfolio, WINDOW_DAYS
from model import run_reference
from naive_immediate import run_naive_immediate
from naive_effdate import run_naive_effdate

SEED = 1234
N_LOANS = 24


def compare(ref, other, label):
    n_loans = len(ref)
    n_loans_exact = 0
    field_mismatches = {"principal_balance": 0, "accrued_interest": 0, "escrow_balance": 0,
                         "fees_owed": 0, "suspense_balance": 0, "next_due_date": 0, "days_past_due": 0}
    total_abs_principal_err = 0.0
    total_abs_interest_err = 0.0
    worst = []

    for lid in ref:
        r, o = ref[lid], other[lid]
        exact = True
        for f in ("principal_balance", "accrued_interest", "escrow_balance", "suspense_balance",
                  "next_due_date", "days_past_due"):
            rv, ov = r[f], o[f]
            if isinstance(rv, float):
                if abs(rv - ov) > 0.005:
                    field_mismatches[f] += 1
                    exact = False
            else:
                if rv != ov:
                    field_mismatches[f] += 1
                    exact = False
        if r["fees_owed"] != o["fees_owed"]:
            field_mismatches["fees_owed"] += 1
            exact = False

        total_abs_principal_err += abs(r["principal_balance"] - o["principal_balance"])
        total_abs_interest_err += abs(r["accrued_interest"] - o["accrued_interest"])
        if not exact:
            worst.append((lid, r, o))
        else:
            n_loans_exact += 1

    print(f"--- {label} ---")
    print(f"loans exact match: {n_loans_exact}/{n_loans}")
    print(f"field mismatch counts: {field_mismatches}")
    print(f"total |principal err|: {total_abs_principal_err:.2f}  total |interest err|: {total_abs_interest_err:.2f}")
    print(f"sample mismatches (up to 3):")
    for lid, r, o in worst[:3]:
        print(f"  {lid}: ref={r}")
        print(f"       {label}={o}")
    print()
    return n_loans_exact, n_loans


if __name__ == "__main__":
    loans_ref, payments = make_portfolio(N_LOANS, SEED)
    ref_final, breakdown, trace = run_reference(loans_ref, payments, WINDOW_DAYS, trace=True)

    loans_a, payments_a = make_portfolio(N_LOANS, SEED)
    naive_final = run_naive_immediate(loans_a, payments_a, WINDOW_DAYS)

    loans_b, payments_b = make_portfolio(N_LOANS, SEED)
    effdate_final = run_naive_effdate(loans_b, payments_b, WINDOW_DAYS)

    # sanity: how many payments ever got held in suspense at all (mechanism relevance check)
    n_suspense_events = sum(1 for b in breakdown if b["event"] == "held_in_suspense")
    n_release_events = sum(1 for b in breakdown if b["event"] == "release")
    print(f"payment events: {len(payments)}  held_in_suspense events: {n_suspense_events}  release events: {n_release_events}")
    print()

    compare(ref_final, naive_final, "naive_immediate")
    compare(ref_final, effdate_final, "naive_effdate")
