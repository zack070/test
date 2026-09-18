"""Second, independently-coded online reference policy for cash-sweep,
built specifically to cross-check dev/online_reference.py (and
solution/policy.py, which is the same implementation) against a
DIFFERENT matching algorithm -- exhaustive search over source-to-
obligation assignments instead of the Hungarian algorithm -- so a bug
shared between "the reference" and "the thing that sets the pass bar"
can't hide simply because both are the same code. Per-call ready-set
sizes are small in practice (checked empirically: at most 7 simultaneous
pending obligations across both held-out scenarios), so brute-force
permutation search is both correct-by-construction and fast enough to
run for real, not just in theory -- there is a hard assertion below that
refuses to silently degrade if a future scenario ever grows past what
this can exhaustively search.

Same trigger-time CONCEPT as dev/online_reference.py (defer to each
obligation's last useful cutoff before its due time, using only public
schedule data) -- that concept is what's under test, not incidental to
this file -- but the matching step itself shares no code with the
Hungarian implementation.
"""
from __future__ import annotations

import itertools

MISS_PENALTY = 200.0
MAX_BRUTE_FORCE_READY = 9  # 9! = 362,880 -- still fast; refuses beyond this rather than silently truncate


def make_policy():
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
                continue
            trig = _trigger_time(ob, cutoffs_by_dst.get(ob.currency, set()), ob.obligation_id)
            if trig is None or state.current_time >= trig:
                ready.append(ob)
        if not ready:
            return []

        sources = [c for c in state.currencies if bal.get(c, 0.0) > 1e-9]
        if not sources:
            return []

        assert len(ready) <= MAX_BRUTE_FORCE_READY, (
            f"ready set of {len(ready)} obligations exceeds the size this cross-check "
            f"reference was built and verified to handle exhaustively -- widen it or cap "
            f"scenario generation, do not silently truncate the search"
        )

        def pair_cost(src, ob):
            if src == ob.currency or bal.get(src, 0.0) < ob.amount - 1e-9:
                return None
            p = (src, ob.currency)
            if p not in cutoff:
                return None
            rate = rate_cheap[p] if state.current_time <= cutoff[p] else rate_expensive[p]
            return ob.amount * rate

        # Exhaustive search: try every way of choosing which subset of
        # `ready` gets funded this call and by which distinct source, and
        # keep the assignment with the lowest total cost (unfunded
        # obligations in this call cost MISS_PENALTY each, same as the
        # simulator's real accounting for a miss at due_time -- this call
        # is each ready obligation's last chance, by construction of the
        # trigger rule, so that charge is the real cost of skipping it).
        # Exhaustive over every k from 0 to m, no shortcuts: funding more
        # obligations is not guaranteed monotonically cheaper (a smaller,
        # cheaper subset can beat a larger one forced through an
        # expensive source), so this deliberately does not break early.
        m = min(len(ready), len(sources))
        best_cost = None
        best_assignment = None
        for k in range(0, m + 1):
            for ob_subset in itertools.combinations(range(len(ready)), k):
                for src_perm in itertools.permutations(range(len(sources)), k):
                    cost = 0.0
                    ok = True
                    assignment = []
                    for ob_idx, src_idx in zip(ob_subset, src_perm):
                        ob = ready[ob_idx]
                        c = pair_cost(sources[src_idx], ob)
                        if c is None:
                            ok = False
                            break
                        cost += c
                        assignment.append((sources[src_idx], ob.currency, ob.amount))
                    if not ok:
                        continue
                    unfunded = len(ready) - k
                    cost += unfunded * MISS_PENALTY
                    if best_cost is None or cost < best_cost - 1e-9:
                        best_cost = cost
                        best_assignment = assignment
        return best_assignment or []

    return decide
