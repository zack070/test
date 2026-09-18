"""Builds the 3 visible sample scenarios and 2 sealed held-out scenarios,
serializes them to disk, and computes calibrated pass bars from the
measured online-reference cost on each held-out scenario (not assumed --
see dev/calibrate.py, which already confirmed the reference beats every
probe in the battery by a real margin on all 5 of these exact profiles).
Pass bar = reference cost * 1.2: enough slack that a genuinely
near-optimal (but not pixel-perfect Hungorian-exact) policy can still
clear it, while staying far below the best tested probe's cost on every
profile (measured 1.66x-2.09x over the reference in dev/calibrate.py), so
no heuristic in the battery can coast through by accident.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
from simulator import run_simulation  # noqa: E402
from scenario_gen import generate_scenario, write_scenario  # noqa: E402
from online_reference import make_policy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE_PROFILES = [
    ("sample_A", dict(seed=101, n_gadgets=2, n_filler=4, home_balance=30000.0, mid_day_credit=False)),
    ("sample_B", dict(seed=202, n_gadgets=3, n_filler=6, home_balance=50000.0, mid_day_credit=True)),
    ("sample_C", dict(seed=303, n_gadgets=2, n_filler=8, home_balance=40000.0, mid_day_credit=False)),
]
HELD_OUT_PROFILES = [
    ("held_out_1", dict(seed=404, n_gadgets=3, n_filler=5, home_balance=45000.0, mid_day_credit=False)),
    ("held_out_2", dict(seed=505, n_gadgets=4, n_filler=8, home_balance=70000.0, mid_day_credit=True)),
]

PASS_BAR_MARGIN = 1.2


def reference_cost(scenario):
    policy = make_policy()
    r = run_simulation(
        scenario.currencies, scenario.spread_cheap, scenario.spread_expensive,
        scenario.cutoff_time, scenario.starting_balances, scenario.credits,
        scenario.obligations, scenario.horizon, policy,
    )
    assert r.num_missed == 0, f"reference missed {r.num_missed} obligations -- scenario is miscalibrated"
    return r.total_cost


def main():
    for name, kwargs in SAMPLE_PROFILES:
        scenario = generate_scenario(**kwargs)
        out_dir = os.path.join(ROOT, "environment", "data", name)
        write_scenario(scenario, out_dir)
        cost = reference_cost(scenario)
        print(f"{name}: reference_cost={cost:.2f} -> {out_dir}")

    pass_bars = {}
    for name, kwargs in HELD_OUT_PROFILES:
        scenario = generate_scenario(**kwargs)
        out_dir = os.path.join(ROOT, "tests", "sealed", "inputs", name)
        write_scenario(scenario, out_dir)
        cost = reference_cost(scenario)
        bar = round(cost * PASS_BAR_MARGIN, 2)
        pass_bars[name] = {"reference_cost": round(cost, 2), "pass_bar_cost": bar}
        print(f"{name}: reference_cost={cost:.2f} pass_bar={bar:.2f} -> {out_dir}")

    bar_path = os.path.join(ROOT, "tests", "sealed", "reference", "pass_bar.json")
    os.makedirs(os.path.dirname(bar_path), exist_ok=True)
    with open(bar_path, "w") as f:
        json.dump({"scenarios": pass_bars}, f, indent=2)
    print(f"wrote {bar_path}")


if __name__ == "__main__":
    main()
