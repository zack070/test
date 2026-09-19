#!/usr/bin/env python3
"""Cheat: computes the final ledger correctly (identical algorithm to the
reference solution) but only emits payment_allocations entries for
'release' events, silently skipping 'held_in_suspense' ones -- a plausible
shortcut for someone who thinks only actual money movements need to be
reported. Tests whether the verifier's allocation-coverage check catches
an otherwise-correct submission that skips part of the required output."""
import argparse
import json

CYCLE_DAYS = 30
LATE_FEE_GRACE_DAYS = 15


class LoanState:
    def __init__(self, lj):
        self.loan_id = lj["loan_id"]
        self.annual_rate = lj["annual_rate"]
        self.monthly_installment = lj["monthly_installment"]
        self.late_fee_amount = lj["late_fee_amount"]
        self.next_due_date = lj["first_due_day"]
        self.principal_balance = lj["opening_principal"]
        self.escrow_balance = lj["opening_escrow"]
        self.fees_owed = dict(lj["opening_fees"])
        self.disbursements = {int(day): amt for day, amt in lj["disbursements"]}
        self.accrued_interest = 0.0
        self.suspense_balance = 0.0
        self.late_fee_charged_for_cycle = False

    def fees_total(self):
        return sum(self.fees_owed.values())


def run(loans_json, payments_json, window_days):
    loans = {lj["loan_id"]: LoanState(lj) for lj in loans_json}
    pay_by_day = {}
    for p in payments_json:
        pay_by_day.setdefault(p["posting_date"], []).append(p)

    breakdown = []
    for d in range(1, window_days + 1):
        for loan in loans.values():
            loan.accrued_interest += loan.principal_balance * loan.annual_rate / 365.0
        for loan in loans.values():
            if d in loan.disbursements:
                loan.escrow_balance -= loan.disbursements[d]

        cash_today = {}
        for p in pay_by_day.get(d, []):
            cash_today[p["loan_id"]] = cash_today.get(p["loan_id"], 0.0) + p["amount"]

        for lid, loan in loans.items():
            c = cash_today.get(lid, 0.0)
            pending = loan.suspense_balance + c
            shortage = max(0.0, -loan.escrow_balance)
            required = loan.fees_total() + shortage + loan.monthly_installment

            if c > 0 or loan.suspense_balance > 0:
                if pending + 1e-9 >= required:
                    remaining = pending
                    paid = {}
                    for bucket in ("late", "nsf", "extension"):
                        pay = min(loan.fees_owed[bucket], remaining)
                        loan.fees_owed[bucket] -= pay
                        paid[bucket] = pay
                        remaining -= pay
                    pay = min(shortage, remaining)
                    loan.escrow_balance += pay
                    paid["escrow_shortage"] = pay
                    remaining -= pay
                    pay = min(loan.accrued_interest, remaining)
                    loan.accrued_interest -= pay
                    paid["interest"] = pay
                    remaining -= pay
                    paid["principal"] = remaining
                    loan.principal_balance -= remaining
                    loan.suspense_balance = 0.0
                    loan.next_due_date += CYCLE_DAYS
                    loan.late_fee_charged_for_cycle = False

                    breakdown.append({
                        "loan_id": lid, "posting_date": d, "event": "release",
                        "cash_in": round(c, 2), "released_from_suspense": round(pending - c, 2),
                        "fee_late": round(paid["late"], 2), "fee_nsf": round(paid["nsf"], 2),
                        "fee_extension": round(paid["extension"], 2),
                        "escrow_shortage_paid": round(paid["escrow_shortage"], 2),
                        "interest_paid": round(paid["interest"], 2),
                        "principal_paid": round(paid["principal"], 2),
                        "held_in_suspense": 0.0,
                    })
                else:
                    loan.suspense_balance = pending
                    # NOTE: intentionally does not append a held_in_suspense record

            dpd = max(0, d - loan.next_due_date)
            if dpd > LATE_FEE_GRACE_DAYS and not loan.late_fee_charged_for_cycle:
                loan.fees_owed["late"] += loan.late_fee_amount
                loan.late_fee_charged_for_cycle = True

    final_ledger = {}
    for lid, loan in loans.items():
        dpd = max(0, window_days - loan.next_due_date)
        final_ledger[lid] = {
            "principal_balance": round(loan.principal_balance, 2),
            "accrued_interest": round(loan.accrued_interest, 2),
            "escrow_balance": round(loan.escrow_balance, 2),
            "fees_owed": {k: round(v, 2) for k, v in loan.fees_owed.items()},
            "suspense_balance": round(loan.suspense_balance, 2),
            "next_due_date": loan.next_due_date,
            "days_past_due": dpd,
        }
    return {"final_ledger": final_ledger, "payment_allocations": breakdown}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loans", required=True)
    ap.add_argument("--payments", required=True)
    ap.add_argument("--window-days", required=True, type=int)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open(args.loans) as f:
        loans_json = json.load(f)
    with open(args.payments) as f:
        payments_json = json.load(f)

    result = run(loans_json, payments_json, args.window_days)
    with open(args.output, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
