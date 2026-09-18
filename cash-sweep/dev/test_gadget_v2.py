import sys, itertools, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
from simulator import run_simulation, CreditSpec, ObligationSpec

CURRENCIES = ["A", "B", "C", "D"]
RATE = {
    ("A", "C"): 0.01, ("A", "D"): 0.03,
    ("B", "C"): 0.03, ("B", "D"): 0.15,
}
CUTOFF = {k: 120 for k in RATE}
START = {"A": 1000.0, "B": 1000.0, "C": 0.0, "D": 0.0}
CREDITS = []
OBLIGATIONS = [
    ObligationSpec("OBL_C", "C", 1000.0, due_time=150, arrival_time=0),
    ObligationSpec("OBL_D", "D", 1000.0, due_time=150, arrival_time=50),
]
HORIZON = 200


def _balmap(state):
    return dict(state.balances)


def greedy_immediate(state):
    bal = _balmap(state)
    out = []
    for ob in sorted(state.pending_obligations, key=lambda o: o.obligation_id):
        if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
            continue
        best = None
        for cur in CURRENCIES:
            if cur == ob.currency:
                continue
            if bal.get(cur, 0.0) < ob.amount - 1e-9:
                continue
            rate = RATE.get((cur, ob.currency))
            if rate is None:
                continue
            if best is None or rate < best[0]:
                best = (rate, cur)
        if best is not None:
            out.append((best[1], ob.currency, ob.amount))
    return out


def patient_greedy(state, lead_time=40):
    bal = _balmap(state)
    out = []
    used = set()
    for ob in sorted(state.pending_obligations, key=lambda o: o.due_time):
        if ob.due_time - state.current_time > lead_time:
            continue
        if bal.get(ob.currency, 0.0) >= ob.amount - 1e-9:
            continue
        best = None
        for cur in CURRENCIES:
            if cur == ob.currency or cur in used:
                continue
            if bal.get(cur, 0.0) < ob.amount - 1e-9:
                continue
            rate = RATE.get((cur, ob.currency))
            if rate is None:
                continue
            if best is None or rate < best[0]:
                best = (rate, cur)
        if best is not None:
            out.append((best[1], ob.currency, ob.amount))
            used.add(best[1])
    return out


def joint_reference(state, lead_time=40):
    bal = _balmap(state)
    urgent = [ob for ob in state.pending_obligations if ob.due_time - state.current_time <= lead_time and bal.get(ob.currency, 0.0) < ob.amount - 1e-9]
    if not urgent:
        return []
    sources = [cur for cur in CURRENCIES if bal.get(cur, 0.0) > 0]
    best_assignment = None
    best_cost = None
    m = min(len(urgent), len(sources))
    for ob_subset in itertools.combinations(urgent, m):
        for src_perm in itertools.permutations(sources, m):
            ok = True
            cost = 0.0
            assignment = []
            used = set()
            for ob, src in zip(ob_subset, src_perm):
                if src == ob.currency or src in used:
                    ok = False; break
                if bal.get(src, 0.0) < ob.amount - 1e-9:
                    ok = False; break
                rate = RATE.get((src, ob.currency))
                if rate is None:
                    ok = False; break
                cost += ob.amount * rate
                assignment.append((src, ob.currency, ob.amount))
                used.add(src)
            if ok and (best_cost is None or cost < best_cost):
                best_cost = cost
                best_assignment = assignment
    return best_assignment or []


for name, fn in [("greedy_immediate", greedy_immediate), ("patient_greedy", patient_greedy), ("joint_reference", joint_reference)]:
    r = run_simulation(CURRENCIES, RATE, RATE, CUTOFF, START, CREDITS, OBLIGATIONS, HORIZON, fn)
    print(f"{name:20s} cost={r.total_cost:8.2f} missed={r.num_missed} spread_cost={r.total_spread_cost:.2f}")
    for line in r.log:
        print("   ", line)
