"""A genuinely online (decide()-by-decide(), no simulation-internals
access) reference policy for the cash-sweep task. This is not the offline
optimum used by find_swap_gadget.py to establish a ground-truth floor --
it is a real candidate for solution/policy.py: it only ever sees what
SimState documents (current balances, pending obligations, the public
rate/cutoff schedule), and it has to decide when to act using nothing
but that.

Core idea, the direct analog of field-service-dispatch's t=0-batching
logic generalized from a single special instant to every currency pair's
own cutoff: for any pending obligation, using the cheap rate on a
funding pair requires acting at or before that pair's cutoff, so the
latest defensible moment to decide is the LAST cutoff (across all pairs
that could fund that obligation's currency) still before the obligation's
due_time -- earlier than that and a currency that hasn't arrived yet, or
another obligation that hasn't arrived yet, might still show up and
change what the best joint allocation is; later than that and the cheap
rate on some relevant pair is already gone. If no such cutoff exists
before due_time, there is nothing to gain by waiting, so it acts as soon
as the obligation is pending. Every rate/cutoff value used here comes
from state.cutoff_time / state.spread_cheap / state.spread_expensive --
static public market data available on every call, never a hidden file.

Once at least one currently-pending obligation has reached its trigger
point, every pending obligation that has ALSO reached its own trigger
point is solved jointly (minimum-cost bipartite match, sources = every
currency with a positive balance, sinks = the triggered obligations) --
not committed one at a time -- via the same Hungarian algorithm used in
field-service-dispatch's solution/policy.py, adapted to this problem's
own cost structure (a currency-pair spread instead of a technician-skill
pairing cost).
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


def make_policy():
    """Returns a fresh decide() closure with its own private trigger-time
    memo, so a fresh policy instance never leaks state across scenarios."""
    trigger_memo = {}

    def _trigger_time(ob, cutoffs_for_currency, cache_key):
        if cache_key in trigger_memo:
            return trigger_memo[cache_key]
        earlier = [c for c in cutoffs_for_currency if c < ob.due_time]
        trig = max(earlier) if earlier else None
        trigger_memo[cache_key] = trig
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
            trig = _trigger_time(ob, cutoffs_by_dst.get(ob.currency, set()), ob.obligation_id)
            if trig is None or state.current_time >= trig:
                ready.append(ob)
        if not ready:
            return []

        sources = [c for c in state.currencies if bal.get(c, 0.0) > 1e-9]
        if not sources:
            return []

        # Square matrix: real sources as columns 0..len(sources)-1, one
        # "leave this obligation unfunded now" dummy column per ready
        # obligation after that (so the option is always available
        # regardless of how len(ready) compares to len(sources) -- with
        # no separate dummy block, a ready count that happened to equal
        # the source count would force every obligation onto a real
        # source even when leaving one unfunded is actually cheaper),
        # and dummy rows padding up to a square shape. Real-vs-dummy is
        # decided from the assigned COLUMN INDEX, never the cost value:
        # a real, feasible transfer can legitimately cost exactly
        # MISS_PENALTY by coincidence (amount * rate == 200.0 is not
        # rare with round scenario numbers), so comparing costs would
        # misclassify it as the dummy option.
        n_real_obs = len(ready)
        n = len(sources) + n_real_obs  # real source columns + one dummy column per obligation
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

    return decide
