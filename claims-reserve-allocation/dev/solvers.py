"""Three reference policies, in increasing sophistication:

  naive_greedy      -- rank by per-claim savings, greedily fill budget.
                       Ignores correlation AND is not even knapsack-optimal.
  ev_optimal        -- exact 0/1 knapsack (maximize expected savings s.t.
                       budget) via MILP. Optimal for E[cost] alone; blind to
                       CVaR/cluster concentration.
  risk_aware        -- scenario-based MILP with a Rockafellar-Uryasev CVaR
                       linearization. Trades a little expected value to
                       reduce concentrated cluster tail risk.

All return Dict[claim_id, 0|1].
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

sys.path.insert(0, os.path.dirname(__file__))
from model import Claim, ModelConfig, expected_deferred_cost  # noqa: E402


def naive_greedy(claims: Sequence[Claim], cfg: ModelConfig) -> Dict[str, int]:
    scored = []
    for c in claims:
        savings = expected_deferred_cost(c, cfg) - c.settlement_offer_usd
        ratio = savings / c.settlement_offer_usd if c.settlement_offer_usd > 0 else -1.0
        scored.append((ratio, c))
    scored.sort(key=lambda t: t[0], reverse=True)

    decisions = {c.claim_id: 0 for c in claims}
    remaining = cfg.budget_usd
    for ratio, c in scored:
        if ratio <= 0:
            continue
        if c.settlement_offer_usd <= remaining:
            decisions[c.claim_id] = 1
            remaining -= c.settlement_offer_usd
    return decisions


def ev_optimal(claims: Sequence[Claim], cfg: ModelConfig) -> Dict[str, int]:
    n = len(claims)
    savings = np.array([expected_deferred_cost(c, cfg) - c.settlement_offer_usd for c in claims])
    offers = np.array([c.settlement_offer_usd for c in claims])

    c_obj = -savings  # minimize -savings == maximize savings
    budget_constraint = LinearConstraint(offers.reshape(1, -1), -np.inf, cfg.budget_usd)
    bounds = Bounds(0, 1)
    integrality = np.ones(n)

    res = milp(c_obj, constraints=[budget_constraint], bounds=bounds, integrality=integrality)
    x = np.round(res.x).astype(int)
    return {c.claim_id: int(x[i]) for i, c in enumerate(claims)}


def _simulate_deferred_cost_matrix(
    claims: Sequence[Claim], cfg: ModelConfig, rng: np.random.Generator, n_scenarios: int,
) -> np.ndarray:
    """Returns (n_claims, n_scenarios) matrix of what each claim would cost
    if deferred, under each scenario, respecting cluster correlation."""
    cluster_ids = sorted({c.incident_cluster_id for c in claims})
    cluster_index = {cid: i for i, cid in enumerate(cluster_ids)}
    z = rng.lognormal(
        mean=cfg.cluster_lognormal_mu, sigma=cfg.cluster_lognormal_sigma,
        size=(len(cluster_ids), n_scenarios),
    )
    d = np.zeros((len(claims), n_scenarios))
    for i, c in enumerate(claims):
        t = cfg.claim_types[c.claim_type]
        base = rng.lognormal(mean=t.lognormal_mu, sigma=t.lognormal_sigma, size=n_scenarios)
        litigated = rng.random(n_scenarios) < t.litigation_prob
        escalation = np.where(litigated, t.escalation_factor, 1.0)
        cz = z[cluster_index[c.incident_cluster_id], :]
        d[i, :] = base * cz * escalation * cfg.deferral_factor
    return d


def risk_aware(
    claims: Sequence[Claim], cfg: ModelConfig, rng: np.random.Generator, n_scenarios: int = 300,
) -> Dict[str, int]:
    n = len(claims)
    offers = np.array([c.settlement_offer_usd for c in claims])
    d = _simulate_deferred_cost_matrix(claims, cfg, rng, n_scenarios)  # (n, S)

    a = offers.reshape(-1, 1) - d  # (n, S): contribution delta if settled vs deferred
    e = d.sum(axis=0)  # (S,): baseline cost if everything deferred
    mean_a = a.mean(axis=1)  # (n,)

    alpha = cfg.risk_alpha
    lam = cfg.risk_lambda
    S = n_scenarios

    # variables: x (n binary), eta (1 free), u (S, >= 0)
    n_vars = n + 1 + S
    c_obj = np.zeros(n_vars)
    c_obj[:n] = mean_a
    c_obj[n] = lam  # eta coefficient
    c_obj[n + 1:] = lam / ((1 - alpha) * S)  # u_s coefficients

    # Budget constraint: sum offer_i * x_i <= budget
    row_budget = np.zeros(n_vars)
    row_budget[:n] = offers
    budget_constraint = LinearConstraint(row_budget, -np.inf, cfg.budget_usd)

    # CVaR constraints: -sum_i a_{i,s} x_i + u_s + eta >= e_s   for each s
    rows_cvar = np.zeros((S, n_vars))
    rows_cvar[:, :n] = -a.T  # (S, n)
    rows_cvar[np.arange(S), n] = 1.0  # eta
    rows_cvar[np.arange(S), n + 1:] = np.eye(S)  # u_s
    cvar_constraint = LinearConstraint(rows_cvar, e, np.inf)

    lower = np.concatenate([np.zeros(n), [-np.inf], np.zeros(S)])
    upper = np.concatenate([np.ones(n), [np.inf], np.full(S, np.inf)])
    bounds = Bounds(lower, upper)
    integrality = np.concatenate([np.ones(n), [0], np.zeros(S)])

    res = milp(
        c_obj, constraints=[budget_constraint, cvar_constraint],
        bounds=bounds, integrality=integrality,
        options={"time_limit": 120},
    )
    x = np.round(res.x[:n]).astype(int)
    return {c.claim_id: int(x[i]) for i, c in enumerate(claims)}
