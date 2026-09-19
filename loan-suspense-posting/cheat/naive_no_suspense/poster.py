#!/usr/bin/env python3
"""Cheat / adversarial baseline: the most natural reading of the spec by a
competent engineer who does not model suspense/hold-until-full. Every
payment, whatever its size, is applied immediately through the waterfall.
A running per-cycle credit counter tracks whether the current cycle's
installment has been covered, without ever holding cash back."""
import argparse
import json

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

    breakdown = []
    for d in range(1, window_days + 1):
        for L in loans.values():
            L["interest"] += L["principal"] * L["rate"] / 365.0
        for L in loans.values():
            if d in L["disb"]:
                L["escrow"] -= L["disb"][d]

        cash_by_loan = {}
        for p in pay_by_day.get(d, []):
            cash_by_loan[p["loan_id"]] = cash_by_loan.get(p["loan_id"], 0.0) + p["amount"]

        for lid, L in loans.items():
            cash = cash_by_loan.get(lid, 0.0)
            if cash > 0:
                remaining = cash
                paid = {}
                for bucket in ("late", "nsf", "extension"):
                    pay = min(L["fees"][bucket], remaining)
                    L["fees"][bucket] -= pay
                    paid[bucket] = pay
                    remaining -= pay
                shortage = max(0.0, -L["escrow"])
                pay = min(shortage, remaining)
                L["escrow"] += pay
                paid["escrow_shortage"] = pay
                remaining -= pay
                pay = min(L["interest"], remaining)
                L["interest"] -= pay
                paid["interest"] = pay
                remaining -= pay
                L["credit"] += pay
                L["principal"] -= remaining
                L["credit"] += remaining
                paid["principal"] = remaining
                breakdown.append({
                    "loan_id": lid, "posting_date": d, "event": "release",
                    "cash_in": round(cash, 2), "released_from_suspense": 0.0,
                    "fee_late": round(paid["late"], 2), "fee_nsf": round(paid["nsf"], 2),
                    "fee_extension": round(paid["extension"], 2),
                    "escrow_shortage_paid": round(paid["escrow_shortage"], 2),
                    "interest_paid": round(paid["interest"], 2),
                    "principal_paid": round(paid["principal"], 2),
                    "held_in_suspense": 0.0,
                })

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
    return {"final_ledger": final, "payment_allocations": breakdown}


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
