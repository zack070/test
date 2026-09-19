"""
Model B: independently-structured (loan-major) implementation of the same
disclosed servicing rules, written without reusing model_a's code, to cross-
check for shared-bug risk before either is trusted as ground truth. Used to
compute the sealed reference answers (frozen once, at dev time).
"""
CYCLE_DAYS = 30
GRACE = 15


def _accrue(principal, rate):
    return principal * rate / 365.0


def run(loans_json, payments_json, window_days):
    final = {}
    all_breakdown = []

    payments_by_loan = {}
    for p in payments_json:
        payments_by_loan.setdefault(p["loan_id"], {}).setdefault(p["posting_date"], 0.0)
        payments_by_loan[p["loan_id"]][p["posting_date"]] += p["amount"]

    for lj in loans_json:
        lid = lj["loan_id"]
        rate = lj["annual_rate"]
        installment = lj["monthly_installment"]
        late_fee_amt = lj["late_fee_amount"]
        due = lj["first_due_day"]
        principal = lj["opening_principal"]
        escrow = lj["opening_escrow"]
        fees = dict(lj["opening_fees"])
        disb_map = {int(day): amt for day, amt in lj["disbursements"]}
        pay_map = payments_by_loan.get(lid, {})

        interest_accrued = 0.0
        suspense = 0.0
        cycle_fee_flag = False

        for day in range(1, window_days + 1):
            # per-diem always uses the balance carried into this day
            interest_accrued += _accrue(principal, rate)

            if day in disb_map:
                escrow = escrow - disb_map[day]

            cash = pay_map.get(day, 0.0)
            pool = suspense + cash

            shortfall = -escrow if escrow < 0 else 0.0
            fees_sum = fees["late"] + fees["nsf"] + fees["extension"]
            threshold = fees_sum + shortfall + installment

            posted_this_day = False
            if cash != 0.0 or suspense != 0.0:
                if pool >= threshold - 1e-9:
                    posted_this_day = True
                    left = pool
                    paid_late = min(fees["late"], left); fees["late"] -= paid_late; left -= paid_late
                    paid_nsf = min(fees["nsf"], left); fees["nsf"] -= paid_nsf; left -= paid_nsf
                    paid_ext = min(fees["extension"], left); fees["extension"] -= paid_ext; left -= paid_ext
                    paid_shortfall = min(shortfall, left)
                    escrow += paid_shortfall
                    left -= paid_shortfall
                    paid_interest = min(interest_accrued, left)
                    interest_accrued -= paid_interest
                    left -= paid_interest
                    paid_principal = left
                    principal -= paid_principal
                    suspense = 0.0
                    due += CYCLE_DAYS
                    cycle_fee_flag = False

                    all_breakdown.append({
                        "loan_id": lid, "posting_date": day, "event": "release",
                        "cash_in": round(cash, 2), "released_from_suspense": round(pool - cash, 2),
                        "fee_late": round(paid_late, 2), "fee_nsf": round(paid_nsf, 2),
                        "fee_extension": round(paid_ext, 2),
                        "escrow_shortage_paid": round(paid_shortfall, 2),
                        "interest_paid": round(paid_interest, 2),
                        "principal_paid": round(paid_principal, 2),
                        "held_in_suspense": 0.0,
                    })
                else:
                    suspense = pool
                    if cash != 0.0:
                        all_breakdown.append({
                            "loan_id": lid, "posting_date": day, "event": "held_in_suspense",
                            "cash_in": round(cash, 2), "released_from_suspense": 0.0,
                            "fee_late": 0.0, "fee_nsf": 0.0, "fee_extension": 0.0,
                            "escrow_shortage_paid": 0.0, "interest_paid": 0.0, "principal_paid": 0.0,
                            "held_in_suspense": round(pool, 2),
                        })

            days_late = day - due
            if days_late > GRACE and not cycle_fee_flag:
                fees["late"] += late_fee_amt
                cycle_fee_flag = True

        dpd_final = window_days - due
        if dpd_final < 0:
            dpd_final = 0

        final[lid] = {
            "principal_balance": round(principal, 2),
            "accrued_interest": round(interest_accrued, 2),
            "escrow_balance": round(escrow, 2),
            "fees_owed": {k: round(v, 2) for k, v in fees.items()},
            "suspense_balance": round(suspense, 2),
            "next_due_date": due,
            "days_past_due": dpd_final,
        }

    return final, all_breakdown
