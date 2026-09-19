import random

N_FAMILIES = 6


def _family_setup_table(rng):
    family_pos = {f: rng.uniform(0, 10) for f in range(N_FAMILIES)}

    def raw(fi, fj):
        if fi == fj:
            return rng.randint(2, 5)
        dist = abs(family_pos[fi] - family_pos[fj])
        dist = min(dist, 10 - dist)
        return max(1, int(15 + dist * 12 + rng.randint(-3, 3)))

    matrix = [[raw(i, j) for j in range(N_FAMILIES)] for i in range(N_FAMILIES)]
    return matrix


def make_instance(n_jobs, seed, id_offset=0):
    rng = random.Random(seed)
    setup_matrix = _family_setup_table(rng)
    initial_setup = [setup_matrix[rng.randrange(N_FAMILIES)][f] for f in range(N_FAMILIES)]

    jobs = []
    for i in range(n_jobs):
        fam = rng.randrange(N_FAMILIES)
        proc = rng.randint(10, 40)
        weight = rng.choice([1, 1, 1, 2, 2, 3, 5])
        jobs.append({
            "job_id": f"J{i + id_offset:03d}",
            "family": fam,
            "proc_time": proc,
            "weight": weight,
        })

    total_work = sum(j["proc_time"] for j in jobs) + n_jobs * 15
    for j in jobs:
        slack_factor = rng.uniform(0.35, 0.9)
        j["due_date"] = int(total_work * slack_factor * rng.uniform(0.6, 1.0)) + rng.randint(0, 40)

    return {"jobs": jobs, "setup_matrix": setup_matrix, "initial_setup": initial_setup}


def make_worked_example():
    """Tiny, fully hand-checkable instance: 4 jobs, 2 families."""
    setup_matrix = [
        [3, 20],
        [25, 4],
    ]
    initial_setup = [8, 30]
    jobs = [
        {"job_id": "A", "family": 0, "proc_time": 10, "due_date": 15, "weight": 2},
        {"job_id": "B", "family": 1, "proc_time": 8, "due_date": 20, "weight": 3},
        {"job_id": "C", "family": 0, "proc_time": 12, "due_date": 55, "weight": 1},
        {"job_id": "D", "family": 1, "proc_time": 6, "due_date": 60, "weight": 4},
    ]
    return {"jobs": jobs, "setup_matrix": setup_matrix, "initial_setup": initial_setup}
