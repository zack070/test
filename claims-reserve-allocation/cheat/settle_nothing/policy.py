"""Defers every claim -- trivially budget-feasible, but forfeits every
settlement discount, so its expected cost (and objective) should be far
worse than any real policy."""
import csv
import json
import sys

if __name__ == "__main__":
    decisions = {}
    with open(sys.argv[1] + "/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            decisions[r["claim_id"]] = 0
    with open(sys.argv[2], "w") as f:
        json.dump({"decisions": decisions}, f)
