import random
from model import Loan, CYCLE_DAYS

WINDOW_DAYS = 75


def make_portfolio(n_loans=24, seed=1234):
    rng = random.Random(seed)
    loans = {}
    payments = []

    for i in range(n_loans):
        lid = f"L{i:03d}"
        annual_rate = round(rng.uniform(0.055, 0.11), 4)
        principal = round(rng.uniform(8000, 45000), 2)
        # rough monthly P&I for a 5-15yr amortization, doesn't need to be exact
        term_months = rng.choice([60, 84, 120, 180])
        r = annual_rate / 12.0
        installment = principal * r * (1 + r) ** term_months / ((1 + r) ** term_months - 1)
        installment = round(installment, 2)
        late_fee = rng.choice([25.00, 35.00, 50.00])
        first_due = rng.randint(3, CYCLE_DAYS)
        opening_escrow = round(rng.uniform(200, 1500), 2)
        opening_fees = {"late": 0.0, "nsf": 0.0, "extension": 0.0}

        scenario = rng.choice([
            "always_full_ontime",
            "chronic_underpay",
            "partial_then_catchup",
            "delinquent_then_recover",
            "overpay_curtailment",
            "disbursement_collision",
        ])

        disbursements = []
        # every loan gets 1-2 escrow disbursements somewhere in the window
        n_disb = rng.choice([1, 2])
        disb_days = sorted(rng.sample(range(5, WINDOW_DAYS - 5), n_disb))
        disb_amt_total = opening_escrow * rng.uniform(0.6, 1.3)
        for k, day in enumerate(disb_days):
            disbursements.append((day, round(disb_amt_total / n_disb, 2)))

        loan = Loan(
            loan_id=lid, annual_rate=annual_rate, monthly_installment=installment,
            late_fee_amount=late_fee, first_due_day=first_due,
            opening_principal=principal, opening_escrow=opening_escrow,
            opening_fees=opening_fees, disbursements=disbursements,
        )
        loans[lid] = loan

        due_days = list(range(first_due, WINDOW_DAYS + CYCLE_DAYS, CYCLE_DAYS))

        if scenario == "always_full_ontime":
            for dd in due_days:
                if dd > WINDOW_DAYS:
                    continue
                payments.append(_pay(lid, dd, installment, rng))

        elif scenario == "chronic_underpay":
            # pays ~70% of installment each cycle -> accumulates in suspense,
            # eventually crosses threshold every 2nd or 3rd cycle
            for dd in due_days:
                if dd > WINDOW_DAYS:
                    continue
                amt = round(installment * rng.uniform(0.55, 0.8), 2)
                payments.append(_pay(lid, dd, amt, rng))

        elif scenario == "partial_then_catchup":
            for j, dd in enumerate(due_days):
                if dd > WINDOW_DAYS:
                    continue
                if j % 2 == 0:
                    payments.append(_pay(lid, dd, round(installment * 0.4, 2), rng))
                else:
                    payments.append(_pay(lid, dd, round(installment * 1.6, 2), rng))

        elif scenario == "delinquent_then_recover":
            for j, dd in enumerate(due_days):
                if dd > WINDOW_DAYS:
                    continue
                if j == 0:
                    continue  # skip first cycle entirely -> triggers late fee
                payments.append(_pay(lid, dd, installment, rng))

        elif scenario == "overpay_curtailment":
            for dd in due_days:
                if dd > WINDOW_DAYS:
                    continue
                extra = round(rng.uniform(200, 2000), 2)
                payments.append(_pay(lid, dd, installment + extra, rng))

        elif scenario == "disbursement_collision":
            # force: a payment's release-crossing day lands exactly on a
            # scheduled disbursement day. Two small payments; the second
            # exactly on a disbursement day, sized to just barely clear
            # (pre-disbursement) so the disbursement-caused shortage is the
            # deciding factor in whether release happens that day.
            disb_day = disb_days[0]
            first_pay_day = max(1, disb_day - 10)
            payments.append(_pay(lid, first_pay_day, round(installment * 0.5, 2), rng))
            # second payment lands ON the disbursement day
            payments.append(_pay(lid, disb_day, round(installment * 0.5, 2), rng))

        opening_fees_choice = rng.random()
        if opening_fees_choice < 0.15:
            loan.opening_fees["late"] = late_fee
            loan.fees_owed["late"] = late_fee

    return loans, payments


def _pay(loan_id, posting_date, amount, rng):
    eff = posting_date - rng.choice([0, 0, 0, 1, 2, 3])
    memo = rng.choice([
        "", "", "please apply to principal", "escrow catch-up", "extra to principal please",
    ])
    return {
        "loan_id": loan_id, "posting_date": posting_date,
        "effective_date": max(1, eff), "amount": round(amount, 2), "memo": memo,
    }
