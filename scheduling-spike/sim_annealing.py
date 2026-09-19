import random
from heuristic import sequence_objective


def simulated_annealing(order, jobs, setup_matrix, initial_setup, seed=0,
                         iters=200000, t_start=500.0, t_end=0.5):
    rng = random.Random(seed)
    n = len(order)
    cur = list(order)
    cur_obj = sequence_objective(cur, jobs, setup_matrix, initial_setup)
    best, best_obj = list(cur), cur_obj

    for it in range(iters):
        frac = it / iters
        temp = t_start * ((t_end / t_start) ** frac)

        move = rng.random()
        cand = cur[:]
        if move < 0.5:
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
