"""Shared probe policies for calibrating cash-sweep pass bars.

Mirrors the adversarial-sweep discipline used for field-service-dispatch:
build many plausible non-omniscient strategies BEFORE trusting any pass
bar, and require the reference to beat every one of them by a real
margin -- not just the single "obvious" greedy. Each probe factory
returns a fresh decide() closure so probes never leak state across
scenarios or across each other.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from online_reference import _hungarian_min_cost, MISS_PENALTY  # noqa: E402


def _rate_lookup(state, which):
    pairs = state.spread_cheap if which == "cheap" else state.spread_expensive
    return {(f, t): r for f, t, r in pairs}


def _current_rate(state, pair):
    cutoff = {(f, t): c for f, t, c in state.cutoff_time}.get(pair)
    if cutoff is None:
        return None
    cheap = {(f, t): r for f, t, r in state.spread_cheap}.get(pair)
    expensive = {(f, t): r for f, t, r in state.spread_expensive}.get(pair)
    return cheap if state.current_time <= cutoff else expensive


# ---------------------------------------------------------------- greedy family

def make_greedy_immediate(order="id", tie_break="rate"):
    """Acts the instant any obligation is underfunded and a source exists,
    never waits. `order` controls which pending obligation is considered
    first when several compete for the same source in one call; `tie_break`
    controls which source is picked when rates tie."""
    def _key(ob):
        if order == "id":
            return ob.obligation_id
        if order == "amount_desc":
            return -ob.amount
        if order == "due":
            return ob.due_time
        if order == "currency":
            return ob.currency
        return ob.obligation_id

    def decide(state):
        bal = dict(state.balances)
        out = []
        for ob in sorted(state.pending_obligations, key=_key):
            if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
                continue
            best = None
            for cur in state.currencies:
                if cur == ob.currency or bal.get(cur, 0.0) < ob.amount - 1e-9:
                    continue
                rate = _current_rate(state, (cur, ob.currency))
                if rate is None:
                    continue
                key = (rate, cur) if tie_break == "rate" else (rate, -bal.get(cur, 0.0), cur)
                if best is None or key < best[0]:
                    best = (key, cur)
            if best is not None:
                out.append((best[1], ob.currency, ob.amount))
                bal[best[1]] -= ob.amount
        return out
    return decide


def make_patient_greedy(lead_time, order="due"):
    """Waits until an obligation is within `lead_time` of its due_time,
    then funds it from whatever single cheapest source is available right
    then -- sequential, one obligation at a time, no joint matching. Tests
    whether deferral ALONE (without a real joint solve) is enough."""
    def _key(ob):
        if order == "due":
            return ob.due_time
        if order == "amount_desc":
            return -ob.amount
        return ob.obligation_id

    def decide(state):
        bal = dict(state.balances)
        used = set()
        out = []
        for ob in sorted(state.pending_obligations, key=_key):
            if ob.due_time - state.current_time > lead_time:
                continue
            if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
                continue
            best = None
            for cur in state.currencies:
                if cur == ob.currency or cur in used or bal.get(cur, 0.0) < ob.amount - 1e-9:
                    continue
                rate = _current_rate(state, (cur, ob.currency))
                if rate is None:
                    continue
                if best is None or rate < best[0]:
                    best = (rate, cur)
            if best is not None:
                out.append((best[1], ob.currency, ob.amount))
                used.add(best[1])
                bal[best[1]] -= ob.amount
        return out
    return decide


def make_cutoff_blind_joint():
    """Does a genuine joint (Hungarian) match among ALL currently pending
    obligations every single call -- no deferral, no waiting for a
    checkpoint -- as soon as more than one obligation is pending. Tests
    whether joint reasoning WITHOUT correct timing (committing before
    later same-batch obligations have even arrived) is enough."""
    def decide(state):
        bal = dict(state.balances)
        pending = [ob for ob in state.pending_obligations if bal.get(ob.currency, 0.0) < ob.amount - 1e-9]
        if not pending:
            return []
        sources = [c for c in state.currencies if bal.get(c, 0.0) > 1e-9]
        if not sources:
            return []
        n = len(sources) + len(pending)
        BIG = MISS_PENALTY * 100.0
        cost = [[0.0] * n for _ in range(n)]
        for i, ob in enumerate(pending):
            for j in range(len(sources)):
                src = sources[j]
                if src == ob.currency or bal.get(src, 0.0) < ob.amount - 1e-9:
                    cost[i][j] = BIG
                    continue
                rate = _current_rate(state, (src, ob.currency))
                cost[i][j] = ob.amount * rate if rate is not None else BIG
            for j in range(len(sources), n):
                cost[i][j] = MISS_PENALTY
        assign = _hungarian_min_cost(cost)
        out = []
        used = set()
        for i, ob in enumerate(pending):
            j = assign[i]
            if j < len(sources) and sources[j] not in used and cost[i][j] < BIG - 1e-6:
                out.append((sources[j], ob.currency, ob.amount))
                used.add(sources[j])
        return out
    return decide


def make_first_arrival_joint(lead_time):
    """Joint (Hungarian) match, but triggers on a fixed lead_time window
    like patient_greedy rather than on the real per-pair cutoff schedule
    -- tests whether joint reasoning with a plausible-but-wrong timing
    heuristic is enough."""
    def decide(state):
        bal = dict(state.balances)
        pending = [ob for ob in state.pending_obligations
                   if bal.get(ob.currency, 0.0) < ob.amount - 1e-9
                   and ob.due_time - state.current_time <= lead_time]
        if not pending:
            return []
        sources = [c for c in state.currencies if bal.get(c, 0.0) > 1e-9]
        if not sources:
            return []
        n = len(sources) + len(pending)
        BIG = MISS_PENALTY * 100.0
        cost = [[0.0] * n for _ in range(n)]
        for i, ob in enumerate(pending):
            for j in range(len(sources)):
                src = sources[j]
                if src == ob.currency or bal.get(src, 0.0) < ob.amount - 1e-9:
                    cost[i][j] = BIG
                    continue
                rate = _current_rate(state, (src, ob.currency))
                cost[i][j] = ob.amount * rate if rate is not None else BIG
            for j in range(len(sources), n):
                cost[i][j] = MISS_PENALTY
        assign = _hungarian_min_cost(cost)
        out = []
        used = set()
        for i, ob in enumerate(pending):
            j = assign[i]
            if j < len(sources) and sources[j] not in used and cost[i][j] < BIG - 1e-6:
                out.append((sources[j], ob.currency, ob.amount))
                used.add(sources[j])
        return out
    return decide


def build_all_probes():
    probes = {}
    for order in ("id", "amount_desc", "due", "currency"):
        for tie in ("rate", "balance"):
            probes[f"greedy_immediate_{order}_{tie}"] = make_greedy_immediate(order, tie)
    for lead in (10, 20, 30, 40, 60, 80, 100, 150):
        for order in ("due", "amount_desc"):
            probes[f"patient_greedy_{lead}_{order}"] = make_patient_greedy(lead, order)
    probes["cutoff_blind_joint"] = make_cutoff_blind_joint()
    for lead in (20, 40, 60, 80, 100):
        probes[f"first_arrival_joint_{lead}"] = make_first_arrival_joint(lead)
    return probes
