"""Ablation checks: for each boundary convention in the rulebook, compute
the total under the most plausible ALTERNATE reading of that one
convention (everything else correct) and confirm it misses the true
total by a clear margin. This is the identifiability proof the idea
checker asked for explicitly -- not just the two headline traps, every
boundary a solver could plausibly read differently.
"""
import sys
import os
import decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_engine as eng  # noqa: E402


def _round2(x):
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def _relevant_parent_alt_tiebreak(sc, entity, on_date, _depth=0):
    """ALTERNATE reading: a stake of exactly 50% ALSO continues the
    look-through (>= 50 continues, not > 50). Correct rule: exactly 50%
    stops at that owner."""
    if _depth > len(sc.entities) + 2:
        raise RuntimeError("cycle")
    owner_record = None
    for rec in sc.ownership:
        if rec.owned == entity and rec.effective_from <= on_date < rec.effective_to:
            owner_record = rec
            break
    if owner_record is None:
        return entity
    if owner_record.stake_pct >= 50:  # <-- the one changed line
        return _relevant_parent_alt_tiebreak(sc, owner_record.owner, on_date, _depth + 1)
    return owner_record.owner


def alt_stake_tiebreak(sc: eng.ScenarioData) -> float:
    def rate_fn(p):
        parent = _relevant_parent_alt_tiebreak(sc, p.payee, p.payment_date)
        parent_jur = sc.entities.get(parent, parent)
        treaty_rate = sc.treaty_partners.get(parent_jur)
        if treaty_rate is not None and eng.holding_days(p) >= sc.holding_period_days:
            return treaty_rate
        return sc.statutory_rate
    return _apply_threshold_and_total(sc, rate_fn)


def alt_holding_period_strict(sc: eng.ScenarioData) -> float:
    """ALTERNATE reading: holding period test requires STRICTLY more
    than 365 days (> 365), not >= 365. Correct rule: exactly 365
    qualifies."""
    def rate_fn(p):
        parent = eng.relevant_parent(sc, p.payee, p.payment_date)
        parent_jur = sc.entities.get(parent, parent)
        treaty_rate = sc.treaty_partners.get(parent_jur)
        if treaty_rate is not None and eng.holding_days(p) > sc.holding_period_days:  # <-- changed
            return treaty_rate
        return sc.statutory_rate
    return _apply_threshold_and_total(sc, rate_fn)


def alt_threshold_inclusive(sc: eng.ScenarioData) -> float:
    """ALTERNATE reading: a cumulative total EQUAL to the threshold also
    triggers retroactive re-rating (>= threshold), not just strictly
    greater than."""
    usd_amount = {}
    base_rate = {}
    for p in sc.payments:
        rate, _ = eng.base_rate_for_payment(sc, p)
        base_rate[p.payment_id] = rate
        usd_amount[p.payment_id] = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
    running = {}
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        running[key] = running.get(key, 0.0) + usd_amount[p.payment_id]
    breached = {k for k, v in running.items() if v >= sc.threshold_usd}  # <-- changed
    total = 0.0
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        rate = sc.statutory_rate if key in breached else base_rate[p.payment_id]
        total += usd_amount[p.payment_id] * rate
    return _round2(total)


def alt_fx_fixed_january(sc: eng.ScenarioData) -> float:
    """ALTERNATE reading: use January's rate for every payment all year,
    instead of the rate for the payment's own month."""
    def rate_fn(p):
        rate, _ = eng.base_rate_for_payment(sc, p)
        return rate
    usd_amount = {}
    base_rate = {}
    for p in sc.payments:
        base_rate[p.payment_id] = rate_fn(p)
        usd_amount[p.payment_id] = p.amount * sc.fx_rates[(p.currency, p.payment_date.year, 1)]  # <-- always January
    running = {}
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        running[key] = running.get(key, 0.0) + usd_amount[p.payment_id]
    breached = {k for k, v in running.items() if v > sc.threshold_usd}
    total = 0.0
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        rate = sc.statutory_rate if key in breached else base_rate[p.payment_id]
        total += usd_amount[p.payment_id] * rate
    return _round2(total)


def alt_round_intermediate(sc: eng.ScenarioData) -> float:
    """ALTERNATE reading: round the USD-converted amount to 2 decimals
    BEFORE applying the rate (an intermediate rounding step), instead of
    only rounding the final reported figures."""
    def rate_fn(p):
        rate, _ = eng.base_rate_for_payment(sc, p)
        return rate
    usd_amount = {}
    base_rate = {}
    for p in sc.payments:
        base_rate[p.payment_id] = rate_fn(p)
        usd_amount[p.payment_id] = _round2(p.amount * eng.fx_rate(sc, p.currency, p.payment_date))  # <-- rounded early
    running = {}
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        running[key] = running.get(key, 0.0) + usd_amount[p.payment_id]
    breached = {k for k, v in running.items() if v > sc.threshold_usd}
    total = 0.0
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        rate = sc.statutory_rate if key in breached else base_rate[p.payment_id]
        total += usd_amount[p.payment_id] * rate  # note: rate applied to an already-rounded amount
    return _round2(total)


def _apply_threshold_and_total(sc, rate_fn) -> float:
    usd_amount = {}
    base_rate = {}
    for p in sc.payments:
        base_rate[p.payment_id] = rate_fn(p)
        usd_amount[p.payment_id] = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
    running = {}
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        running[key] = running.get(key, 0.0) + usd_amount[p.payment_id]
    breached = {k for k, v in running.items() if v > sc.threshold_usd}
    total = 0.0
    for p in sc.payments:
        key = (p.payee, p.payment_date.year)
        rate = sc.statutory_rate if key in breached else base_rate[p.payment_id]
        total += usd_amount[p.payment_id] * rate
    return _round2(total)


ABLATIONS = {
    "stake_tiebreak_inclusive (>=50 continues, not >50)": alt_stake_tiebreak,
    "holding_period_strict (>365, not >=365)": alt_holding_period_strict,
    "threshold_inclusive (>=threshold, not >threshold)": alt_threshold_inclusive,
    "fx_fixed_january (not payment's own month)": alt_fx_fixed_january,
    "round_intermediate (round before applying rate)": alt_round_intermediate,
}


if __name__ == "__main__":
    for data_dir in sys.argv[1:]:
        sc = eng.load_scenario(data_dir)
        correct = eng.compute_report(sc)["total_liability_usd"]
        print(f"\n=== {data_dir}: correct={correct:,.2f} ===")
        for name, fn in ABLATIONS.items():
            val = fn(sc)
            diff = val - correct
            print(f"  {name:55s} {val:12,.2f}  (diff {diff:+,.2f})")
