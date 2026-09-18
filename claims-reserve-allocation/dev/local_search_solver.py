"""Independent second implementation of a risk-aware policy, using a
completely different algorithm (randomized local search, not MILP) to
cross-check that solvers.risk_aware's measured advantage over ev_optimal
is real and not an artifact of the objective/model code shared between
the generator and the MILP solver.

Starts from the ev_optimal decision set (feasible, EV-good) and repeatedly
tries single-claim settle<->defer flips that keep the budget feasible,
accepting a flip if it improves a shared-random-seed Monte Carlo estimate
of the objective. Shared random seed per iteration (common random numbers)
so two candidate decision sets are compared on the same draws, reducing
noise in the accept/reject decision.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Sequence

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from model import Claim, ModelConfig, budget_used, objective  # noqa: E402


def local_search(
    claims: Sequence[Claim],
    cfg: ModelConfig,
    initial: Dict[str, int],
    rng: np.random.Generator,
    n_iterations: int = 400,
    eval_paths: int = 3000,
) -> Dict[str, int]:
    current = dict(initial)
    current_used = budget_used(claims, current)
    ids = [c.claim_id for c in claims]
    id_to_claim = {c.claim_id: c for c in claims}

    common_seed = int(rng.integers(0, 2**31))
    current_obj = objective(claims, current, cfg, np.random.default_rng(common_seed), eval_paths)["objective"]

    for it in range(n_iterations):
        i, j = rng.choice(len(ids), size=2, replace=False)
        a, b = ids[i], ids[j]
        if current[a] == current[b]:
            continue  # flipping two claims with the same decision is a no-op pair; try a single flip instead
        candidate = dict(current)
        candidate[a], candidate[b] = candidate[b], candidate[a]
        cand_used = budget_used(claims, candidate)
        if cand_used > cfg.budget_usd + 1e-6:
            continue

        seed = common_seed + it + 1
        cand_obj = objective(claims, candidate, cfg, np.random.default_rng(seed), eval_paths)["objective"]
        cur_obj_same_draws = objective(claims, current, cfg, np.random.default_rng(seed), eval_paths)["objective"]
        if cand_obj < cur_obj_same_draws:
            current = candidate
            current_used = cand_used

    return current
