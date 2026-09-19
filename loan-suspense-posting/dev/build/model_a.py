"""
Model A: day-major reference implementation of the servicing rules.
This becomes the basis for solution/poster.py (the reference solution).
See SERVICING_SPEC.md for the disclosed rules this implements.
"""
from dataclasses import dataclass, field

CYCLE_DAYS = 30
LATE_FEE_GRACE_DAYS = 15


@dataclass
class LoanState:
    loan_id: str
    annual_rate: float
    monthly_installment: float
    late_fee_amount: float
    first_due_day: int
    principal_balance: float
    escrow_balance: float
    fees_owed: dict
    disbursements: list  # [[day, amount], ...]

    accrued_interest: float = field(default=0.0)
    suspense_balance: float = field(default=0.0)
    next_due_date: int = field(init=False)
    late_fee_charged_for_cycle: bool = field(default=False)

    def __post_init__(self):
        self.next_due_date = self.first_due_day

    def fees_total(self):
        return sum(self.fees_owed.values())


def load_state(loan_json):
    return LoanState(
        loan_id=loan_json["loan_id"],
        annual_rate=loan_json["annual_rate"],
        monthly_installment=loan_json["monthly_installment"],
        late_fee_amount=loan_json["late_fee_amount"],
        first_due_day=loan_json["first_due_day"],
        principal_balance=loan_json["opening_principal"],
        escrow_balance=loan_json["opening_escrow"],
        fees_owed=dict(loan_json["opening_fees"]),
        disbursements=[tuple(x) for x in loan_json["disbursements"]],
    )


def run(loans_json, payments_json, window_days):
    loans = {lj["loan_id"]: load_state(lj) for lj in loans_json}

    pay_by_day = {}
    for p in payments_json:
        pay_by_day.setdefault(p["posting_date"], []).append(p)

    disb_by_day = {lid: dict(loan.disbursements) for lid, loan in loans.items()}

    breakdown = []

    for d in range(1, window_days + 1):
        for loan in loans.values():
            loan.accrued_interest += loan.principal_balance * loan.annual_rate / 365.0

        for lid, loan in loans.items():
            if d in disb_by_day[lid]:
                loan.escrow_balance -= disb_by_day[lid][d]

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
                    alloc = {"late": 0.0, "nsf": 0.0, "extension": 0.0,
                             "escrow_shortage": 0.0, "interest": 0.0, "principal": 0.0}
                    for bucket in ("late", "nsf", "extension"):
                        pay = min(loan.fees_owed[bucket], remaining)
                        loan.fees_owed[bucket] -= pay
                        alloc[bucket] = pay
                        remaining -= pay
                    pay = min(shortage, remaining)
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
                        "cash_in": round(c, 2), "released_from_suspense": round(pending - c, 2),
                        "fee_late": round(alloc["late"], 2), "fee_nsf": round(alloc["nsf"], 2),
                        "fee_extension": round(alloc["extension"], 2),
                        "escrow_shortage_paid": round(alloc["escrow_shortage"], 2),
                        "interest_paid": round(alloc["interest"], 2),
                        "principal_paid": round(alloc["principal"], 2),
                        "held_in_suspense": 0.0,
                    })
                else:
                    loan.suspense_balance = pending
                    if c > 0:
                        breakdown.append({
                            "loan_id": lid, "posting_date": d, "event": "held_in_suspense",
                            "cash_in": round(c, 2), "released_from_suspense": 0.0,
                            "fee_late": 0.0, "fee_nsf": 0.0, "fee_extension": 0.0,
                            "escrow_shortage_paid": 0.0, "interest_paid": 0.0, "principal_paid": 0.0,
                            "held_in_suspense": round(pending, 2),
                        })

            dpd = max(0, d - loan.next_due_date)
            if dpd > LATE_FEE_GRACE_DAYS and not loan.late_fee_charged_for_cycle:
                loan.fees_owed["late"] += loan.late_fee_amount
                loan.late_fee_charged_for_cycle = True

    final = {}
    for lid, loan in loans.items():
        dpd = max(0, window_days - loan.next_due_date)
        final[lid] = {
            "principal_balance": round(loan.principal_balance, 2),
            "accrued_interest": round(loan.accrued_interest, 2),
            "escrow_balance": round(loan.escrow_balance, 2),
            "fees_owed": {k: round(v, 2) for k, v in loan.fees_owed.items()},
            "suspense_balance": round(loan.suspense_balance, 2),
            "next_due_date": loan.next_due_date,
            "days_past_due": dpd,
        }
    return final, breakdown
