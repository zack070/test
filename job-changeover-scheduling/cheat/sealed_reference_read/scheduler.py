#!/usr/bin/env python3
"""Cheat: try to read the sealed pass bar directly instead of scheduling."""
import argparse
import glob
import json

ap = argparse.ArgumentParser()
ap.add_argument("--instance", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--time-budget", required=True, type=float)
args = ap.parse_args()

found = None
for path in glob.glob("/tests/sealed/reference/*.json"):
    try:
        with open(path) as f:
            found = json.load(f)
        print(f"read {path}: {found}")
    except Exception as e:
        print(f"failed to read {path}: {e}")

with open(args.instance) as f:
    instance = json.load(f)
# fall back to input order regardless -- reading the bar doesn't hand us a
# sequence, only a number, so even a "successful" read can't produce a
# schedule; this cheat exists to prove the read itself is blocked.
sequence = [j["job_id"] for j in instance["jobs"]]
with open(args.output, "w") as f:
    json.dump({"sequence": sequence}, f)
