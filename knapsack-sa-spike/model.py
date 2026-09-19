import random

N_ITEMS = 60
N_PAIRS = 8  # linked pairs, individually bad, jointly good


def make_instance(seed):
    rng = random.Random(seed)
    items = []
    for i in range(N_ITEMS):
        cost = rng.uniform(10, 100)
        # ordinary items: value/cost ratio varies, some good some bad standalone
        value = cost * rng.uniform(0.5, 1.5)
        items.append({"id": i, "cost": cost, "value": value})

    # designate some items as linked pairs: individually bad (value < cost),
    # but a bonus makes the pair jointly good
    pool = list(range(N_ITEMS))
    rng.shuffle(pool)
    pairs = []
    for k in range(N_PAIRS):
        a, b = pool[2 * k], pool[2 * k + 1]
        # make both individually bad standalone
        items[a]["value"] = items[a]["cost"] * rng.uniform(0.5, 0.8)
        items[b]["value"] = items[b]["cost"] * rng.uniform(0.5, 0.8)
        # bonus large enough that jointly selecting is a good deal
        standalone_deficit = (items[a]["cost"] - items[a]["value"]) + (items[b]["cost"] - items[b]["value"])
        bonus = standalone_deficit + max(items[a]["cost"], items[b]["cost"]) * rng.uniform(0.4, 0.7)
        pairs.append((a, b, bonus))

    total_cost = sum(it["cost"] for it in items)
    budget = total_cost * 0.4  # tight enough to force real tradeoffs
    return items, pairs, budget


def objective(selection, items, pairs, budget):
    """selection: list of 0/1 per item. Returns (net_value, feasible)."""
    cost = sum(items[i]["cost"] for i in range(len(items)) if selection[i])
    if cost > budget:
        return -1e18, False
    value = sum(items[i]["value"] for i in range(len(items)) if selection[i])
    for a, b, bonus in pairs:
        if selection[a] and selection[b]:
            value += bonus
    return value, True
