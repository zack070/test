"""
Adversarial baseline #2: implements the CORRECT suspense/release/waterfall
mechanism exactly, but buckets each payment by its effective_date instead of
its posting_date (a plausible mistake: the field is borrower-facing and
"effective" sounds like it should govern effect). Isolates the value of the
posting-date-is-authoritative rule in isolation from the suspense mechanism.
"""
from model import CYCLE_DAYS, LATE_FEE_GRACE_DAYS


def run_naive_effdate(loans: dict, payments: list, window_days: int):
    pay_by_day = {}
    for p in payments:
        pay_by_day.setdefault(p["effective_date"], []).append(p)  # BUG: should be posting_date

    disb_by_day = {lid: {} for lid in loans}
    for lid, loan in loans.items():
        for day, amt in loan.disbursements:
            disb_by_day[lid][day] = amt

    for d in range(1, window_days + 1):
        for loan in loans.values():
            loan.accrued_interest += loan.principal_balance * loan.annual_rate / 365.0

        for lid, loan in loans.items():
            if d in disb_by_day[lid]:
                loan.escrow_balance -= disb_by_day[lid][d]

        todays = pay_by_day.get(d, [])
        pay_amt_by_loan = {}
        for p in todays:
            pay_amt_by_loan[p["loan_id"]] = pay_amt_by_loan.get(p["loan_id"], 0.0) + p["amount"]

        for lid, loan in loans.items():
            cash_today = pay_amt_by_loan.get(lid, 0.0)
            pending_cash = loan.suspense_balance + cash_today
            shortage_today = max(0.0, -loan.escrow_balance)
            required_today = loan.fees_total() + shortage_today + loan.monthly_installment

            if cash_today > 0 or loan.suspense_balance > 0:
                if pending_cash + 1e-9 >= required_today:
                    remaining = pending_cash
                    for bucket in ("late", "nsf", "extension"):
                        owe = loan.fees_owed[bucket]
                        pay = min(owe, remaining)
                        loan.fees_owed[bucket] -= pay
                        remaining -= pay
                    pay = min(shortage_today, remaining)
                    loan.escrow_balance += pay
                    remaining -= pay
                    pay = min(loan.accrued_interest, remaining)
                    loan.accrued_interest -= pay
                    remaining -= pay
                    loan.principal_balance -= remaining
                    loan.suspense_balance = 0.0
                    loan.next_due_date += CYCLE_DAYS
                    loan.late_fee_charged_for_cycle = False
                else:
                    loan.suspense_balance = pending_cash

            dpd = max(0, d - loan.next_due_date)
            if dpd > LATE_FEE_GRACE_DAYS and not loan.late_fee_charged_for_cycle:
                loan.fees_owed["late"] += loan.late_fee_amount
                loan.late_fee_charged_for_cycle = True

    final = {}
    for lid, loan in loans.items():
        dpd = max(0, window_days - loan.next_due_date)
        final[lid] = {
            "loan_id": lid,
            "principal_balance": round(loan.principal_balance, 2),
            "accrued_interest": round(loan.accrued_interest, 2),
            "escrow_balance": round(loan.escrow_balance, 2),
            "fees_owed": {k: round(v, 2) for k, v in loan.fees_owed.items()},
            "suspense_balance": round(loan.suspense_balance, 2),
            "next_due_date": loan.next_due_date,
            "days_past_due": dpd,
        }
    return final
