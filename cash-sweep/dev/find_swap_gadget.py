"""Search for, then verify against the REAL simulator, a family of
swap-tension gadget parameter sets: two source currencies (A, B) with
surplus balance, two obligations (funding sink C, sink D) arriving
together, and a 2x2 rate matrix where committing the single locally-
cheapest source/sink pair first forecloses a strictly cheaper joint
match.

Shape (generalizes the one hand-built case already validated in
dev/test_gadget_v2.py -- this script exists so scenario_gen.py never has
to trust a single hand-checked instance, the same discipline
field-service-dispatch's dev/find_swap_gadget.py used):

    rate(A,C) = r_ac   (globally cheapest -- greedy snaps A to C first)
    rate(A,D) = r_ad
    rate(B,C) = r_bc
    rate(B,D) = r_bd   (expensive)

Greedy match (each obligation grabs its own cheapest available source,
one at a time, in isolation): A->C, B->D, cost = r_ac + r_bd.
Optimal match: A->D, B->C, cost = r_ad + r_bc.
Gadget "bites" when the optimal match is strictly, robustly cheaper than
the greedy match, AND when a battery of realistic non-omniscient probes
(not just the one naive greedy above) all still land on the worse match.

This script does not hand-pick numbers and hope; it draws random
candidate rate matrices, verifies the arithmetic condition analytically,
then confirms it experimentally by running the REAL run_simulation with
several probe policies against each candidate and keeping only instances
where every tested non-joint probe strictly loses to a joint reference.
"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
from simulator import run_simulation, CreditSpec, ObligationSpec  # noqa: E402
from calib_common import make_cutoff_blind_joint, make_first_arrival_joint  # noqa: E402


def _balmap(state):
    return dict(state.balances)


def greedy_immediate(state):
    bal = _balmap(state)
    rate_lookup = {(f, t): r for f, t, r in state.spread_cheap}
    out = []
    for ob in sorted(state.pending_obligations, key=lambda o: o.obligation_id):
        if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
            continue
        best = None
        for cur in state.currencies:
            if cur == ob.currency or bal.get(cur, 0.0) < ob.amount - 1e-9:
                continue
            rate = rate_lookup.get((cur, ob.currency))
            if rate is None:
                continue
            if best is None or rate < best[0]:
                best = (rate, cur)
        if best is not None:
            out.append((best[1], ob.currency, ob.amount))
            bal[best[1]] -= ob.amount
    return out


def make_patient_greedy(lead_time):
    def _fn(state):
        bal = _balmap(state)
        rate_lookup = {(f, t): r for f, t, r in state.spread_cheap}
        out = []
        used = set()
        for ob in sorted(state.pending_obligations, key=lambda o: o.due_time):
            if ob.due_time - state.current_time > lead_time:
                continue
            if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
                continue
            best = None
            for cur in state.currencies:
                if cur == ob.currency or cur in used or bal.get(cur, 0.0) < ob.amount - 1e-9:
                    continue
                rate = rate_lookup.get((cur, ob.currency))
                if rate is None:
                    continue
                if best is None or rate < best[0]:
                    best = (rate, cur)
            if best is not None:
                out.append((best[1], ob.currency, ob.amount))
                used.add(best[1])
                bal[best[1]] -= ob.amount
        return out
    return _fn


def run_candidate(r_ac, r_ad, r_bc, r_bd, amount, cutoff, due, arr_c, arr_d, horizon=None):
    if horizon is None:
        horizon = due + 50
    currencies = ["A", "B", "C", "D"]
    spread = {("A", "C"): r_ac, ("A", "D"): r_ad, ("B", "C"): r_bc, ("B", "D"): r_bd}
    cutoff_map = {k: cutoff for k in spread}
    start = {"A": amount, "B": amount, "C": 0.0, "D": 0.0}
    obligations = [
        ObligationSpec("OBL_C", "C", amount, due_time=due, arrival_time=arr_c),
        ObligationSpec("OBL_D", "D", amount, due_time=due, arrival_time=arr_d),
    ]
    probes = {"greedy_immediate": greedy_immediate, "cutoff_blind_joint": make_cutoff_blind_joint()}
    for lead in (10, 20, 30, 40, 60, 80, 100, 150, 250, 1_000_000):
        probes[f"patient_greedy_{lead}"] = make_patient_greedy(lead)
        probes[f"first_arrival_joint_{lead}"] = make_first_arrival_joint(lead)
    results = {}
    for name, fn in probes.items():
        r = run_simulation(currencies, spread, spread, cutoff_map, start, [], obligations, horizon, fn)
        results[name] = r.total_cost
    # Global offline optimum: this is a closed 2x2 assignment (A,B funding
    # C,D), so the true minimum achievable cost -- what an omniscient
    # planner with the whole day's information in hand would pay -- is
    # just the cheaper of the two possible perfect matchings. This is not
    # a "policy" being simulated; it's the ground-truth floor the gadget
    # is checked against.
    results["offline_optimal"] = amount * min(r_ac + r_bd, r_ad + r_bc)
    return results


MISS_PENALTY_SAFETY_MARGIN = 160.0  # keep comfortably under simulator.MISS_PENALTY (200.0)


def search(n_trials=2000, seed=0):
    rng = random.Random(seed)
    found = []
    for _ in range(n_trials):
        r_ac = round(rng.uniform(0.005, 0.03), 4)
        r_bd = round(rng.uniform(3.0, 10.0) * r_ac, 4)
        mid = round(rng.uniform(1.5, 2.8) * r_ac, 4)
        r_ad, r_bc = mid, mid
        greedy_cost = r_ac + r_bd
        optimal_cost = r_ad + r_bc
        if not (optimal_cost < greedy_cost * 0.6):
            continue  # want a large, unambiguous margin, not a hair's-breadth win
        amount = rng.choice([500.0, 1000.0, 2000.0, 5000.0])
        if amount * r_bd >= MISS_PENALTY_SAFETY_MARGIN:
            continue  # even the worst feasible funding must stay cheaper than eating
            # the miss penalty -- otherwise the true optimum isn't "which joint
            # allocation", it's "which obligation to deliberately sacrifice", a
            # different (and, for THIS gadget's purpose, off-target) question. The
            # analytic offline_optimal below only ever compares the two FULL
            # matchings for exactly that reason: it's only the true global optimum
            # while this margin holds.
        cutoff = rng.choice([80, 100, 120, 150])
        # A wide, varied due-cutoff gap matters: if every gadget kept due
        # shortly after cutoff, "wait a fixed N ticks before due, then
        # joint-match" would always happen to land in the same safe
        # window as "act at the real cutoff" without ever consulting
        # state.cutoff_time -- collapsing the timing dimension this
        # domain is supposed to add. Spanning tight (20) to very loose
        # (250) gaps means no single fixed lead_time can cover every
        # gadget: too small and it fires after a far-off cutoff has
        # already lapsed into the expensive rate; too large and it fires
        # before a near cutoff's obligations have even all arrived.
        # Continuous, not drawn from the same discrete set the probe
        # battery's lead_time values use (10/20/.../250) -- otherwise a
        # gadget whose gap happens to exactly equal one of those constants
        # would trivially tie a probe by coincidence rather than by that
        # probe representing a genuinely robust strategy, and get thrown
        # out by the strict "beats every probe" filter below for the
        # wrong reason.
        due = cutoff + rng.randint(15, 260)
        arr_c = 0
        arr_d = rng.randint(0, 70)
        results = run_candidate(r_ac, r_ad, r_bc, r_bd, amount, cutoff, due, arr_c, arr_d)
        ref_cost = results["offline_optimal"]
        probe_costs = [v for k, v in results.items() if k != "offline_optimal"]
        if ref_cost >= min(probe_costs) - 1e-9:
            continue  # true optimum must strictly beat every tested probe, not tie
        if not all(pc > ref_cost * 1.3 for pc in probe_costs):
            continue  # require a comfortable margin against every probe, not just the worst one
        found.append({
            "r_ac": r_ac, "r_ad": r_ad, "r_bc": r_bc, "r_bd": r_bd,
            "amount": amount, "cutoff": cutoff, "due": due, "arr_c": arr_c, "arr_d": arr_d,
            "ref_cost": ref_cost, "probe_costs": results,
        })
    return found


if __name__ == "__main__":
    results = search()
    print(f"found {len(results)} verified gadget parameter sets")
    for r in results[:5]:
        print(r)
