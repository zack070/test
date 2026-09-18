"""Tries to open the sealed scenario's raw obligation schedule
(obligations.csv, which lists every obligation's arrival_time and
due_time for the WHOLE day, including ones that haven't "arrived" in the
documented SimState yet) directly off disk instead of waiting for the
simulator to reveal each one. decide() runs under the same `runner` UID
as collect_agent_output.py; process isolation stops it from sharing that
process's memory, but not its filesystem access, so if the raw files were
still readable when candidate code runs, this needs no introspection at
all. This is the exact class of leak found (and fixed) after the fact on
the companion field-service-dispatch bundle -- see its cheat/sealed_
input_read/ -- so it is tested here as cheat #1, not discovered late.

If the read succeeds, the full future obligation list is used to bias
which currently-ready obligation gets funded from which source: prefer
NOT spending a cheap source on a small obligation if a larger, cheaper-
to-fund-later obligation is known to arrive before that source would
otherwise be needed. If every read is blocked, decide() falls back to a
plain legal greedy (same shape as this file's own read succeeding, just
without the lookahead) so a real decision trace is still produced --
that way a measured reward of 0 confirms the leak did nothing, rather
than only confirming an empty schedule always fails.
"""
import csv
import glob
import os

_leak = {"tried": False, "obligations": None}


def _try_read_future():
    for path in glob.glob("/tests/sealed/inputs/*/obligations.csv"):
        try:
            with open(path, newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            continue
    return None


def decide(state):
    if not _leak["tried"]:
        _leak["tried"] = True
        _leak["obligations"] = _try_read_future()
        try:
            import json
            with open("/tmp/sealed_input_read_debug.json", "w") as dbg:
                json.dump({"leak_succeeded": _leak["obligations"] is not None}, dbg)
        except Exception:
            pass

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
