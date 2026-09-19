"""
Canonical reference implementation of the loan-suspense-posting servicing
state machine. This encodes the EXACT rules that will go into the disclosed
spec (environment/SERVICING_SPEC.md). Spike purpose: prove the mechanism
before building the full bundle.

Rules (all fully disclosed to the agent in the real task):

1. Calendar: the window is days 1..WINDOW_DAYS (no real calendar dates -
   avoids month-length trivia). Due dates recur every CYCLE_DAYS days
   starting at first_due_day.

2. Accrual: every day d, for every loan, before anything else:
     accrued_interest += principal_balance_entering_day_d * annual_rate / 365
   principal_balance_entering_day_d is the balance as it stood at the END
   of day d-1 (i.e. any curtailment posted on day d-1 already lowers day d's
   accrual; a curtailment posted ON day d does not lower day d's own accrual,
   only day d+1's). This is the single per-diem rule; there is no separate
   "recompute" step.

3. posting_date is authoritative for every computation (accrual-through,
   release test, delinquency). effective_date and memo are informational
   only and must never influence any computed value.

4. Escrow: each loan has a fixed list of scheduled disbursements
   (day, amount), fully known in advance. On the scheduled day, BEFORE the
   release test, escrow_balance -= amount (can go negative -> shortage).
   escrow_shortage_today = max(0, -escrow_balance) after applying any
   disbursement scheduled for today.

5. Suspense / release test: pending_cash = suspense_balance_entering_day
   + (today's payment amount, if a payment posts today for this loan).
   required_today = fees_owed_total + escrow_shortage_today
                     + monthly_installment (fixed P&I figure)
   If pending_cash >= required_today: RELEASE. The entire pending_cash is
   posted today via the waterfall (fees, then escrow shortage, then
   interest-in-full, then principal -- excess beyond required_today is a
   curtailment). suspense_balance becomes 0. next_due_date advances by
   exactly one CYCLE_DAYS (regardless of how large the excess was -- a
   release only ever clears one cycle). late_fee_charged_for_cycle resets
   to False for the new cycle.
   If pending_cash < required_today: nothing posts. suspense_balance_end =
   pending_cash. No waterfall entries for this loan today.

6. Waterfall order on a release day: (a) fees_owed, in order
   late -> nsf -> extension, paid in full (all included in required_today,
   so always fully clearable); (b) escrow shortage, paid in full; (c)
   accrued_interest, paid in full; (d) remainder -> principal (curtailment).

7. Delinquency: days_past_due(d) = max(0, d - next_due_date). This is a
   pure function of the current day and the loan's current next_due_date;
   no separate stored status.

8. Late fee: if days_past_due(d) > LATE_FEE_GRACE_DAYS and
   late_fee_charged_for_cycle is False, assess late_fee_amount into
   fees_owed['late'] and set late_fee_charged_for_cycle = True. This can
   only ever fire once per (loan, due-date cycle) because next_due_date
   cannot advance without a release, and a release resets the flag for the
   NEW cycle only.
"""
from dataclasses import dataclass, field
from typing import Optional

CYCLE_DAYS = 30
LATE_FEE_GRACE_DAYS = 15


@dataclass
class Loan:
    loan_id: str
    annual_rate: float
    monthly_installment: float
    late_fee_amount: float
    first_due_day: int
    opening_principal: float
    opening_escrow: float
    opening_fees: dict  # {"late":0,"nsf":0,"extension":0}
    disbursements: list  # [(day, amount), ...]

    # mutable state
    principal_balance: float = field(init=False)
    escrow_balance: float = field(init=False)
    accrued_interest: float = field(init=False, default=0.0)
    fees_owed: dict = field(init=False)
    suspense_balance: float = field(init=False, default=0.0)
    next_due_date: int = field(init=False)
    late_fee_charged_for_cycle: bool = field(init=False, default=False)

    def __post_init__(self):
        self.principal_balance = self.opening_principal
        self.escrow_balance = self.opening_escrow
        self.fees_owed = dict(self.opening_fees)
        self.next_due_date = self.first_due_day

    def fees_total(self):
        return sum(self.fees_owed.values())


def run_reference(loans: dict, payments: list, window_days: int, trace=False):
    """
    loans: dict loan_id -> Loan
    payments: list of dicts {loan_id, effective_date, posting_date, amount, memo}
              (effective_date, memo are IGNORED by this reference on purpose)
    Returns: (final_state per loan, per_payment_breakdown list, daily_suspense_trace)
    """
    pay_by_day = {}
    for p in payments:
        pay_by_day.setdefault(p["posting_date"], []).append(p)

    disb_by_day = {lid: {} for lid in loans}
    for lid, loan in loans.items():
        for day, amt in loan.disbursements:
            disb_by_day[lid][day] = amt

    breakdown = []
    suspense_trace = {lid: {} for lid in loans}

    for d in range(1, window_days + 1):
        # 1. accrual using balance entering day d (i.e. balance as of end of d-1)
        for loan in loans.values():
            loan.accrued_interest += loan.principal_balance * loan.annual_rate / 365.0

        # 2. escrow disbursement for today (before release test)
        for lid, loan in loans.items():
            if d in disb_by_day[lid]:
                loan.escrow_balance -= disb_by_day[lid][d]

        todays_payments = pay_by_day.get(d, [])
        pay_amt_by_loan = {}
        for p in todays_payments:
            pay_amt_by_loan[p["loan_id"]] = pay_amt_by_loan.get(p["loan_id"], 0.0) + p["amount"]

        for lid, loan in loans.items():
            cash_today = pay_amt_by_loan.get(lid, 0.0)
            pending_cash = loan.suspense_balance + cash_today

            shortage_today = max(0.0, -loan.escrow_balance)
            required_today = loan.fees_total() + shortage_today + loan.monthly_installment

            if cash_today > 0 or loan.suspense_balance > 0:
                if pending_cash + 1e-9 >= required_today:
                    # RELEASE
                    alloc = {"late": 0.0, "nsf": 0.0, "extension": 0.0,
                             "escrow_shortage": 0.0, "interest": 0.0, "principal": 0.0,
                             "held_in_suspense": 0.0}
                    remaining = pending_cash
                    for bucket in ("late", "nsf", "extension"):
                        owe = loan.fees_owed[bucket]
                        pay = min(owe, remaining)
                        loan.fees_owed[bucket] -= pay
                        alloc[bucket] = pay
                        remaining -= pay
                    pay = min(shortage_today, remaining)
                    loan.escrow_balance += pay
                    alloc["escrow_shortage"] = pay
                    remaining -= pay
                    pay = min(loan.accrued_interest, remaining)
                    loan.accrued_interest -= pay
                    alloc["interest"] = pay
                    remaining -= pay
                    alloc["principal"] = remaining
                    loan.principal_balance -= remaining
                    loan.suspense_balance = 0.0

                    loan.next_due_date += CYCLE_DAYS
                    loan.late_fee_charged_for_cycle = False

                    breakdown.append({
                        "loan_id": lid, "posting_date": d, "event": "release",
                        "cash_in": cash_today, "from_suspense": pending_cash - cash_today,
                        **alloc,
                    })
                else:
                    loan.suspense_balance = pending_cash
                    if cash_today > 0:
                        breakdown.append({
                            "loan_id": lid, "posting_date": d, "event": "held_in_suspense",
                            "cash_in": cash_today, "from_suspense": loan.suspense_balance - cash_today,
                            "late": 0.0, "nsf": 0.0, "extension": 0.0,
                            "escrow_shortage": 0.0, "interest": 0.0, "principal": 0.0,
                            "held_in_suspense": pending_cash,
                        })

            # delinquency / late fee, evaluated AFTER today's release attempt
            dpd = max(0, d - loan.next_due_date)
            if dpd > LATE_FEE_GRACE_DAYS and not loan.late_fee_charged_for_cycle:
                loan.fees_owed["late"] += loan.late_fee_amount
                loan.late_fee_charged_for_cycle = True

            if trace:
                suspense_trace[lid][d] = loan.suspense_balance

    final = {}
    for lid, loan in loans.items():
        dpd = max(0, window_days - loan.next_due_date) if window_days >= loan.next_due_date else 0
        # recompute dpd cleanly at final day using same rule as loop
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
    return final, breakdown, suspense_trace
