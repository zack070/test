"""
Reference solution: a scenario-based MILP (Rockafellar-Uryasev CVaR
linearization) that jointly optimizes expected cost and tail risk, unlike
a plain expected-value knapsack. It also handles linked-claim pairs via
an AND-linearization (w_p = x_i * x_j), since the linked-settlement
discount is invisible to any per-claim marginal-value search -- it only
shows up once both members of a pair are considered together.
See dev/solvers.py:risk_aware for the same logic developed during
calibration.

Run it with: python3 policy.py <data_dir> <output_path>
"""
from __future__ import annotations

import csv
import json
import math
import sys
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

N_SCENARIOS = 2000
SOLVER_SEED = 20240917


@dataclass(frozen=True)
class ClaimTypeParams:
    mean_severity_usd: float
    severity_cv: float
    litigation_prob: float
    escalation_factor: float

    @property
    def lognormal_sigma(self) -> float:
        return math.sqrt(math.log(1.0 + self.severity_cv ** 2))

    @property
    def lognormal_mu(self) -> float:
        return math.log(self.mean_severity_usd) - 0.5 * self.lognormal_sigma ** 2


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim_type: str
    incident_cluster_id: str
    settlement_offer_usd: float
    linked_claim_id: str = ""


def load_portfolio(data_dir: str) -> Tuple[List[Claim], Dict]:
    with open(f"{data_dir}/config.json") as f:
        cfg = json.load(f)
    claims: List[Claim] = []
    with open(f"{data_dir}/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            claims.append(Claim(
                claim_id=r["claim_id"], claim_type=r["claim_type"],
                incident_cluster_id=r["incident_cluster_id"],
                settlement_offer_usd=float(r["settlement_offer_usd"]),
                linked_claim_id=r.get("linked_claim_id", "") or "",
            ))
    return claims, cfg


def _simulate_deferred_cost_matrix(
    claims: Sequence[Claim], cfg: Dict, rng: np.random.Generator, n_scenarios: int,
) -> np.ndarray:
    types = {name: ClaimTypeParams(**p) for name, p in cfg["claim_types"].items()}
    cluster_sigma = cfg["cluster_sigma"]
    deferral_factor = 1.0 + cfg["interest_rate_annual"] * cfg["deferral_years"]

    cluster_ids = sorted({c.incident_cluster_id for c in claims})
    cluster_index = {cid: i for i, cid in enumerate(cluster_ids)}
    z = rng.lognormal(mean=-0.5 * cluster_sigma ** 2, sigma=cluster_sigma,
                       size=(len(cluster_ids), n_scenarios))

    d = np.zeros((len(claims), n_scenarios))
    for i, c in enumerate(claims):
        t = types[c.claim_type]
        base = rng.lognormal(mean=t.lognormal_mu, sigma=t.lognormal_sigma, size=n_scenarios)
        litigated = rng.random(n_scenarios) < t.litigation_prob
        escalation = np.where(litigated, t.escalation_factor, 1.0)
        cz = z[cluster_index[c.incident_cluster_id], :]
        d[i, :] = base * cz * escalation * deferral_factor
    return d


def _build_pairs(claims: Sequence[Claim]) -> List[tuple]:
    index = {c.claim_id: i for i, c in enumerate(claims)}
    seen = set()
    pairs = []
    for i, c in enumerate(claims):
        if not c.linked_claim_id:
            continue
        j = index[c.linked_claim_id]
        key = tuple(sorted((i, j)))
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    return pairs


def solve(claims: List[Claim], cfg: Dict, n_scenarios: int = N_SCENARIOS) -> Dict[str, int]:
    rng = np.random.default_rng(SOLVER_SEED)
    n = len(claims)
    offers = np.array([c.settlement_offer_usd for c in claims])
    pairs = _build_pairs(claims)
    P = len(pairs)
    discount = cfg.get("linked_settlement_discount", 0.0)

    d = _simulate_deferred_cost_matrix(claims, cfg, rng, n_scenarios)
    a = offers.reshape(-1, 1) - d
    e = d.sum(axis=0)
    mean_a = a.mean(axis=1)

    alpha = cfg["risk_alpha"]
    lam = cfg["risk_lambda"]
    budget = cfg["budget_usd"]
    S = n_scenarios

    n_vars = n + 1 + S + P
    x_sl, eta_i, u_sl, w_sl = slice(0, n), n, slice(n + 1, n + 1 + S), slice(n + 1 + S, n_vars)

    pair_amt = np.array([discount * (offers[i] + offers[j]) for i, j in pairs]) if P else np.zeros(0)

    c_obj = np.zeros(n_vars)
    c_obj[x_sl] = mean_a
    c_obj[eta_i] = lam
    c_obj[u_sl] = lam / ((1 - alpha) * S)
    c_obj[w_sl] = -pair_amt

    row_budget = np.zeros(n_vars)
    row_budget[x_sl] = offers
    row_budget[w_sl] = -pair_amt
    budget_constraint = LinearConstraint(row_budget, -np.inf, budget)

    rows_cvar = np.zeros((S, n_vars))
    rows_cvar[:, x_sl] = -a.T
    rows_cvar[np.arange(S), eta_i] = 1.0
    rows_cvar[:, u_sl] = np.eye(S)
    if P:
        rows_cvar[:, w_sl] = pair_amt.reshape(1, -1)
    cvar_constraint = LinearConstraint(rows_cvar, e, np.inf)

    constraints = [budget_constraint, cvar_constraint]
    if P:
        rows_and = np.zeros((3 * P, n_vars))
        lb_and = np.full(3 * P, -np.inf)
        ub_and = np.zeros(3 * P)
        for k, (i, j) in enumerate(pairs):
            rows_and[3 * k, i] = -1; rows_and[3 * k, n + 1 + S + k] = 1
            rows_and[3 * k + 1, j] = -1; rows_and[3 * k + 1, n + 1 + S + k] = 1
            rows_and[3 * k + 2, i] = 1; rows_and[3 * k + 2, j] = 1
            rows_and[3 * k + 2, n + 1 + S + k] = -1
            ub_and[3 * k + 2] = 1.0
        constraints.append(LinearConstraint(rows_and, lb_and, ub_and))

    lower = np.concatenate([np.zeros(n), [-np.inf], np.zeros(S), np.zeros(P)])
    upper = np.concatenate([np.ones(n), [np.inf], np.full(S, np.inf), np.ones(P)])
    bounds = Bounds(lower, upper)
    integrality = np.concatenate([np.ones(n), [0], np.zeros(S), np.ones(P)])

    res = milp(
        c_obj, constraints=constraints,
        bounds=bounds, integrality=integrality, options={"time_limit": 180},
    )
    x = np.round(res.x[x_sl]).astype(int)
    return {c.claim_id: int(x[i]) for i, c in enumerate(claims)}


def run(data_dir: str) -> Dict:
    claims, cfg = load_portfolio(data_dir)
    decisions = solve(claims, cfg)
    return {"decisions": decisions}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 policy.py <data_dir> <output_path>", file=sys.stderr)
        sys.exit(1)
    report = run(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(report, f, indent=2)
    n_settled = sum(report["decisions"].values())
    print(f"wrote {sys.argv[2]}: settled {n_settled}/{len(report['decisions'])} claims")
