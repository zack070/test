"""
Adversarial baseline #1 (JSON-interface version, for final calibration
numbers): the most natural reading of the waterfall spec by a competent
engineer who does not model suspense/hold-until-full. Every payment,
whatever its size, is applied immediately through the waterfall. A running
per-cycle credit counter (interest+principal applied since the last due
date advance) is used to decide when to advance next_due_date -- a
plausible way to track "have they paid this cycle" without literally
holding cash back.
"""
CYCLE_DAYS = 30
GRACE = 15


def run(loans_json, payments_json, window_days):
    loans = {}
    for lj in loans_json:
        loans[lj["loan_id"]] = {
            "rate": lj["annual_rate"], "installment": lj["monthly_installment"],
            "late_fee": lj["late_fee_amount"], "due": lj["first_due_day"],
            "principal": lj["opening_principal"], "escrow": lj["opening_escrow"],
            "fees": dict(lj["opening_fees"]),
            "disb": {int(d): a for d, a in lj["disbursements"]},
            "interest": 0.0, "credit": 0.0, "fee_charged": False,
        }

    pay_by_day = {}
    for p in payments_json:
        pay_by_day.setdefault(p["posting_date"], []).append(p)

    for d in range(1, window_days + 1):
        for L in loans.values():
            L["interest"] += L["principal"] * L["rate"] / 365.0
        for lid, L in loans.items():
            if d in L["disb"]:
                L["escrow"] -= L["disb"][d]

        cash_by_loan = {}
        for p in pay_by_day.get(d, []):
            cash_by_loan[p["loan_id"]] = cash_by_loan.get(p["loan_id"], 0.0) + p["amount"]

        for lid, L in loans.items():
            cash = cash_by_loan.get(lid, 0.0)
            if cash > 0:
                remaining = cash
                for bucket in ("late", "nsf", "extension"):
                    pay = min(L["fees"][bucket], remaining)
                    L["fees"][bucket] -= pay
                    remaining -= pay
                shortage = max(0.0, -L["escrow"])
                pay = min(shortage, remaining)
                L["escrow"] += pay
                remaining -= pay
                pay = min(L["interest"], remaining)
                L["interest"] -= pay
                remaining -= pay
                L["credit"] += pay
                L["principal"] -= remaining
                L["credit"] += remaining

            if L["credit"] >= L["installment"] - 1e-9:
                L["due"] += CYCLE_DAYS
                L["credit"] = 0.0
                L["fee_charged"] = False

            dpd = max(0, d - L["due"])
            if dpd > GRACE and not L["fee_charged"]:
                L["fees"]["late"] += L["late_fee"]
                L["fee_charged"] = True

    final = {}
    for lid, L in loans.items():
        dpd = max(0, window_days - L["due"])
        final[lid] = {
            "principal_balance": round(L["principal"], 2),
            "accrued_interest": round(L["interest"], 2),
            "escrow_balance": round(L["escrow"], 2),
            "fees_owed": {k: round(v, 2) for k, v in L["fees"].items()},
            "suspense_balance": 0.0,
            "next_due_date": L["due"],
            "days_past_due": dpd,
        }
    return final
