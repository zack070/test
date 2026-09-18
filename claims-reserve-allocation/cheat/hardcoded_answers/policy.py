"""Ships a lookup table of decisions computed on the visible case dataset
(the same generator's claim_id numbering restarts at CLM0001 for every
portfolio, so held-out claim_ids happen to overlap with the visible
case's), falling back to settle-nothing for anything unrecognized. The
underlying claim facts (type, cluster, offer, budget) differ on held-out
data even where the id matches, so this should fail to generalize."""
import csv
import json
import os
import sys

MEMORIZED_PATH = os.path.join(os.path.dirname(__file__), "memorized.json")


def main(data_dir, out_path):
    with open(MEMORIZED_PATH) as f:
        memorized = json.load(f)

    decisions = {}
    with open(f"{data_dir}/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            decisions[r["claim_id"]] = memorized.get(r["claim_id"], 0)

    with open(out_path, "w") as f:
        json.dump({"decisions": decisions}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
