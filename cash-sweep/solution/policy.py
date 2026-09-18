"""
Reference cash-sweep policy.

Core idea: using a currency pair's cheap rate requires initiating the
transfer at or before that pair's cutoff, so the latest defensible moment
to decide how to fund a given obligation is the LAST cutoff -- across
every pair that could fund that obligation's currency -- still strictly
before the obligation's own due_time. Deciding earlier risks acting on an
incomplete picture (another obligation, or a credit, that hasn't shown up
yet might change the best allocation); deciding later means the cheap
rate on some relevant pair is already gone. If no such cutoff exists
before due_time, there is nothing to gain by waiting, so the obligation
is funded as soon as it is pending. All of this uses only what the
documented state actually exposes: state.cutoff_time and the two spread
tables are public market data resent on every call, so reasoning about
"the last good cutoff" never requires anything beyond the current
decide() call's own arguments.

Once at least one pending obligation has reached its own trigger point,
every pending obligation that has ALSO reached its trigger point is
funded together -- a minimum-cost bipartite match (sources = every
currency with a positive balance, sinks = the triggered obligations),
not one at a time -- because committing the single cheapest source to
whichever obligation is considered first can leave a worse source as the
only option left for another obligation that a joint look at the same
moment would have funded more cheaply overall.
"""
from __future__ import annotations


def _hungarian_min_cost(cost):
    """Classic O(n^3) Kuhn-Munkres on a square cost matrix (list of lists
    of floats). Returns result[i] = column index assigned to row i."""
    n = len(cost)
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    result = [0] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            result[p[j] - 1] = j - 1
    return result


MISS_PENALTY = 200.0  # kept in sync with environment/sim/simulator.py's own constant

_trigger_memo = {}


def _trigger_time(ob, cutoffs_for_currency):
    key = ob.obligation_id
    if key in _trigger_memo:
        return _trigger_memo[key]
    earlier = [c for c in cutoffs_for_currency if c < ob.due_time]
    trig = max(earlier) if earlier else None
    _trigger_memo[key] = trig
    return trig


def decide(state):
    bal = dict(state.balances)
    rate_cheap = {(f, t): r for f, t, r in state.spread_cheap}
    rate_expensive = {(f, t): r for f, t, r in state.spread_expensive}
    cutoff = {(f, t): c for f, t, c in state.cutoff_time}
    cutoffs_by_dst = {}
    for (f, t), c in cutoff.items():
        cutoffs_by_dst.setdefault(t, set()).add(c)

    ready = []
    for ob in state.pending_obligations:
        if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
            continue  # already covered, nothing to decide
        trig = _trigger_time(ob, cutoffs_by_dst.get(ob.currency, set()))
        if trig is None or state.current_time >= trig:
            ready.append(ob)
    if not ready:
        return []

    sources = [c for c in state.currencies if bal.get(c, 0.0) > 1e-9]
    if not sources:
        return []

    # Square matrix: real sources as columns 0..len(sources)-1, one
    # "leave this obligation unfunded this call" dummy column per ready
    # obligation after that (always available, independent of how
    # len(ready) compares to len(sources)), and dummy rows padding up to
    # a square shape. Real-vs-dummy is decided from the assigned COLUMN
    # INDEX, never the cost value -- a real, feasible transfer can
    # legitimately cost exactly MISS_PENALTY by coincidence (amount *
    # rate landing on 200.0 is not rare with round numbers), so comparing
    # costs would misclassify it as the dummy option.
    n = len(sources) + len(ready)
    BIG = MISS_PENALTY * 100.0
    cost = [[0.0] * n for _ in range(n)]
    for i, ob in enumerate(ready):
        for j in range(len(sources)):
            src = sources[j]
            if src == ob.currency or bal.get(src, 0.0) < ob.amount - 1e-9:
                cost[i][j] = BIG
                continue
            pair = (src, ob.currency)
            if pair not in cutoff:
                cost[i][j] = BIG
                continue
            rate = rate_cheap[pair] if state.current_time <= cutoff[pair] else rate_expensive[pair]
            cost[i][j] = ob.amount * rate
        for j in range(len(sources), n):
            cost[i][j] = MISS_PENALTY  # any dummy column -- leave this obligation unfunded this call

    assign = _hungarian_min_cost(cost)
    out = []
    used_sources = set()
    for i, ob in enumerate(ready):
        j = assign[i]
        if j < len(sources):
            src = sources[j]
            if src in used_sources:
                continue  # Hungarian already guarantees a 1-1 match; defensive only
            out.append((src, ob.currency, ob.amount))
            used_sources.add(src)
    return out
