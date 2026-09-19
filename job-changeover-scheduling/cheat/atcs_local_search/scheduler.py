#!/usr/bin/env python3
"""Cheat / headline adversarial baseline: ATCS dispatch-rule construction
plus adjacent-swap and reinsertion local search, with NO metaheuristic
restart phase. A genuinely competent, published approach (Lee, Bhaskaran,
Pinedo 1997, plus a standard local-search polish) -- not a strawman --
that stops once local search converges rather than searching further."""
import argparse
import json
import math
import time

ap = argparse.ArgumentParser()
ap.add_argument("--instance", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--time-budget", required=True, type=float)
args = ap.parse_args()

t0 = time.time()
deadline = t0 + max(args.time_budget - 3.0, 0.5)

with open(args.instance) as f:
    instance = json.load(f)

jobs = instance["jobs"]
n = len(jobs)
jobs_by_idx = {i: jobs[i] for i in range(n)}
setup_matrix = instance["setup_matrix"]
initial_setup = instance["initial_setup"]


def sequence_objective(order):
    t = 0
    cost = 0
    prev_fam = None
    for idx in order:
        j = jobs_by_idx[idx]
        if prev_fam is None:
            t += initial_setup[j["family"]]
        else:
            t += setup_matrix[prev_fam][j["family"]]
        t += j["proc_time"]
        tardy = t - j["due_date"]
        if tardy > 0:
            cost += j["weight"] * tardy
        prev_fam = j["family"]
    return cost


# ATCS construction
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

# local search: adjacent swap + reinsertion, until convergence (deadline-guarded)
best_obj = sequence_objective(order)
improved = True
iters = 0
while improved and iters < 2000:
    if time.time() > deadline:
        break
    improved = False
    iters += 1
    for i in range(n):
        if i % 10 == 0 and time.time() > deadline:
            break
        for j in range(i + 1, n):
            cand = order[:]
            cand[i], cand[j] = cand[j], cand[i]
            obj = sequence_objective(cand)
            if obj < best_obj - 1e-9:
                order, best_obj = cand, obj
                improved = True
    for i in range(n):
        if i % 10 == 0 and time.time() > deadline:
            break
        job = order[i]
        rest = order[:i] + order[i + 1:]
        for pos in range(n):
            cand = rest[:pos] + [job] + rest[pos:]
            obj = sequence_objective(cand)
            if obj < best_obj - 1e-9:
                order, best_obj = cand, obj
                improved = True

sequence = [jobs_by_idx[i]["job_id"] for i in order]
with open(args.output, "w") as f:
    json.dump({"sequence": sequence}, f)
