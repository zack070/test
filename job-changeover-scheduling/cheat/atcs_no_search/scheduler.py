#!/usr/bin/env python3
"""Cheat / adversarial baseline: the ATCS dispatch rule construction only,
with no local search and no metaheuristic refinement -- a genuinely
competent published heuristic (Lee, Bhaskaran, Pinedo 1997), not a
strawman, but stops at the first reasonable sequence rather than
searching for a better one."""
import argparse
import json
import math

ap = argparse.ArgumentParser()
ap.add_argument("--instance", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--time-budget", required=True, type=float)
args = ap.parse_args()

with open(args.instance) as f:
    instance = json.load(f)

jobs = instance["jobs"]
n = len(jobs)
jobs_by_idx = {i: jobs[i] for i in range(n)}
setup_matrix = instance["setup_matrix"]
initial_setup = instance["initial_setup"]

k1, k2 = 2.0, 2.0
remaining = set(range(n))
p_bar = sum(j["proc_time"] for j in jobs) / n
s_vals = [setup_matrix[a][b] for a in range(len(setup_matrix)) for b in range(len(setup_matrix))]
s_bar = max(sum(s_vals) / len(s_vals), 1e-6)

order = []
t = 0
prev_fam = None
while remaining:
    best_idx, best_score = None, -1.0
    for idx in remaining:
        j = jobs_by_idx[idx]
        s = initial_setup[j["family"]] if prev_fam is None else setup_matrix[prev_fam][j["family"]]
        slack = max(j["due_date"] - j["proc_time"] - t, 0)
        score = (j["weight"] / j["proc_time"]) * math.exp(-slack / (k1 * p_bar)) * math.exp(-s / (k2 * s_bar))
        if score > best_score:
            best_score, best_idx = score, idx
    order.append(best_idx)
    j = jobs_by_idx[best_idx]
    s = initial_setup[j["family"]] if prev_fam is None else setup_matrix[prev_fam][j["family"]]
    t += s + j["proc_time"]
    prev_fam = j["family"]
    remaining.discard(best_idx)

sequence = [jobs_by_idx[i]["job_id"] for i in order]
with open(args.output, "w") as f:
    json.dump({"sequence": sequence}, f)
