"""Validates dev/online_reference.py against every gadget instance
find_swap_gadget.py's search accepted: confirms the genuinely-online
policy (no future knowledge beyond the public rate/cutoff schedule)
actually reaches the offline optimum on each one, not just beats the
naive greedy probes. A gadget that's hard for greedy but unreachable by
ANY fair online policy would make a calibrated pass bar unfair.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
from simulator import run_simulation, ObligationSpec  # noqa: E402
from find_swap_gadget import search  # noqa: E402
from online_reference import make_policy  # noqa: E402


def run_online(r_ac, r_ad, r_bc, r_bd, amount, cutoff, due, arr_c, arr_d, horizon=200):
    currencies = ["A", "B", "C", "D"]
    spread = {("A", "C"): r_ac, ("A", "D"): r_ad, ("B", "C"): r_bc, ("B", "D"): r_bd}
    cutoff_map = {k: cutoff for k in spread}
    start = {"A": amount, "B": amount, "C": 0.0, "D": 0.0}
    obligations = [
        ObligationSpec("OBL_C", "C", amount, due_time=due, arrival_time=arr_c),
        ObligationSpec("OBL_D", "D", amount, due_time=due, arrival_time=arr_d),
    ]
    policy = make_policy()
    r = run_simulation(currencies, spread, spread, cutoff_map, start, [], obligations, horizon, policy)
    return r.total_cost, r.num_missed


def main():
    gadgets = search()
    print(f"testing online_reference against {len(gadgets)} verified gadget instances")
    mismatches = []
    for g in gadgets:
        cost, missed = run_online(
            g["r_ac"], g["r_ad"], g["r_bc"], g["r_bd"],
            g["amount"], g["cutoff"], g["due"], g["arr_c"], g["arr_d"],
        )
        if missed != 0 or cost > g["ref_cost"] + 1e-6:
            mismatches.append((g, cost, missed))
    print(f"{len(gadgets) - len(mismatches)}/{len(gadgets)} reached the offline optimum exactly, 0 misses")
    for g, cost, missed in mismatches[:10]:
        print("MISMATCH", g, "online_cost=", cost, "missed=", missed)


if __name__ == "__main__":
    main()
