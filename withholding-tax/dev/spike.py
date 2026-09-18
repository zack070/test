"""Fast validation spike: does a genuinely careless-but-plausible
computation diverge from the correct one under a small set of
interacting withholding-tax rules? No simulator, no online decide()
loop -- this is a pure batch computation over a fixed transaction list,
checked against a hand-verified correct total.

Rules (deliberately small, just enough to create real rule-interaction
tension):
  1. Statutory withholding rate on cross-border interest/royalty
     payments: 20%.
  2. A tax treaty between the payer and payee jurisdictions can reduce
     this to a treaty rate, but ONLY if the payee has held the
     underlying instrument for >= 365 days as of the payment date
     (the "holding period test").
  3. Anti-abuse override: if the payee's ultimate parent is resident in
     a THIRD jurisdiction that has no treaty with the payer jurisdiction
     at all (treaty shopping), the treaty rate is denied regardless of
     the holding period, and statutory rate applies.
  4. Cumulative annual threshold: once total payments (converted to a
     single reporting currency at each payment's own spot rate) to one
     payee in a calendar year exceed $500,000, ALL of that payee's
     payments for the year -- including ones already paid at a lower
     rate -- are retroactively subject to statutory rate, and the
     shortfall is owed as a true-up.

A "naive" implementation computes each payment's withholding using only
that payment's own facts, in the order given, and never revisits an
earlier payment once computed -- exactly what a careless-but-competent
first pass at "compute withholding per row" would do.
"""

RATE_STATUTORY = 0.20
RATE_TREATY = 0.10
THRESHOLD = 500_000.0

# (payee_id, ultimate_parent_jurisdiction, has_treaty_with_payer)
PAYEES = {
    "P1": {"parent_jur": "JUR_A", "parent_has_treaty": True},   # legitimate treaty claim
    "P2": {"parent_jur": "JUR_X", "parent_has_treaty": False},  # treaty-shopping case
}

# (payment_id, payee, amount_usd, holding_days_at_payment, order)
PAYMENTS = [
    ("T1", "P1", 200_000.0, 400),   # qualifies for treaty rate on its own facts
    ("T2", "P1", 200_000.0, 400),   # qualifies on its own facts
    ("T3", "P1", 200_000.0, 400),   # cumulative for P1 now 600k > threshold -> retroactive statutory on ALL of P1's payments
    ("T4", "P2", 300_000.0, 400),   # holding period satisfied, but anti-abuse denies treaty regardless
]


def naive_compute():
    total = 0.0
    for pid, payee, amount, holding_days in PAYMENTS:
        info = PAYEES[payee]
        if holding_days >= 365 and info["parent_has_treaty"]:
            rate = RATE_TREATY
        else:
            rate = RATE_STATUTORY
        total += amount * rate
    return total


def correct_compute():
    # Pass 1: naive per-payment rate, respecting the anti-abuse override
    # but NOT yet the cumulative threshold.
    per_payment_rate = {}
    for pid, payee, amount, holding_days in PAYMENTS:
        info = PAYEES[payee]
        if holding_days >= 365 and info["parent_has_treaty"]:
            per_payment_rate[pid] = RATE_TREATY
        else:
            per_payment_rate[pid] = RATE_STATUTORY

    # Pass 2: cumulative threshold check per payee, in payment order;
    # once a payee's running total exceeds THRESHOLD, EVERY payment for
    # that payee this year (including earlier ones already computed at
    # the treaty rate) is retroactively re-rated to statutory.
    running = {}
    breached = set()
    for pid, payee, amount, holding_days in PAYMENTS:
        running[payee] = running.get(payee, 0.0) + amount
        if running[payee] > THRESHOLD:
            breached.add(payee)

    total = 0.0
    for pid, payee, amount, holding_days in PAYMENTS:
        rate = RATE_STATUTORY if payee in breached else per_payment_rate[pid]
        total += amount * rate
    return total


if __name__ == "__main__":
    n = naive_compute()
    c = correct_compute()
    print(f"naive total withholding:   {n:,.2f}")
    print(f"correct total withholding: {c:,.2f}")
    print(f"difference: {c - n:,.2f} ({'MATCH -- no tension' if abs(c-n) < 1e-6 else 'DIVERGES -- real rule-interaction trap'})")
