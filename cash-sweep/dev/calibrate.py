"""Calibration harness: runs the full adversarial probe battery plus the
genuinely-online reference policy against a set of generated scenarios,
and asserts the reference beats every single probe on every scenario --
a hard invariant, not a target to eyeball. Prints per-scenario floors so
pass bars can be set with real, measured headroom above the reference and
real, measured distance below the weakest probe.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
from simulator import run_simulation  # noqa: E402
from scenario_gen import generate_scenario  # noqa: E402
from online_reference import make_policy  # noqa: E402
from calib_common import build_all_probes  # noqa: E402


def run_all(scenario, label):
    probes = build_all_probes()
    results = {}
    for name, fn in probes.items():
        r = run_simulation(
            scenario.currencies, scenario.spread_cheap, scenario.spread_expensive,
            scenario.cutoff_time, scenario.starting_balances, scenario.credits,
            scenario.obligations, scenario.horizon, fn,
        )
        results[name] = (r.total_cost, r.num_missed)

    ref_policy = make_policy()
    ref = run_simulation(
        scenario.currencies, scenario.spread_cheap, scenario.spread_expensive,
        scenario.cutoff_time, scenario.starting_balances, scenario.credits,
        scenario.obligations, scenario.horizon, ref_policy,
    )
    results["online_reference"] = (ref.total_cost, ref.num_missed)

    worst_probe = max((c for name, (c, m) in results.items() if name != "online_reference"), default=None)
    best_probe = min((c for name, (c, m) in results.items() if name != "online_reference"), default=None)

    print(f"\n=== {label} ===")
    print(f"gadgets={scenario.gadget_count} filler={scenario.filler_count} "
          f"currencies={len(scenario.currencies)} obligations={len(scenario.obligations)} horizon={scenario.horizon}")
    print(f"online_reference: cost={ref.total_cost:.2f} missed={ref.num_missed}")
    print(f"best probe:  {best_probe:.2f}   worst probe: {worst_probe:.2f}")
    violations = [(name, c, m) for name, (c, m) in results.items()
                  if name != "online_reference" and c <= ref.total_cost + 1e-6]
    if violations:
        print("VIOLATIONS (probe at or below reference):")
        for name, c, m in violations:
            print(f"  {name}: cost={c:.2f} missed={m}")
    else:
        print(f"OK: reference beats every probe (margin {best_probe / ref.total_cost:.2f}x - {worst_probe / ref.total_cost:.2f}x)")
    return ref.total_cost, best_probe, worst_probe, len(violations)


def main():
    profiles = [
        ("sample_A", dict(seed=101, n_gadgets=2, n_filler=4, home_balance=30000.0, mid_day_credit=False)),
        ("sample_B", dict(seed=202, n_gadgets=3, n_filler=6, home_balance=50000.0, mid_day_credit=True)),
        ("sample_C", dict(seed=303, n_gadgets=2, n_filler=8, home_balance=40000.0, mid_day_credit=False)),
        ("held_out_1", dict(seed=404, n_gadgets=3, n_filler=5, home_balance=45000.0, mid_day_credit=False)),
        ("held_out_2", dict(seed=505, n_gadgets=4, n_filler=8, home_balance=70000.0, mid_day_credit=True)),
    ]
    total_violations = 0
    for label, kwargs in profiles:
        scenario = generate_scenario(**kwargs)
        _, _, _, violations = run_all(scenario, label)
        total_violations += violations
    print(f"\n{'ALL CLEAR' if total_violations == 0 else 'FAILURES'}: {total_violations} total violations across {len(profiles)} scenarios")
    sys.exit(1 if total_violations else 0)


if __name__ == "__main__":
    main()
