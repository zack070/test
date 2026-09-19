import random

WINDOW_DAYS = 75
CYCLE_DAYS = 30

SCENARIO_COUNTS = {
    "disbursement_collision": 15,
    "chronic_underpay": 15,
    "partial_then_catchup": 15,
    "delinquent_then_recover": 15,
    "overpay_curtailment": 10,
    "always_full_ontime": 10,
}


def _installment(principal, annual_rate, term_months):
    r = annual_rate / 12.0
    return principal * r * (1 + r) ** term_months / ((1 + r) ** term_months - 1)


def make_portfolio(seed, n_loans=80, window_days=WINDOW_DAYS, id_offset=0):
    rng = random.Random(seed)
    scenarios = []
    for name, count in SCENARIO_COUNTS.items():
        scenarios += [name] * count
    assert len(scenarios) == n_loans
    rng.shuffle(scenarios)

    loans = []
    payments = []

    for i, scenario in enumerate(scenarios):
        lid = f"L{i + id_offset:03d}"
        annual_rate = round(rng.uniform(0.055, 0.11), 4)
        principal = round(rng.uniform(8000, 45000), 2)
        term_months = rng.choice([60, 84, 120, 180])
        installment = round(_installment(principal, annual_rate, term_months), 2)
        late_fee = rng.choice([25.00, 35.00, 50.00])
        first_due = rng.randint(3, CYCLE_DAYS)
        opening_escrow = round(rng.uniform(200, 1500), 2)
        opening_fees = {"late": 0.0, "nsf": 0.0, "extension": 0.0}
        if rng.random() < 0.15:
            opening_fees["late"] = late_fee

        n_disb = rng.choice([1, 2])
        disb_days = sorted(rng.sample(range(5, window_days - 5), n_disb))
        disb_total = opening_escrow * rng.uniform(0.6, 1.3)
        disbursements = [[day, round(disb_total / n_disb, 2)] for day in disb_days]

        loan_json = {
            "loan_id": lid, "annual_rate": annual_rate, "monthly_installment": installment,
            "late_fee_amount": late_fee, "first_due_day": first_due,
            "opening_principal": principal, "opening_escrow": opening_escrow,
            "opening_fees": opening_fees, "disbursements": disbursements,
        }
        loans.append(loan_json)

        due_days = list(range(first_due, window_days + CYCLE_DAYS, CYCLE_DAYS))
        due_days = [d for d in due_days if d <= window_days]

        if scenario == "always_full_ontime":
            for dd in due_days:
                payments.append(_pay(lid, dd, installment, rng))

        elif scenario == "chronic_underpay":
            for dd in due_days:
                amt = round(installment * rng.uniform(0.55, 0.8), 2)
                payments.append(_pay(lid, dd, amt, rng))

        elif scenario == "partial_then_catchup":
            for j, dd in enumerate(due_days):
                frac = 0.4 if j % 2 == 0 else 1.6
                payments.append(_pay(lid, dd, round(installment * frac, 2), rng))

        elif scenario == "delinquent_then_recover":
            for j, dd in enumerate(due_days):
                if j == 0:
                    continue
                payments.append(_pay(lid, dd, installment, rng))

        elif scenario == "overpay_curtailment":
            for dd in due_days:
                extra = round(rng.uniform(200, 2000), 2)
                payments.append(_pay(lid, dd, installment + extra, rng))

        elif scenario == "disbursement_collision":
            disb_day = disb_days[0]
            first_pay_day = max(1, disb_day - 10)
            payments.append(_pay(lid, first_pay_day, round(installment * 0.5, 2), rng))
            payments.append(_pay(lid, disb_day, round(installment * 0.5, 2), rng))
            # keep going with normal cycles after the forced collision
            for dd in due_days:
                if dd > disb_day + 5:
                    payments.append(_pay(lid, dd, installment, rng))

    payments.sort(key=lambda p: (p["posting_date"], p["loan_id"]))
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


def make_worked_example():
    """Tiny, fully hand-checkable case: 2 loans, 45-day window."""
    loans = [
        {
            "loan_id": "W001", "annual_rate": 0.08, "monthly_installment": 400.00,
            "late_fee_amount": 25.00, "first_due_day": 10,
            "opening_principal": 20000.00, "opening_escrow": 100.00,
            "opening_fees": {"late": 0.0, "nsf": 0.0, "extension": 0.0},
            "disbursements": [[20, 300.00]],
        },
        {
            "loan_id": "W002", "annual_rate": 0.06, "monthly_installment": 250.00,
            "late_fee_amount": 25.00, "first_due_day": 10,
            "opening_principal": 12000.00, "opening_escrow": 500.00,
            "opening_fees": {"late": 0.0, "nsf": 0.0, "extension": 0.0},
            "disbursements": [],
        },
    ]
    payments = [
        # W001: underpays, held in suspense day 10, then a second payment day 18
        # brings pool to enough to release. Disbursement on day 20 happens AFTER
        # the day-18 release, so it does not affect this cycle's threshold.
        {"loan_id": "W001", "posting_date": 10, "effective_date": 10, "amount": 150.00, "memo": ""},
        {"loan_id": "W001", "posting_date": 18, "effective_date": 18, "amount": 300.00, "memo": ""},
        # W002: pays full on time every cycle
        {"loan_id": "W002", "posting_date": 10, "effective_date": 10, "amount": 250.00, "memo": ""},
        {"loan_id": "W002", "posting_date": 40, "effective_date": 39, "amount": 250.00, "memo": ""},
    ]
    return loans, payments, 45
