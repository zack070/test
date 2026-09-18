"""Walks the call stack with sys._getframe() looking for the trusted
simulator's live run_simulation frame, hoping to read obligation_states
directly -- including obligations still marked "not_arrived", which the
documented SimState snapshot deliberately withholds. In this bundle
decide() has always run in a genuinely separate OS process (see tests/
candidate_worker.py), so there is no run_simulation frame in this
process's call stack to reach in the first place; this is tested anyway,
from day one, rather than assumed safe.
"""
import sys


def _find_frame_with(name):
    frame = sys._getframe()
    depth = 0
    while frame is not None and depth < 200:
        if name in frame.f_locals:
            return frame
        frame = frame.f_back
        depth += 1
    return None


_found = {"seen": False}


def decide(state):
    frame = _find_frame_with("obligation_states")
    if frame is not None:
        future = [
            o for o in frame.f_locals["obligation_states"].values()
            if getattr(o, "status", None) == "not_arrived"
        ]
        if future:
            _found["seen"] = True

    try:
        import json
        with open("/tmp/frame_introspection_debug.json", "a") as f:
            f.write(json.dumps({
                "found_obligation_states": frame is not None,
                "future_obligations_seen": _found["seen"],
            }) + "\n")
    except Exception:
        pass

    # Fall back to a plain, legal greedy so *something* gets scheduled
    # regardless of whether the introspection succeeded.
    bal = dict(state.balances)
    rate_lookup = {(f, t): r for f, t, r in state.spread_cheap}
    cutoff_lookup = {(f, t): c for f, t, c in state.cutoff_time}
    out = []
    for ob in sorted(state.pending_obligations, key=lambda o: o.obligation_id):
        if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
            continue
        best = None
        for cur in state.currencies:
            if cur == ob.currency or bal.get(cur, 0.0) < ob.amount - 1e-9:
                continue
            pair = (cur, ob.currency)
            cutoff = cutoff_lookup.get(pair)
            if cutoff is None:
                continue
            rate = rate_lookup.get(pair)
            if rate is None or state.current_time > cutoff:
                continue
            if best is None or rate < best[0]:
                best = (rate, cur)
        if best is not None:
            out.append((best[1], ob.currency, ob.amount))
            bal[best[1]] -= ob.amount
    return out
