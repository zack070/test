#!/usr/bin/env python3
"""
Reference solution for the nightly loan-posting task.

Usage:
    python3 poster.py --loans LOANS_JSON --payments PAYMENTS_JSON \
        --window-days N --output OUTPUT_JSON

Implements the posting rules described in SERVICING_SPEC.md: per-diem
actual/365 accrual, escrow-shortage-before-release evaluation, the
suspense/full-release mechanism, the fees->escrow->interest->principal
waterfall, and once-per-cycle late fee assessment.
"""
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
                        "cash_in": round(c, 2),
                        "released_from_suspense": round(pending - c, 2),
                        "fee_late": round(paid["late"], 2),
                        "fee_nsf": round(paid["nsf"], 2),
                        "fee_extension": round(paid["extension"], 2),
                        "escrow_shortage_paid": round(paid["escrow_shortage"], 2),
                        "interest_paid": round(paid["interest"], 2),
                        "principal_paid": round(paid["principal"], 2),
                        "held_in_suspense": 0.0,
                    })
                else:
                    loan.suspense_balance = pending
                    if c > 0:
                        breakdown.append({
                            "loan_id": lid, "posting_date": d, "event": "held_in_suspense",
                            "cash_in": round(c, 2), "released_from_suspense": 0.0,
                            "fee_late": 0.0, "fee_nsf": 0.0, "fee_extension": 0.0,
                            "escrow_shortage_paid": 0.0, "interest_paid": 0.0,
                            "principal_paid": 0.0, "held_in_suspense": round(pending, 2),
                        })

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
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
