import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
MARGIN = 1.15

with open("/tmp/calibration_results.json") as f:
    results = json.load(f)

names = ["case_a", "case_b"]

for name, r in zip(names, results):
    inst = r["instance"]
    ref_obj = r["reference_obj"]
    bar = round(ref_obj * MARGIN, 2)

    in_dir = os.path.join(ROOT, "tests/sealed/inputs", name)
    os.makedirs(in_dir, exist_ok=True)
    with open(os.path.join(in_dir, "instance.json"), "w") as f:
        json.dump(inst, f, indent=2)

    ref_dir = os.path.join(ROOT, "tests/sealed/reference")
    os.makedirs(ref_dir, exist_ok=True)
    with open(os.path.join(ref_dir, f"{name}_reference.json"), "w") as f:
        json.dump({
            "reference_objective": ref_obj,
            "pass_bar": bar,
            "heuristic_objective": r["heuristic_obj"],
            "cpsat_objective": r["cpsat_obj"],
        }, f, indent=2)

    print(f"{name}: seed={r['seed']} reference={ref_obj} bar={bar} "
          f"heuristic={r['heuristic_obj']} cpsat={r['cpsat_obj']}")

print("Sealed data + reference bars frozen.")
