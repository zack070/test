import random
import math
from model import objective


def sa(items, pairs, budget, seed, iters=200000, t_start=50.0, t_end=0.05):
    n = len(items)
    rng = random.Random(seed)

    # start from a feasible greedy-ish random solution
    selection = [0] * n
    cost = 0.0
    order = list(range(n))
    rng.shuffle(order)
    for i in order:
        if rng.random() < 0.5 and cost + items[i]["cost"] <= budget:
            selection[i] = 1
            cost += items[i]["cost"]

    cur_obj, _ = objective(selection, items, pairs, budget)
    best, best_obj = selection[:], cur_obj

    for it in range(iters):
        frac = it / iters
        temp = t_start * ((t_end / t_start) ** frac)

        cand = selection[:]
        move = rng.random()
        if move < 0.7:
            i = rng.randrange(n)
            cand[i] = 1 - cand[i]
        else:
            i, j = rng.sample(range(n), 2)
            cand[i], cand[j] = cand[j], cand[i]

        cand_obj, feasible = objective(cand, items, pairs, budget)
        if not feasible:
            continue
        delta = cand_obj - cur_obj
        if delta > 0 or rng.random() < math.exp(delta / max(temp, 1e-9)):
            selection, cur_obj = cand, cand_obj
            if cur_obj > best_obj:
                best, best_obj = selection[:], cur_obj

    return best, best_obj


def sa_multi_restart(items, pairs, budget, n_restarts=4, iters=150000):
    best, best_obj = None, -1e18
    for r in range(n_restarts):
        sel, obj = sa(items, pairs, budget, seed=1000 + r, iters=iters)
        if obj > best_obj:
            best, best_obj = sel, obj
    return best, best_obj
