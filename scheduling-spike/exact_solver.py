from ortools.sat.python import cp_model
import time


def solve_exact(jobs, setup_matrix, initial_setup, time_limit_sec=120):
    n = len(jobs)
    model = cp_model.CpModel()

    horizon = sum(j["proc"] for j in jobs) + sum(max(row) for row in setup_matrix) + max(initial_setup) + 10

    # nodes: 0 = depot, 1..n = jobs (job j -> node j+1)
    arcs = []
    lits = {}
    for i in range(n + 1):
        for j in range(n + 1):
            if i == j:
                continue
            if i == 0 and j == 0:
                continue
            lit = model.NewBoolVar(f"x_{i}_{j}")
            lits[(i, j)] = lit
            arcs.append((i, j, lit))
    model.AddCircuit(arcs)

    start = [model.NewIntVar(0, horizon, f"start_{j}") for j in range(n)]

    for j in range(n):
        node = j + 1
        lit0 = lits[(0, node)]
        model.Add(start[j] >= initial_setup[j]).OnlyEnforceIf(lit0)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            node_i, node_j = i + 1, j + 1
            lit = lits[(node_i, node_j)]
            model.Add(start[j] >= start[i] + jobs[i]["proc"] + setup_matrix[i][j]).OnlyEnforceIf(lit)

    tardy = []
    for j in range(n):
        completion = start[j] + jobs[j]["proc"]
        t = model.NewIntVar(0, horizon, f"tardy_{j}")
        model.Add(t >= completion - jobs[j]["due"])
        model.Add(t >= 0)
        tardy.append(t)

    model.Minimize(sum(jobs[j]["weight"] * tardy[j] for j in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_sec
    solver.parameters.num_search_workers = 8
    t0 = time.time()
    status = solver.Solve(model)
    elapsed = time.time() - t0

    return {
        "status": solver.StatusName(status),
        "objective": solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        "best_bound": solver.BestObjectiveBound(),
        "elapsed_sec": elapsed,
        "proven_optimal": status == cp_model.OPTIMAL,
    }
