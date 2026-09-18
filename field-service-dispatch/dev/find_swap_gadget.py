#!/usr/bin/env python3
"""Searches for verified 'swap gadget' parameter sets: two technicians and
two jobs (all sharing one otherwise-unused skill) where reacting to
whichever job arrives first and picking its pairwise-cheapest technician
locks in a technician who is wrong for the OTHER job, at a large,
unambiguous cost gap versus the true joint-optimal pairing. Verified
directly against solution/policy.py's real (corrected) cost formula, not
assumed. Used to hand-pick a diverse library of gadgets for
build_scenarios.py rather than re-searching at generation time.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solution"))
import simulator as sim
from policy import _pairing_cost


def search(seed, n_trials=500_000, min_gap=150):
    rng = random.Random(seed)
    best = None
    for _ in range(n_trials):
        se_a = rng.randint(60, 400)
        mo_a = rng.randint(10, 200)
        se_b = rng.randint(60, 400)
        mo_b = rng.randint(10, 200)
        d1 = rng.randint(15, 250)
        d2 = rng.randint(15, 250)
        urgent1 = rng.random() < 0.5
        urgent2 = rng.random() < 0.5
        now = 0

        A = sim.TechSnapshot(tech_id="A", skills=frozenset({"g"}), continuous_work=0, shift_end=se_a, overtime_used=0, max_overtime=mo_a)
        B = sim.TechSnapshot(tech_id="B", skills=frozenset({"g"}), continuous_work=0, shift_end=se_b, overtime_used=0, max_overtime=mo_b)
        J1 = sim.JobSnapshot(job_id="J1", required_skill="g", duration=d1, priority="urgent" if urgent1 else "standard", deadline=10**6, arrival_time=0, is_followup=False)
        J2 = sim.JobSnapshot(job_id="J2", required_skill="g", duration=d2, priority="urgent" if urgent2 else "standard", deadline=10**6, arrival_time=0, is_followup=False)

        cA1 = _pairing_cost(J1, A, now, [A, B]); cA2 = _pairing_cost(J2, A, now, [A, B])
        cB1 = _pairing_cost(J1, B, now, [A, B]); cB2 = _pairing_cost(J2, B, now, [A, B])
        if None in (cA1, cA2, cB1, cB2):
            continue
        optimal = min(cA1 + cB2, cA2 + cB1)
        if abs(cA1 - cB1) <= 10:
            continue  # want an unambiguous (not near-tied) first pick
        j1_pick_cost = min(cA1, cB1)
        seq_result = (cA1 + cB2) if cA1 < cB1 else (cB1 + cA2)
        gap = seq_result - optimal
        if gap > min_gap and (best is None or gap > best[0]):
            best = (gap, dict(se_a=se_a, mo_a=mo_a, se_b=se_b, mo_b=mo_b, d1=d1, d2=d2,
                               urgent1=urgent1, urgent2=urgent2))
    return best


if __name__ == "__main__":
    for seed in range(1, 9):
        result = search(seed)
        if result:
            gap, params = result
            print(f"seed={seed} gap={gap:.1f} {params}")
        else:
            print(f"seed={seed}: none found")
