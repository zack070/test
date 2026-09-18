"""
Reference solution: a scenario-based MILP (Rockafellar-Uryasev CVaR
linearization) that jointly optimizes expected cost and tail risk, unlike
a plain expected-value knapsack. See dev/solvers.py:risk_aware for the
same logic developed during calibration.

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


def solve(claims: List[Claim], cfg: Dict, n_scenarios: int = N_SCENARIOS) -> Dict[str, int]:
    rng = np.random.default_rng(SOLVER_SEED)
    n = len(claims)
    offers = np.array([c.settlement_offer_usd for c in claims])
    d = _simulate_deferred_cost_matrix(claims, cfg, rng, n_scenarios)

    a = offers.reshape(-1, 1) - d
    e = d.sum(axis=0)
    mean_a = a.mean(axis=1)

    alpha = cfg["risk_alpha"]
    lam = cfg["risk_lambda"]
    budget = cfg["budget_usd"]
    S = n_scenarios

    n_vars = n + 1 + S
    c_obj = np.zeros(n_vars)
    c_obj[:n] = mean_a
    c_obj[n] = lam
    c_obj[n + 1:] = lam / ((1 - alpha) * S)

    row_budget = np.zeros(n_vars)
    row_budget[:n] = offers
    budget_constraint = LinearConstraint(row_budget, -np.inf, budget)

    rows_cvar = np.zeros((S, n_vars))
    rows_cvar[:, :n] = -a.T
    rows_cvar[np.arange(S), n] = 1.0
    rows_cvar[np.arange(S), n + 1:] = np.eye(S)
    cvar_constraint = LinearConstraint(rows_cvar, e, np.inf)

    lower = np.concatenate([np.zeros(n), [-np.inf], np.zeros(S)])
    upper = np.concatenate([np.ones(n), [np.inf], np.full(S, np.inf)])
    bounds = Bounds(lower, upper)
    integrality = np.concatenate([np.ones(n), [0], np.zeros(S)])

    res = milp(
        c_obj, constraints=[budget_constraint, cvar_constraint],
        bounds=bounds, integrality=integrality, options={"time_limit": 90},
    )
    x = np.round(res.x[:n]).astype(int)
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
