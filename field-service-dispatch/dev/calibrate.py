#!/usr/bin/env python3
import importlib.util
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import calib_common as cc

ROOT = cc.ROOT


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCENARIOS = [
    ("sample_45", os.path.join(ROOT, "environment/data/sample_45")),
    ("sample_87", os.path.join(ROOT, "environment/data/sample_87")),
    ("sample_150", os.path.join(ROOT, "environment/data/sample_150")),
    ("held_out_1", os.path.join(ROOT, "tests/sealed/inputs/held_out_1")),
    ("held_out_2", os.path.join(ROOT, "tests/sealed/inputs/held_out_2")),
]


def main():
    ref1 = load_module(os.path.join(ROOT, "solution/policy.py"), "ref1")
    ref2 = load_module(os.path.join(ROOT, "dev/reference2.py"), "ref2")
    no_scarcity = load_module(os.path.join(ROOT, "dev/exact_no_scarcity.py"), "no_scarcity")

    probes = cc.all_fixed_priority_probes()

    for name, path in SCENARIOS:
        techs, jobs, shift_length = cc.load_scenario(path)
        print(f"\n=== {name} ({len(techs)} techs, {len(jobs)} jobs, shift_length={shift_length}) ===")

        def run(fn):
            t0 = time.time()
            r = cc.run(techs, jobs, shift_length, fn)
            dt = time.time() - t0
            return r, dt

        r, dt = run(cc.fifo_policy)
        print(f"  naive_fifo                        cost={r.total_cost:8.1f}  breaches={r.num_breaches:3d} fu={r.num_followups_spawned:2d} OT={r.overtime_minutes_total:4d}  t={dt:.2f}s")

        r, dt = run(cc.edf_no_awareness_policy)
        print(f"  edf_no_awareness                   cost={r.total_cost:8.1f}  breaches={r.num_breaches:3d} fu={r.num_followups_spawned:2d} OT={r.overtime_minutes_total:4d}  t={dt:.2f}s")

        best_greedy = None
        for pname, pfn in probes.items():
            r, dt = run(pfn)
            if best_greedy is None or r.total_cost < best_greedy[0]:
                best_greedy = (r.total_cost, pname, r)
        r, dt = run(cc.mega_greedy_policy)
        if r.total_cost < best_greedy[0]:
            best_greedy = (r.total_cost, "mega_greedy", r)
        print(f"  best_fixed_priority_greedy ({best_greedy[1]:>28}) cost={best_greedy[0]:8.1f}  breaches={best_greedy[2].num_breaches:3d} fu={best_greedy[2].num_followups_spawned:2d} OT={best_greedy[2].overtime_minutes_total:4d}")

        r, dt = run(no_scarcity.decide)
        print(f"  exact_matching_no_scarcity         cost={r.total_cost:8.1f}  breaches={r.num_breaches:3d} fu={r.num_followups_spawned:2d} OT={r.overtime_minutes_total:4d}  t={dt:.2f}s")

        r1, dt1 = run(ref1.decide)
        print(f"  reference_1 (solution/policy.py)  cost={r1.total_cost:8.1f}  breaches={r1.num_breaches:3d} fu={r1.num_followups_spawned:2d} OT={r1.overtime_minutes_total:4d}  t={dt1:.2f}s")

        r2, dt2 = run(ref2.decide)
        print(f"  reference_2 (dev/reference2.py)   cost={r2.total_cost:8.1f}  breaches={r2.num_breaches:3d} fu={r2.num_followups_spawned:2d} OT={r2.overtime_minutes_total:4d}  t={dt2:.2f}s")

        agree = "MATCH" if abs(r1.total_cost - r2.total_cost) < 1e-6 else f"DIFFER by {abs(r1.total_cost - r2.total_cost):.1f}"
        print(f"  -> two independent references: {agree}")


if __name__ == "__main__":
    main()
