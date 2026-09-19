import json
import os
import sys
import importlib.util

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tests", "lib"))

from generator import make_scenario, make_worked_example
import reference_engine


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


solution_engine = load_module(os.path.join(ROOT, "solution", "engine.py"), "solution_engine")

CASE_SEED = 9001  # visible practice case -- disjoint from sealed seeds/offsets


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def main():
    # worked example
    events = make_worked_example()
    dump(events, os.path.join(ROOT, "environment/data/worked_example/events.json"))

    # visible practice case (id offset 500, disjoint from case_a=0, case_b=200)
    events = make_scenario(CASE_SEED, n_skus=60, id_offset=500)
    dump(events, os.path.join(ROOT, "environment/data/case/events.json"))

    # sealed grading datasets
    sealed_specs = [("case_a", 8001, 0), ("case_b", 8002, 200)]
    for name, seed, offset in sealed_specs:
        events = make_scenario(seed, n_skus=60, id_offset=offset)
        dump(events, os.path.join(ROOT, f"tests/sealed/inputs/{name}/events.json"))

        # cross-check before freezing
        state = solution_engine.process_events(events)
        sol_report = solution_engine.build_report(state)["skus"]
        ref_report = reference_engine.score(events)

        mism = []
        for sku in sol_report:
            a = (sol_report[sku]["on_hand_qty"], sol_report[sku]["valuation"])
            b = (ref_report[sku]["on_hand_qty"], ref_report[sku]["valuation"])
            if a != b:
                mism.append((sku, a, b))
        if mism:
            print(f"REFUSING TO FREEZE {name}: {len(mism)} mismatches between the two "
                  f"independent implementations, e.g. {mism[0]}")
            sys.exit(1)

        dump({"skus": ref_report}, os.path.join(ROOT, f"tests/sealed/reference/{name}_reference.json"))
        print(f"{name}: seed={seed} offset={offset} -- {len(sol_report)} skus, "
              f"frozen from reference_engine, cross-checked against solution/engine.py: 0 mismatches")

    print("All data files written and sealed references frozen.")


if __name__ == "__main__":
    main()
