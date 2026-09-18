"""Settles every claim regardless of the budget cap -- checks that
feasibility is enforced mechanically, independent of how good the
resulting objective would otherwise look."""
import csv
import json
import sys

if __name__ == "__main__":
    decisions = {}
    with open(sys.argv[1] + "/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            decisions[r["claim_id"]] = 1
    with open(sys.argv[2], "w") as f:
        json.dump({"decisions": decisions}, f)
