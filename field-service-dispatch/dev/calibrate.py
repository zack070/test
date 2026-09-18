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
    for name, path in SCENARIOS:
        # Rebuild every probe fresh per scenario -- some (the t0-deferring
        # greedy variants) carry closure state across a shift that must
        # not leak between scenarios in this same process.
        probes = cc.all_fixed_priority_probes()
        # Reload every scenario-scoped module fresh per scenario: some
        # (the references, with their t=0 batching) now keep module-level
        # state across a shift that must not leak between scenarios in
        # this same process, exactly like the real verifier's stage 1.
        ref1 = load_module(os.path.join(ROOT, "solution/policy.py"), f"ref1_{name}")
        ref2 = load_module(os.path.join(ROOT, "dev/reference2.py"), f"ref2_{name}")
        no_scarcity = load_module(os.path.join(ROOT, "dev/exact_no_scarcity.py"), f"no_scarcity_{name}")
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

        all_probes = dict(probes)
        all_probes["mega_greedy"] = cc.mega_greedy_policy
        all_probes["mega_greedy__feasible"] = cc.mega_greedy_feasible_policy
        all_probes["greedy_pair_picker_real_cost"] = cc.greedy_pair_picker_real_cost_policy
        # t0-deferring hybrids: same batching trick as the real reference,
        # but a plain greedy (not a joint solve) on the accumulated batch.
        # If any of these matches the reference, deferral alone would be
        # "enough" and the difficulty wouldn't really be about joint
        # reasoning -- so this is a required check, not decoration.
        for jo in cc.JOB_ORDER_RULES:
            for tb in cc.TIE_BREAK_RULES:
                all_probes[f"defer_t0__{jo}__{tb}"] = cc.make_t0_deferring_greedy(jo, tb, feasibility_filtered=True)

        best_greedy = None
        for pname, pfn in all_probes.items():
            r, dt = run(pfn)
            if best_greedy is None or r.total_cost < best_greedy[0]:
                best_greedy = (r.total_cost, pname, r)
        print(f"  best_of_{len(all_probes):2d}_greedy_probes ({best_greedy[1]:>28}) cost={best_greedy[0]:8.1f}  breaches={best_greedy[2].num_breaches:3d} fu={best_greedy[2].num_followups_spawned:2d} OT={best_greedy[2].overtime_minutes_total:4d}")

        r, dt = run(no_scarcity.decide)
        print(f"  exact_matching_no_scarcity         cost={r.total_cost:8.1f}  breaches={r.num_breaches:3d} fu={r.num_followups_spawned:2d} OT={r.overtime_minutes_total:4d}  t={dt:.2f}s")

        r1, dt1 = run(ref1.decide)
        print(f"  reference_1 (solution/policy.py)  cost={r1.total_cost:8.1f}  breaches={r1.num_breaches:3d} fu={r1.num_followups_spawned:2d} OT={r1.overtime_minutes_total:4d}  t={dt1:.2f}s")

        r2, dt2 = run(ref2.decide)
        print(f"  reference_2 (dev/reference2.py)   cost={r2.total_cost:8.1f}  breaches={r2.num_breaches:3d} fu={r2.num_followups_spawned:2d} OT={r2.overtime_minutes_total:4d}  t={dt2:.2f}s")

        agree = "MATCH" if abs(r1.total_cost - r2.total_cost) < 1e-6 else f"DIFFER by {abs(r1.total_cost - r2.total_cost):.1f}"
        print(f"  -> two independent references: {agree}")

        # Hard invariant: an "exact" reference must never be beaten by any
        # tested greedy/heuristic probe. If this fires, the reference (or
        # its cost model) is wrong -- not a calibration nuance to shrug off.
        if best_greedy[0] < r1.total_cost - 1e-6:
            print(f"  !!! INVARIANT VIOLATED: best greedy ({best_greedy[0]:.1f}) beats reference_1 ({r1.total_cost:.1f}) !!!")
        if best_greedy[0] < r2.total_cost - 1e-6:
            print(f"  !!! INVARIANT VIOLATED: best greedy ({best_greedy[0]:.1f}) beats reference_2 ({r2.total_cost:.1f}) !!!")


if __name__ == "__main__":
    main()
