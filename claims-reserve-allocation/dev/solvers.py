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


def _build_pairs(claims: Sequence[Claim]) -> List[tuple]:
    """Each linked pair appears once, as (index_i, index_j)."""
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


def risk_aware(
    claims: Sequence[Claim], cfg: ModelConfig, rng: np.random.Generator, n_scenarios: int = 300,
) -> Dict[str, int]:
    """Scenario-based MILP with a Rockafellar-Uryasev CVaR linearization,
    PLUS an AND-linearization (w_p = x_i * x_j) for each linked-claim pair,
    so the linked-settlement discount is only realized when both members
    of a pair are jointly settled. Without this, the solver would only
    ever find the discount by accident (it's invisible to any per-claim
    marginal-value ranking, since the offer used is fixed per claim)."""
    n = len(claims)
    offers = np.array([c.settlement_offer_usd for c in claims])
    pairs = _build_pairs(claims)
    P = len(pairs)
    discount = cfg.linked_settlement_discount

    d = _simulate_deferred_cost_matrix(claims, cfg, rng, n_scenarios)  # (n, S)
    a = offers.reshape(-1, 1) - d  # (n, S): contribution delta if settled vs deferred
    e = d.sum(axis=0)  # (S,): baseline cost if everything deferred
    mean_a = a.mean(axis=1)  # (n,)

    alpha = cfg.risk_alpha
    lam = cfg.risk_lambda
    S = n_scenarios

    # variables: x (n binary), eta (1 free), u (S, >= 0), w (P binary)
    n_vars = n + 1 + S + P
    x_sl, eta_i, u_sl, w_sl = slice(0, n), n, slice(n + 1, n + 1 + S), slice(n + 1 + S, n_vars)

    pair_amt = np.array([discount * (offers[i] + offers[j]) for i, j in pairs]) if P else np.zeros(0)

    c_obj = np.zeros(n_vars)
    c_obj[x_sl] = mean_a
    c_obj[eta_i] = lam
    c_obj[u_sl] = lam / ((1 - alpha) * S)
    c_obj[w_sl] = -pair_amt  # settling both members of a pair reduces cost

    # Budget: sum offer_i*x_i - sum discount*(offer_i+offer_j)*w_p <= budget
    row_budget = np.zeros(n_vars)
    row_budget[x_sl] = offers
    row_budget[w_sl] = -pair_amt
    budget_constraint = LinearConstraint(row_budget, -np.inf, cfg.budget_usd)

    # CVaR: u_s + eta - sum_i a_{i,s} x_i + sum_p pair_amt_p * w_p >= e_s
    rows_cvar = np.zeros((S, n_vars))
    rows_cvar[:, x_sl] = -a.T
    rows_cvar[np.arange(S), eta_i] = 1.0
    rows_cvar[:, u_sl] = np.eye(S)
    if P:
        rows_cvar[:, w_sl] = pair_amt.reshape(1, -1)
    cvar_constraint = LinearConstraint(rows_cvar, e, np.inf)

    constraints = [budget_constraint, cvar_constraint]
    if P:
        # AND-linearization: w_p <= x_i, w_p <= x_j, w_p >= x_i + x_j - 1
        rows_and = np.zeros((3 * P, n_vars))
        lb_and = np.full(3 * P, -np.inf)
        ub_and = np.zeros(3 * P)
        for k, (i, j) in enumerate(pairs):
            rows_and[3 * k, x_sl.start + i] = -1; rows_and[3 * k, n + 1 + S + k] = 1        # w - x_i <= 0
            rows_and[3 * k + 1, x_sl.start + j] = -1; rows_and[3 * k + 1, n + 1 + S + k] = 1  # w - x_j <= 0
            rows_and[3 * k + 2, x_sl.start + i] = 1; rows_and[3 * k + 2, x_sl.start + j] = 1
            rows_and[3 * k + 2, n + 1 + S + k] = -1                                          # x_i+x_j-w <= 1
            ub_and[3 * k + 2] = 1.0
        constraints.append(LinearConstraint(rows_and, lb_and, ub_and))

    lower = np.concatenate([np.zeros(n), [-np.inf], np.zeros(S), np.zeros(P)])
    upper = np.concatenate([np.ones(n), [np.inf], np.full(S, np.inf), np.ones(P)])
    bounds = Bounds(lower, upper)
    integrality = np.concatenate([np.ones(n), [0], np.zeros(S), np.ones(P)])

    res = milp(
        c_obj, constraints=constraints,
        bounds=bounds, integrality=integrality,
        options={"time_limit": 180},
    )
    x = np.round(res.x[x_sl]).astype(int)
    return {c.claim_id: int(x[i]) for i, c in enumerate(claims)}
