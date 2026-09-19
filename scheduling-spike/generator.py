import random

N_FAMILIES = 6

def make_instance(n_jobs, seed):
    rng = random.Random(seed)
    # family "positions" on a cycle -- switching to a nearby family is cheap,
    # to a distant one is expensive (mimics real color/tooling changeover
    # matrices, e.g. light-to-dark paint booths, chemical batch trains).
    family_pos = {f: rng.uniform(0, 10) for f in range(N_FAMILIES)}

    def family_setup(fi, fj):
        if fi == fj:
            return rng.randint(2, 5)
        dist = abs(family_pos[fi] - family_pos[fj])
        dist = min(dist, 10 - dist)  # cyclic distance
        return int(15 + dist * 12 + rng.randint(-3, 3))

    setup_cache = {}
    def setup(fi, fj):
        key = (fi, fj)
        if key not in setup_cache:
            setup_cache[key] = max(1, family_setup(fi, fj))
        return setup_cache[key]

    jobs = []
    for j in range(n_jobs):
        fam = rng.randrange(N_FAMILIES)
        proc = rng.randint(10, 40)
        weight = rng.choice([1, 1, 1, 2, 2, 3, 5])
        jobs.append({"id": j, "family": fam, "proc": proc, "weight": weight})

    # due dates: derive from a rough "if processed in family-clustered order"
    # estimate, then perturb, so some due dates are tight and some loose --
    # avoids a degenerate instance where everything is trivially on time or
    # everything is trivially late.
    total_work = sum(j["proc"] for j in jobs) + n_jobs * 15
    for j in jobs:
        slack_factor = rng.uniform(0.35, 0.9)
        j["due"] = int(total_work * slack_factor * rng.uniform(0.6, 1.0) / 1.0) + rng.randint(0, 40)

    setup_matrix = [[setup(jobs[i]["family"], jobs[j]["family"]) if i != j else 0
                     for j in range(n_jobs)] for i in range(n_jobs)]
    initial_setup = [setup(rng.randrange(N_FAMILIES), jobs[j]["family"]) for j in range(n_jobs)]

    return jobs, setup_matrix, initial_setup
