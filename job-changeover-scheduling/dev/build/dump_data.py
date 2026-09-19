import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from generator import make_instance, make_worked_example

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

CASE_SEED = 6001


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def main():
    worked = make_worked_example()
    dump(worked, os.path.join(ROOT, "environment/data/worked_example/instance.json"))

    case = make_instance(45, seed=CASE_SEED, id_offset=0)
    dump(case, os.path.join(ROOT, "environment/data/case/instance.json"))

    print("practice/worked data written")


if __name__ == "__main__":
    main()
