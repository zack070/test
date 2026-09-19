"""
Adversarial baseline #1: the most natural 'obvious' reading of the waterfall
spec by a competent engineer who does NOT model suspense/hold-until-full.
Every payment, whatever its size, is applied immediately through the
waterfall (fees -> escrow shortage -> interest -> principal). The engineer
still tracks "how much has been applied toward the current cycle's required
installment" and advances next_due_date once that running total reaches the
installment amount -- a plausible, not-stupid way to handle "did they pay
this cycle" without literally holding cash back. This isolates exactly the
value of the suspense/hold mechanism.
"""
from model import Loan, CYCLE_DAYS, LATE_FEE_GRACE_DAYS


def run_naive_immediate(loans: dict, payments: list, window_days: int):
    pay_by_day = {}
    for p in payments:
        pay_by_day.setdefault(p["posting_date"], []).append(p)

    disb_by_day = {lid: {} for lid in loans}
    for lid, loan in loans.items():
        for day, amt in loan.disbursements:
            disb_by_day[lid][day] = amt

    cycle_credit = {lid: 0.0 for lid in loans}  # applied toward interest+principal this cycle
    late_fee_charged = {lid: False for lid in loans}

    for d in range(1, window_days + 1):
        for loan in loans.values():
            loan.accrued_interest += loan.principal_balance * loan.annual_rate / 365.0

        for lid, loan in loans.items():
            if d in disb_by_day[lid]:
                loan.escrow_balance -= disb_by_day[lid][d]

        todays = [p for p in pay_by_day.get(d, [])]
        pay_amt_by_loan = {}
        for p in todays:
            pay_amt_by_loan[p["loan_id"]] = pay_amt_by_loan.get(p["loan_id"], 0.0) + p["amount"]

        for lid, loan in loans.items():
            cash = pay_amt_by_loan.get(lid, 0.0)
            if cash > 0:
                remaining = cash
                for bucket in ("late", "nsf", "extension"):
                    owe = loan.fees_owed[bucket]
                    pay = min(owe, remaining)
                    loan.fees_owed[bucket] -= pay
                    remaining -= pay
                shortage = max(0.0, -loan.escrow_balance)
                pay = min(shortage, remaining)
                loan.escrow_balance += pay
                remaining -= pay
                pay = min(loan.accrued_interest, remaining)
                loan.accrued_interest -= pay
                remaining -= pay
                cycle_credit[lid] += pay  # interest portion applied this cycle
                loan.principal_balance -= remaining
                cycle_credit[lid] += remaining  # principal portion applied this cycle

            if cycle_credit[lid] >= loan.monthly_installment - 1e-9:
                loan.next_due_date += CYCLE_DAYS
                cycle_credit[lid] = 0.0
                late_fee_charged[lid] = False

            dpd = max(0, d - loan.next_due_date)
            if dpd > LATE_FEE_GRACE_DAYS and not late_fee_charged[lid]:
                loan.fees_owed["late"] += loan.late_fee_amount
                late_fee_charged[lid] = True

    final = {}
    for lid, loan in loans.items():
        dpd = max(0, window_days - loan.next_due_date)
        final[lid] = {
            "loan_id": lid,
            "principal_balance": round(loan.principal_balance, 2),
            "accrued_interest": round(loan.accrued_interest, 2),
            "escrow_balance": round(loan.escrow_balance, 2),
            "fees_owed": {k: round(v, 2) for k, v in loan.fees_owed.items()},
            "suspense_balance": 0.0,
            "next_due_date": loan.next_due_date,
            "days_past_due": dpd,
        }
    return final
