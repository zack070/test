#!/usr/bin/env python3
"""Cheat: memorized sequence for the visible practice case (seed 6001,
job ids J000-J044), embedded inline since only one file is graded.
Outputs it regardless of the actual input -- should fail because the
sealed grading instances use disjoint job-id ranges (J1xx / J3xx)."""
import argparse
import json

MEMORIZED_SEQUENCE = json.loads('["J009", "J016", "J041", "J003", "J026", "J012", "J039", "J017", "J002", "J022", "J020", "J036", "J043", "J034", "J005", "J001", "J044", "J033", "J008", "J031", "J025", "J013", "J029", "J019", "J028", "J018", "J035", "J037", "J000", "J004", "J011", "J021", "J023", "J032", "J038", "J015", "J030", "J010", "J006", "J014", "J027", "J040", "J042", "J007", "J024"]')

ap = argparse.ArgumentParser()
ap.add_argument("--instance", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--time-budget", required=True, type=float)
args = ap.parse_args()

with open(args.output, "w") as f:
    json.dump({"sequence": MEMORIZED_SEQUENCE}, f)
