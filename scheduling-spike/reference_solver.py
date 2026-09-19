"""Time-budgeted reference solver: ATCS construction, then simulated
annealing with restarts until the wall-clock budget runs out. This is the
candidate reference solution -- must beat both a stock CP-SAT run and the
ATCS+local-search baseline within the SAME time budget the real verifier
will give any submission."""
import random
import time
from heuristic import atcs_construct, local_search_improve, sequence_objective


def solve(jobs, setup_matrix, initial_setup, time_budget_sec):
    t0 = time.time()
    n = len(jobs)

    order = atcs_construct(jobs, setup_matrix, initial_setup)
    order, best_obj = local_search_improve(order, jobs, setup_matrix, initial_setup)
    best = list(order)

    restart_seed = 0
    while time.time() - t0 < time_budget_sec:
        remaining = time_budget_sec - (time.time() - t0)
        if remaining < 0.5:
            break
        rng = random.Random(1000 + restart_seed)
        if restart_seed == 0:
            start_order = best
        else:
            start_order = list(range(n))
            rng.shuffle(start_order)

        iters = min(400000, max(20000, int(remaining * 60000)))
        cand, cand_obj = _sa_timeboxed(start_order, jobs, setup_matrix, initial_setup,
                                        seed=2000 + restart_seed,
                                        deadline=t0 + time_budget_sec, max_iters=iters)
        if cand_obj < best_obj:
            best, best_obj = cand, cand_obj
        restart_seed += 1

    return best, best_obj


def _sa_timeboxed(order, jobs, setup_matrix, initial_setup, seed, deadline, max_iters,
                   t_start=500.0, t_end=0.5):
    rng = random.Random(seed)
    n = len(order)
    cur = list(order)
    cur_obj = sequence_objective(cur, jobs, setup_matrix, initial_setup)
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

        cand_obj = sequence_objective(cand, jobs, setup_matrix, initial_setup)
        delta = cand_obj - cur_obj
        if delta < 0 or rng.random() < pow(2.71828, -delta / max(temp, 1e-9)):
            cur, cur_obj = cand, cand_obj
            if cur_obj < best_obj:
                best, best_obj = list(cur), cur_obj

    return best, best_obj
