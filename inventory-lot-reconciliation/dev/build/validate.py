import sys
import os
import importlib.util

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tests", "lib"))

from generator import make_scenario, make_worked_example, SCENARIOS_SINGLE, SCENARIOS_ENTANGLED
import reference_engine

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

solution_engine = load_module(os.path.join(ROOT, "solution", "engine.py"), "solution_engine")
buggy_engine = load_module(os.path.join(ROOT, "environment", "pipeline", "engine.py"), "buggy_engine")


def report_from(engine_mod, events):
    state = engine_mod.process_events(events)
    return engine_mod.build_report(state)["skus"]


def normalize(report):
    return {sku: (v["on_hand_qty"], v["valuation"]) for sku, v in report.items()}


def main():
    # 1. cross-check the two independently-written CORRECT implementations
    for name, events in [("worked_example", make_worked_example()),
                          ("case_a(seed=8001)", make_scenario(8001, n_skus=60, id_offset=0)),
                          ("case_b(seed=8002)", make_scenario(8002, n_skus=60, id_offset=200))]:
        sol = normalize(report_from(solution_engine, events))
        ref = normalize(reference_engine.score(events))
        mism = [sku for sku in sol if sol[sku] != ref.get(sku)]
        print(f"[{name}] solution vs reference_engine: {len(mism)} mismatches" +
              (f"  FIRST: {mism[0]} sol={sol[mism[0]]} ref={ref[mism[0]]}" if mism else ""))
        assert not mism, "cross-check FAILED -- do not trust either implementation yet"

    # 2. confirm the buggy pipeline actually diverges, broken down by scenario label
    import random
    for name, seed, offset in [("case_a", 8001, 0), ("case_b", 8002, 200)]:
        rng = random.Random(seed)
        n_skus = 60
        scenarios = (["plain"] * (n_skus // 4)
                     + SCENARIOS_SINGLE * (n_skus // 4 // len(SCENARIOS_SINGLE) + 1) * 3
                     + SCENARIOS_ENTANGLED * (n_skus // 4 // len(SCENARIOS_ENTANGLED) + 1) * 3)
        rng.shuffle(scenarios)
        scenarios = scenarios[:n_skus]
        while len(scenarios) < n_skus:
            scenarios.append("plain")
        labels = {f"SKU{i+offset:03d}": s for i, s in enumerate(scenarios)}

        events = make_scenario(seed, n_skus=n_skus, id_offset=offset)
        correct = normalize(report_from(solution_engine, events))
        buggy = normalize(report_from(buggy_engine, events))

        by_label = {}
        for sku in correct:
            lbl = labels[sku]
            match = correct[sku] == buggy.get(sku)
            by_label.setdefault(lbl, [0, 0])
            by_label[lbl][0 if match else 1] += 1
        print(f"\n[{name}] buggy vs correct, by scenario:")
        for lbl, (m, mm) in sorted(by_label.items()):
            flag = "OK (should diverge)" if (lbl != "plain" and mm > 0) else \
                   "OK (should match)" if (lbl == "plain" and m > 0 and mm == 0) else "*** PROBLEM ***"
            print(f"  {lbl}: matched={m} mismatched={mm}  {flag}")


if __name__ == "__main__":
    main()
