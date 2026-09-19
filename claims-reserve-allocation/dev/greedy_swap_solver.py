"""Replicates the reviewer-reported heuristic: greedy by simulated marginal
objective gain per dollar (using a precomputed, shared scenario matrix for
variance reduction), then 1-1 swaps. This is NOT a strawman -- it's meant
to test whether the disclosed model + a simple simulate-and-rank approach
already captures most of what the MILP reference captures.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Sequence

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from model import Claim, ModelConfig  # noqa: E402


def _scenario_matrix(claims: Sequence[Claim], cfg: ModelConfig, rng: np.random.Generator, n_scenarios: int) -> np.ndarray:
    cluster_ids = sorted({c.incident_cluster_id for c in claims})
    cidx = {cid: i for i, cid in enumerate(cluster_ids)}
    z = rng.lognormal(mean=cfg.cluster_lognormal_mu, sigma=cfg.cluster_lognormal_sigma,
                       size=(len(cluster_ids), n_scenarios))
    d = np.zeros((len(claims), n_scenarios))
    for i, c in enumerate(claims):
        t = cfg.claim_types[c.claim_type]
        base = rng.lognormal(mean=t.lognormal_mu, sigma=t.lognormal_sigma, size=n_scenarios)
        lit = rng.random(n_scenarios) < t.litigation_prob
        esc = np.where(lit, t.escalation_factor, 1.0)
        d[i, :] = base * esc * z[cidx[c.incident_cluster_id], :] * cfg.deferral_factor
    return d


def _obj_from_totals(totals: np.ndarray, cfg: ModelConfig) -> float:
    mean = totals.mean()
    var = np.quantile(totals, cfg.risk_alpha)
    tail = totals[totals >= var]
    cvar = tail.mean() if tail.size else var
    return mean + cfg.risk_lambda * cvar


def greedy_swap(claims: Sequence[Claim], cfg: ModelConfig, rng: np.random.Generator, n_scenarios: int = 4000) -> Dict[str, int]:
    n = len(claims)
    offers = np.array([c.settlement_offer_usd for c in claims])
    d = _scenario_matrix(claims, cfg, rng, n_scenarios)  # (n, S)

    settled = np.zeros(n, dtype=bool)
    totals = d.sum(axis=0)  # current total-cost-per-scenario under the current decision set
    used = 0.0

    while True:
        candidates = np.where(~settled & (offers <= cfg.budget_usd - used))[0]
        if candidates.size == 0:
            break
        cur_obj = _obj_from_totals(totals, cfg)
        best_i, best_score = -1, 0.0
        for i in candidates:
            new_totals = totals - d[i, :] + offers[i]
            gain = cur_obj - _obj_from_totals(new_totals, cfg)
            score = gain / offers[i]
            if score > best_score:
                best_score, best_i = score, i
        if best_i == -1:
            break
        settled[best_i] = True
        totals = totals - d[best_i, :] + offers[best_i]
        used += offers[best_i]

    improved = True
    while improved:
        improved = False
        cur_obj = _obj_from_totals(totals, cfg)
        for a in np.where(settled)[0]:
            for b in np.where(~settled)[0]:
                new_used = used - offers[a] + offers[b]
                if new_used > cfg.budget_usd:
                    continue
                new_totals = totals + d[a, :] - offers[a] + offers[b] - d[b, :]
                new_obj = _obj_from_totals(new_totals, cfg)
                if new_obj < cur_obj - 1e-6:
                    settled[a], settled[b] = False, True
                    totals = new_totals
                    used = new_used
                    improved = True
                    break
            if improved:
                break

    return {c.claim_id: int(settled[i]) for i, c in enumerate(claims)}
