#!/usr/bin/env python3
"""Cheat / adversarial baseline: implements the correct suspense/release
waterfall, but buckets each payment by its effective_date instead of its
posting_date -- a plausible mistake given the field is borrower-facing."""
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
            "interest": 0.0, "suspense": 0.0, "fee_charged": False,
        }

    pay_by_day = {}
    for p in payments_json:
        pay_by_day.setdefault(p["effective_date"], []).append(p)  # BUG: should key by posting_date

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
            pending = L["suspense"] + cash
            shortage = max(0.0, -L["escrow"])
            fees_sum = sum(L["fees"].values())
            required = fees_sum + shortage + L["installment"]

            if cash > 0 or L["suspense"] > 0:
                if pending + 1e-9 >= required:
                    remaining = pending
                    paid = {}
                    for bucket in ("late", "nsf", "extension"):
                        pay = min(L["fees"][bucket], remaining)
                        L["fees"][bucket] -= pay
                        paid[bucket] = pay
                        remaining -= pay
                    pay = min(shortage, remaining)
                    L["escrow"] += pay
                    paid["escrow_shortage"] = pay
                    remaining -= pay
                    pay = min(L["interest"], remaining)
                    L["interest"] -= pay
                    paid["interest"] = pay
                    remaining -= pay
                    paid["principal"] = remaining
                    L["principal"] -= remaining
                    released_from_susp = pending - cash
                    L["suspense"] = 0.0
                    L["due"] += CYCLE_DAYS
                    L["fee_charged"] = False
                    breakdown.append({
                        "loan_id": lid, "posting_date": d, "event": "release",
                        "cash_in": round(cash, 2),
                        "released_from_suspense": round(released_from_susp, 2),
                        "fee_late": round(paid["late"], 2), "fee_nsf": round(paid["nsf"], 2),
                        "fee_extension": round(paid["extension"], 2),
                        "escrow_shortage_paid": round(paid["escrow_shortage"], 2),
                        "interest_paid": round(paid["interest"], 2),
                        "principal_paid": round(paid["principal"], 2),
                        "held_in_suspense": 0.0,
                    })
                else:
                    L["suspense"] = pending
                    if cash > 0:
                        breakdown.append({
                            "loan_id": lid, "posting_date": d, "event": "held_in_suspense",
                            "cash_in": round(cash, 2), "released_from_suspense": 0.0,
                            "fee_late": 0.0, "fee_nsf": 0.0, "fee_extension": 0.0,
                            "escrow_shortage_paid": 0.0, "interest_paid": 0.0,
                            "principal_paid": 0.0, "held_in_suspense": round(pending, 2),
                        })

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
            "suspense_balance": round(L["suspense"], 2),
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
