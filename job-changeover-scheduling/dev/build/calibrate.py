import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "solution"))

from generator import make_instance
from exact_solver import solve_exact
import scheduler as ref  # solution/scheduler.py

TIME_BUDGET = 180


def run_one(seed, n=45, id_offset=0):
    inst = make_instance(n, seed=seed, id_offset=id_offset)
    jobs = inst["jobs"]
    jobs_by_idx = {i: jobs[i] for i in range(n)}
    setup_matrix = inst["setup_matrix"]
    initial_setup = inst["initial_setup"]

    order = ref.atcs_construct(jobs_by_idx, n, setup_matrix, initial_setup)
    order, heur_obj = ref.local_search_improve(order, jobs_by_idx, setup_matrix, initial_setup)
    print(f"[seed={seed}] ATCS+local-search (heuristic baseline): {heur_obj:.0f}", flush=True)

    t0 = time.time()
    ref_order, ref_obj = ref.solve(jobs_by_idx, n, setup_matrix, initial_setup, TIME_BUDGET)
    print(f"[seed={seed}] reference solver ({TIME_BUDGET}s budget, {time.time()-t0:.0f}s actual): {ref_obj:.0f}", flush=True)

    cpsat = solve_exact(jobs, setup_matrix, initial_setup, time_limit_sec=TIME_BUDGET)
    print(f"[seed={seed}] CP-SAT ({TIME_BUDGET}s budget): status={cpsat['status']} "
          f"objective={cpsat['objective']} proven_optimal={cpsat['proven_optimal']}", flush=True)

    return {
        "seed": seed, "instance": inst,
        "heuristic_obj": heur_obj, "reference_obj": ref_obj,
        "reference_sequence": [jobs_by_idx[i]["job_id"] for i in ref_order],
        "cpsat_obj": cpsat["objective"],
    }


if __name__ == "__main__":
    seeds_and_offsets = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [[7001, 0], [7002, 200]]
    results = []
    for seed, offset in seeds_and_offsets:
        results.append(run_one(seed, id_offset=offset))
        print()
    with open("/tmp/calibration_results.json", "w") as f:
        json.dump(results, f)
    print("saved to /tmp/calibration_results.json")
