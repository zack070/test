"""Second spike: does the anti-abuse look-through rule need to be
re-evaluated PER PAYMENT DATE (because ownership stakes change over the
year), rather than once per payee, to get the right answer? This is the
concrete answer to the idea-checker's ask for "genuine reasoning" beyond
reading the rulebook carefully: a solver who has the look-through RULE
completely right can still get the WRONG classification if they apply
it once per payee instead of once per payment.

Look-through rule: to find the "relevant parent" of a payee for
anti-abuse purposes AS OF a given payment date, walk up the ownership
chain from the payee. At each step, if the immediate owner's stake in
the entity below it (as of that date) is > 50%, continue looking through
to that owner's own parent. The moment a stake is <= 50% (or there is no
further owner), STOP -- the entity at that level is the relevant parent
for that payment date. If the relevant parent's jurisdiction has no
treaty with the payer's jurisdiction, the treaty rate is denied
(statutory rate applies) regardless of the payee's own holding period.
"""

RATE_STATUTORY = 0.20
RATE_TREATY = 0.10

# Ownership chain: payee P is owned by Entity_M; the stake CHANGES mid-year.
# Entity_M is owned 100% by Entity_N (JUR_X, no treaty with payer).
# Entity_M itself is resident in JUR_A, which DOES have a treaty with the payer.
OWNERSHIP_HISTORY = [
    # (owner, owned_entity, stake_pct, effective_from, effective_to_exclusive)
    ("Entity_M", "Payee_P", 60, "2024-01-01", "2024-07-01"),
    ("Entity_M", "Payee_P", 40, "2024-07-01", "2025-01-01"),
    ("Entity_N", "Entity_M", 100, "2024-01-01", "2025-01-01"),
]
JURISDICTION = {"Entity_M": "JUR_A", "Entity_N": "JUR_X", "Payee_P": "JUR_PAYEE"}
TREATY_PARTNERS_OF_PAYER = {"JUR_A"}  # payer's jurisdiction has a treaty with JUR_A, not JUR_X

PAYMENTS = [
    ("PAY1", "Payee_P", 100_000.0, "2024-03-01", 400),  # during the 60% window
    ("PAY2", "Payee_P", 100_000.0, "2024-08-01", 400),  # during the 40% window
]


def stake_as_of(owner, owned, date):
    for o, e, pct, start, end in OWNERSHIP_HISTORY:
        if o == owner and e == owned and start <= date < end:
            return pct
    return None


def relevant_parent_as_of(payee, date):
    current = payee
    while True:
        owner = None
        for o, e, pct, start, end in OWNERSHIP_HISTORY:
            if e == current and start <= date < end:
                owner = o
                stake = pct
                break
        if owner is None:
            return current  # no further owner on record
        if stake > 50:
            current = owner  # look through, keep climbing
            continue
        return owner  # stake <= 50%: STOP here, this is the relevant parent


def rate_naive_once_per_payee(payee, date, holding_days):
    # Naive-but-plausible: resolve the "relevant parent" ONCE for the
    # payee (using, say, the first payment's date, or year start) and
    # reuse it for every payment -- a reasonable-looking shortcut if you
    # don't notice the rule says "as of" the payment date specifically.
    parent = relevant_parent_as_of(payee, "2024-01-01")
    parent_jur = JURISDICTION.get(parent, parent)
    if parent_jur not in TREATY_PARTNERS_OF_PAYER:
        return RATE_STATUTORY
    return RATE_TREATY if holding_days >= 365 else RATE_STATUTORY


def rate_correct_per_payment(payee, date, holding_days):
    parent = relevant_parent_as_of(payee, date)
    parent_jur = JURISDICTION.get(parent, parent)
    if parent_jur not in TREATY_PARTNERS_OF_PAYER:
        return RATE_STATUTORY
    return RATE_TREATY if holding_days >= 365 else RATE_STATUTORY


if __name__ == "__main__":
    naive_total = 0.0
    correct_total = 0.0
    for pid, payee, amount, date, holding_days in PAYMENTS:
        rn = rate_naive_once_per_payee(payee, date, holding_days)
        rc = rate_correct_per_payment(payee, date, holding_days)
        naive_total += amount * rn
        correct_total += amount * rc
        print(f"{pid} on {date}: naive_rate={rn:.0%} correct_rate={rc:.0%} "
              f"{'MATCH' if rn == rc else 'DIVERGE'}")
    print(f"\nnaive total:   {naive_total:,.2f}")
    print(f"correct total: {correct_total:,.2f}")
    print(f"difference: {correct_total - naive_total:,.2f} "
          f"({'MATCH -- no tension' if abs(correct_total-naive_total) < 1e-6 else 'DIVERGES -- genuine per-date reasoning required'})")
