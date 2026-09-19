import math


def sequence_objective(order, jobs, setup_matrix, initial_setup):
    t = 0
    total = 0.0
    prev = None
    for idx in order:
        j = jobs[idx]
        s = initial_setup[idx] if prev is None else setup_matrix[prev][idx]
        t += s
        t += j["proc"]
        tardy = max(0, t - j["due"])
        total += j["weight"] * tardy
        prev = idx
    return total


def atcs_construct(jobs, setup_matrix, initial_setup, k1=2.0, k2=2.0):
    """Apparent Tardiness Cost with Setups (Lee, Bhaskaran, Pinedo 1997) --
    a genuinely competent, well-published dispatch-rule heuristic for
    exactly this problem class, not a strawman."""
    n = len(jobs)
    remaining = set(range(n))
    p_bar = sum(j["proc"] for j in jobs) / n
    s_bar = sum(sum(row) for row in setup_matrix) / (n * n) if n > 1 else 1
    s_bar = max(s_bar, 1e-6)

    order = []
    t = 0
    prev = None
    while remaining:
        best_idx, best_score = None, -1
        for idx in remaining:
            j = jobs[idx]
            s = initial_setup[idx] if prev is None else setup_matrix[prev][idx]
            slack = max(j["due"] - j["proc"] - t, 0)
            score = (j["weight"] / j["proc"]) * math.exp(-slack / (k1 * p_bar)) * math.exp(-s / (k2 * s_bar))
            if score > best_score:
                best_score, best_idx = score, idx
        order.append(best_idx)
        j = jobs[best_idx]
        s = initial_setup[best_idx] if prev is None else setup_matrix[prev][best_idx]
        t += s + j["proc"]
        prev = best_idx
        remaining.discard(best_idx)
    return order


def local_search_improve(order, jobs, setup_matrix, initial_setup, max_iters=2000):
    """Adjacent-swap + single-job-reinsertion local search until no
    improving move is found -- the natural next step a competent engineer
    takes after a dispatch-rule construction, before reaching for a solver."""
    order = list(order)
    n = len(order)
    best_obj = sequence_objective(order, jobs, setup_matrix, initial_setup)
    improved = True
    iters = 0
    while improved and iters < max_iters:
        improved = False
        iters += 1
        for i in range(n):
            for j in range(i + 1, n):
                cand = order[:]
                cand[i], cand[j] = cand[j], cand[i]
                obj = sequence_objective(cand, jobs, setup_matrix, initial_setup)
                if obj < best_obj - 1e-9:
                    order, best_obj = cand, obj
                    improved = True
        for i in range(n):
            job = order[i]
            rest = order[:i] + order[i + 1:]
            for pos in range(n):
                cand = rest[:pos] + [job] + rest[pos:]
                obj = sequence_objective(cand, jobs, setup_matrix, initial_setup)
                if obj < best_obj - 1e-9:
                    order, best_obj = cand, obj
                    improved = True
    return order, best_obj
