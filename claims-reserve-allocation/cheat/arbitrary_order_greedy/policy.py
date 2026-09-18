"""Settles claims in file order until the budget runs out, ignoring value
entirely -- the 'did essentially no analysis' baseline."""
import csv
import json
import sys


def main(data_dir, out_path):
    with open(f"{data_dir}/config.json") as f:
        cfg = json.load(f)
    budget = cfg["budget_usd"]

    rows = []
    with open(f"{data_dir}/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    decisions = {}
    remaining = budget
    for r in rows:
        offer = float(r["settlement_offer_usd"])
        if offer <= remaining:
            decisions[r["claim_id"]] = 1
            remaining -= offer
        else:
            decisions[r["claim_id"]] = 0

    with open(out_path, "w") as f:
        json.dump({"decisions": decisions}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
