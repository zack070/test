"""Naive/plausible-but-wrong probes, measured against full generated
scenarios (not just isolated toy cases) to confirm both traps create
real, robust divergence once embedded -- mirroring the discipline used
on the sibling field-service-dispatch/cash-sweep bundles: measure, don't
assume, that greedy-shaped shortcuts actually fail.
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_engine as eng  # noqa: E402


def _round2(x):
    import decimal
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def naive_once_per_payee_parent(sc: eng.ScenarioData):
    """Resolves each payee's relevant parent ONCE (as of Jan 1 of the
    scenario year) and reuses it for every payment, instead of per
    payment date."""
    year = sc.payments[0].payment_date.year if sc.payments else 2024
    jan1 = date(year, 1, 1)
    parent_cache = {}

    def parent_of(payee):
        if payee not in parent_cache:
            parent_cache[payee] = eng.relevant_parent(sc, payee, jan1)
        return parent_cache[payee]

    lines = []
    total = 0.0
    running = {}
    base = {}
    for p in sc.payments:
        parent = parent_of(p.payee)
        parent_jur = sc.entities.get(parent, parent)
        treaty_rate = sc.treaty_partners.get(parent_jur)
        rate = treaty_rate if (treaty_rate is not None and eng.holding_days(p) >= sc.holding_period_days) else sc.statutory_rate
        usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
        base[p.payment_id] = (rate, usd)
        key = (p.payee, p.payment_date.year)
        running[key] = running.get(key, 0.0) + usd
    breached = {k for k, v in running.items() if v > sc.threshold_usd}
    for p in sc.payments:
        rate, usd = base[p.payment_id]
        key = (p.payee, p.payment_date.year)
        final_rate = sc.statutory_rate if key in breached else rate
        total += usd * final_rate
    return _round2(total)


def naive_no_retroactive_threshold(sc: eng.ScenarioData):
    """Computes each payment's rate correctly (per-date look-through)
    but never applies the cumulative-threshold retroactive re-rating."""
    total = 0.0
    for p in sc.payments:
        rate, _ = eng.base_rate_for_payment(sc, p)
        usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
        total += usd * rate
    return _round2(total)


def naive_both(sc: eng.ScenarioData):
    year = sc.payments[0].payment_date.year if sc.payments else 2024
    jan1 = date(year, 1, 1)
    parent_cache = {}

    def parent_of(payee):
        if payee not in parent_cache:
            parent_cache[payee] = eng.relevant_parent(sc, payee, jan1)
        return parent_cache[payee]

    total = 0.0
    for p in sc.payments:
        parent = parent_of(p.payee)
        parent_jur = sc.entities.get(parent, parent)
        treaty_rate = sc.treaty_partners.get(parent_jur)
        rate = treaty_rate if (treaty_rate is not None and eng.holding_days(p) >= sc.holding_period_days) else sc.statutory_rate
        usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
        total += usd * rate
    return _round2(total)


def naive_always_statutory(sc: eng.ScenarioData):
    total = 0.0
    for p in sc.payments:
        usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
        total += usd * sc.statutory_rate
    return _round2(total)


def naive_always_treaty_if_any_partner_reachable(sc: eng.ScenarioData):
    """Applies the best-available treaty rate to every payment
    regardless of holding period or look-through, i.e. ignores the
    conditions entirely -- a constant-strategy-style shortcut."""
    best_rate = min(sc.treaty_partners.values()) if sc.treaty_partners else sc.statutory_rate
    total = 0.0
    for p in sc.payments:
        usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
        total += usd * best_rate
    return _round2(total)


PROBES = {
    "naive_once_per_payee_parent": naive_once_per_payee_parent,
    "naive_no_retroactive_threshold": naive_no_retroactive_threshold,
    "naive_both": naive_both,
    "naive_always_statutory": naive_always_statutory,
    "naive_always_best_treaty": naive_always_treaty_if_any_partner_reachable,
}
