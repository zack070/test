#!/usr/bin/env python3
"""
Reference solution for the single-machine changeover-scheduling task.

Usage:
    python3 scheduler.py --instance instance.json --output output.json --time-budget SECONDS

Approach: construct an initial sequence with the ATCS (Apparent Tardiness
Cost with Setups) dispatch rule, improve it with adjacent-swap and
reinsertion local search, then spend the remaining time budget on
simulated-annealing restarts, keeping the best sequence found.
"""
import argparse
import json
import math
import random
import time


def sequence_objective(order, jobs_by_idx, setup_matrix, initial_setup):
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


def atcs_construct(jobs_by_idx, n, setup_matrix, initial_setup, k1=2.0, k2=2.0):
    remaining = set(range(n))
    p_bar = sum(jobs_by_idx[i]["proc_time"] for i in range(n)) / n
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
    return order


def local_search_improve(order, jobs_by_idx, setup_matrix, initial_setup, max_iters=2000, deadline=None):
    order = list(order)
    n = len(order)
    best_obj = sequence_objective(order, jobs_by_idx, setup_matrix, initial_setup)
    improved = True
    iters = 0
    while improved and iters < max_iters:
        if deadline is not None and time.time() > deadline:
            break
        improved = False
        iters += 1
        for i in range(n):
            if deadline is not None and i % 10 == 0 and time.time() > deadline:
                return order, best_obj
            for j in range(i + 1, n):
                cand = order[:]
                cand[i], cand[j] = cand[j], cand[i]
                obj = sequence_objective(cand, jobs_by_idx, setup_matrix, initial_setup)
                if obj < best_obj - 1e-9:
                    order, best_obj = cand, obj
                    improved = True
        for i in range(n):
            if deadline is not None and i % 10 == 0 and time.time() > deadline:
                return order, best_obj
            job = order[i]
            rest = order[:i] + order[i + 1:]
            for pos in range(n):
                cand = rest[:pos] + [job] + rest[pos:]
                obj = sequence_objective(cand, jobs_by_idx, setup_matrix, initial_setup)
                if obj < best_obj - 1e-9:
                    order, best_obj = cand, obj
                    improved = True
    return order, best_obj


def sa_timeboxed(order, jobs_by_idx, setup_matrix, initial_setup, seed, deadline, max_iters,
                  t_start=500.0, t_end=0.5):
    rng = random.Random(seed)
    n = len(order)
    cur = list(order)
    cur_obj = sequence_objective(cur, jobs_by_idx, setup_matrix, initial_setup)
    best, best_obj = list(cur), cur_obj

    for it in range(max_iters):
        if it % 2000 == 0 and time.time() > deadline:
            break
        frac = it / max_iters
        temp = t_start * ((t_end / t_start) ** frac)

        cand = cur[:]
        if rng.random() < 0.5:
            i, j = rng.sample(range(n), 2)
            cand[i], cand[j] = cand[j], cand[i]
        else:
            i = rng.randrange(n)
            j = rng.randrange(n)
            job = cand.pop(i)
            cand.insert(j, job)

        cand_obj = sequence_objective(cand, jobs_by_idx, setup_matrix, initial_setup)
        delta = cand_obj - cur_obj
        if delta < 0 or rng.random() < math.exp(-delta / max(temp, 1e-9)):
            cur, cur_obj = cand, cand_obj
            if cur_obj < best_obj:
                best, best_obj = list(cur), cur_obj

    return best, best_obj


def solve(jobs_by_idx, n, setup_matrix, initial_setup, time_budget_sec):
    t0 = time.time()
    # reserve a safety margin so we always have time to write output
    hard_deadline = t0 + max(time_budget_sec - 3.0, 0.5)

    order = atcs_construct(jobs_by_idx, n, setup_matrix, initial_setup)
    order, best_obj = local_search_improve(order, jobs_by_idx, setup_matrix, initial_setup,
                                            deadline=hard_deadline)
    best = list(order)

    restart_seed = 0
    while time.time() < hard_deadline:
        remaining = hard_deadline - time.time()
        if remaining < 0.3:
            break
        rng = random.Random(1000 + restart_seed)
        if restart_seed == 0:
            start_order = best
        else:
            start_order = list(range(n))
            rng.shuffle(start_order)

        iters = min(400000, max(20000, int(remaining * 60000)))
        cand, cand_obj = sa_timeboxed(start_order, jobs_by_idx, setup_matrix, initial_setup,
                                       seed=2000 + restart_seed, deadline=hard_deadline, max_iters=iters)
        if cand_obj < best_obj:
            best, best_obj = cand, cand_obj
        restart_seed += 1

    return best, best_obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--time-budget", required=True, type=float)
    args = ap.parse_args()

    t_start = time.time()
    with open(args.instance) as f:
        instance = json.load(f)

    jobs = instance["jobs"]
    n = len(jobs)
    jobs_by_idx = {i: jobs[i] for i in range(n)}
    setup_matrix = instance["setup_matrix"]
    initial_setup = instance["initial_setup"]

    elapsed_loading = time.time() - t_start
    remaining_budget = max(args.time_budget - elapsed_loading, 1.0)

    order, obj = solve(jobs_by_idx, n, setup_matrix, initial_setup, remaining_budget)

    sequence = [jobs_by_idx[i]["job_id"] for i in order]
    with open(args.output, "w") as f:
        json.dump({"sequence": sequence}, f)


if __name__ == "__main__":
    main()
