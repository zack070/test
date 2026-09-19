#!/usr/bin/env python3
"""Cheat / naive baseline: the simplest plausible approach -- sort jobs by
due date only (classic EDD dispatch rule), completely ignoring setup
times. This is the "did no real analysis" baseline: a reader who noticed
the objective involves tardiness but didn't think about setup-time
sequencing at all."""
import argparse
import json

ap = argparse.ArgumentParser()
ap.add_argument("--instance", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--time-budget", required=True, type=float)
args = ap.parse_args()

with open(args.instance) as f:
    instance = json.load(f)

jobs = sorted(instance["jobs"], key=lambda j: j["due_date"])
sequence = [j["job_id"] for j in jobs]

with open(args.output, "w") as f:
    json.dump({"sequence": sequence}, f)
