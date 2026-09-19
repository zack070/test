from model import objective


def greedy_swap(items, pairs, budget):
    n = len(items)
    order = sorted(range(n), key=lambda i: items[i]["value"] / items[i]["cost"], reverse=True)
    selection = [0] * n
    cost = 0.0
    for i in order:
        if cost + items[i]["cost"] <= budget:
            selection[i] = 1
            cost += items[i]["cost"]

    best_obj, _ = objective(selection, items, pairs, budget)
    improved = True
    while improved:
        improved = False
        for i in range(n):
            for j in range(n):
                if i == j or selection[i] == selection[j]:
                    continue
                cand = selection[:]
                cand[i], cand[j] = cand[j], cand[i]
                obj, feasible = objective(cand, items, pairs, budget)
                if feasible and obj > best_obj + 1e-9:
                    selection, best_obj = cand, obj
                    improved = True
    return selection, best_obj
