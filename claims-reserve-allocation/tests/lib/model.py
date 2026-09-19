"""
Canonical generative model + objective evaluator for claims-reserve-allocation.

This is the ONE place the math lives. generator.py uses it to build portfolios;
solvers.py and calibrate.py use it to score decisions. The shipped RULEBOOK
(the disclosed spec) must describe exactly this model -- nothing more,
nothing less.

Model (single deferral period, no multi-period chains):
  - Each claim has a claim_type in a small fixed set (AUTO, PROPERTY, LIABILITY).
  - Each claim belongs to exactly one incident_cluster. All claims in a
    cluster share one latent multiplicative factor Z_c ~ LogNormal(mean=1),
    which is what makes their eventual costs correlated.
  - If deferred, a claim's eventual cost is:
        base_severity_i ~ LogNormal(type mean, type CV)      [own draw]
        realized_i = base_severity_i * Z_{cluster(i)}
        if litigated (Bernoulli(p_lit_type)): realized_i *= escalation_factor_type
        deferred_cost_i = realized_i * (1 + interest_rate_annual * deferral_years)
  - If settled now, the claim costs settlement_offer_usd_i (disclosed, fixed,
    known today) -- EXCEPT for a linked-pair claim, which costs
    settlement_offer_usd_i * (1 - linked_settlement_discount) if its
    designated pair partner is ALSO settled, and the full undiscounted
    settlement_offer_usd_i if the partner is not. A small number of claims
    are pair-linked (representing claims that settle only as a package --
    co-defendant claims under one agreement, or a single claimant's
    multiple related claims); most claims have no pair and are unaffected.
  - Decision x_i in {0,1}: 1 = settle now, 0 = defer.
  - Feasibility: sum_i settlement_cost_i(x) <= budget_usd (hard cap), where
    settlement_cost_i(x) is 0 for a deferred claim and the (possibly
    pair-discounted) settled cost above otherwise.
  - Objective (minimize): E[total_cost(x)] + risk_lambda * CVaR_alpha(total_cost(x))
    where CVaR_alpha is the mean of the worst (1 - alpha) tail of the total
    cost distribution induced by the random draws above.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np


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

    @property
    def expected_escalation(self) -> float:
        return 1.0 + self.litigation_prob * (self.escalation_factor - 1.0)


@dataclass(frozen=True)
class ModelConfig:
    claim_types: Dict[str, ClaimTypeParams]
    cluster_sigma: float
    interest_rate_annual: float
    deferral_years: float
    risk_alpha: float
    risk_lambda: float
    budget_usd: float
    linked_settlement_discount: float = 0.0

    @property
    def cluster_lognormal_sigma(self) -> float:
        return self.cluster_sigma

    @property
    def cluster_lognormal_mu(self) -> float:
        # E[Z_c] = 1 exactly.
        return -0.5 * self.cluster_sigma ** 2

    @property
    def deferral_factor(self) -> float:
        return 1.0 + self.interest_rate_annual * self.deferral_years


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim_type: str
    incident_cluster_id: str
    settlement_offer_usd: float
    linked_claim_id: str = ""


def settlement_cost(claim: Claim, decisions: Dict[str, int], cfg: ModelConfig) -> float:
    """What settling `claim` actually costs, given the full decision set --
    the full offer, unless it's pair-linked and its partner is ALSO settled,
    in which case both get the linked discount."""
    if claim.linked_claim_id and decisions.get(claim.linked_claim_id, 0) == 1:
        return claim.settlement_offer_usd * (1.0 - cfg.linked_settlement_discount)
    return claim.settlement_offer_usd


def expected_deferred_cost(claim: Claim, cfg: ModelConfig) -> float:
    """Closed-form E[deferred_cost_i]. Valid because E[Z_c] = E[base_severity]
    (in the sense of matching the disclosed type mean) = 1 by construction,
    and expectation is linear/multiplicative-independent across the three
    independent random factors (base severity, cluster factor, litigation)."""
    t = cfg.claim_types[claim.claim_type]
    return t.mean_severity_usd * t.expected_escalation * cfg.deferral_factor


def simulate_total_cost(
    claims: Sequence[Claim],
    decisions: Dict[str, int],
    cfg: ModelConfig,
    rng: np.random.Generator,
    n_paths: int,
) -> np.ndarray:
    """Vectorized Monte Carlo: returns an (n_paths,) array of total realized
    cost under `decisions`. Settled claims contribute a fixed offer on every
    path; deferred claims contribute a random draw that shares a per-cluster
    latent factor with other deferred claims in the same cluster."""
    cluster_ids = sorted({c.incident_cluster_id for c in claims})
    cluster_index = {cid: i for i, cid in enumerate(cluster_ids)}
    n_clusters = len(cluster_ids)

    z = rng.lognormal(
        mean=cfg.cluster_lognormal_mu, sigma=cfg.cluster_lognormal_sigma,
        size=(n_paths, n_clusters),
    )

    total = np.zeros(n_paths, dtype=np.float64)
    for c in claims:
        if decisions[c.claim_id] == 1:
            total += settlement_cost(c, decisions, cfg)
            continue
        t = cfg.claim_types[c.claim_type]
        base = rng.lognormal(mean=t.lognormal_mu, sigma=t.lognormal_sigma, size=n_paths)
        litigated = rng.random(n_paths) < t.litigation_prob
        escalation = np.where(litigated, t.escalation_factor, 1.0)
        cz = z[:, cluster_index[c.incident_cluster_id]]
        total += base * cz * escalation * cfg.deferral_factor
    return total


def cvar(costs: np.ndarray, alpha: float) -> float:
    """Mean of the worst (1 - alpha) tail (high-cost tail, since this is a
    cost we want to minimize, not a return)."""
    var = np.quantile(costs, alpha)
    tail = costs[costs >= var]
    if tail.size == 0:
        return float(var)
    return float(tail.mean())


def objective(
    claims: Sequence[Claim],
    decisions: Dict[str, int],
    cfg: ModelConfig,
    rng: np.random.Generator,
    n_paths: int,
) -> Dict[str, float]:
    costs = simulate_total_cost(claims, decisions, cfg, rng, n_paths)
    mean_cost = float(costs.mean())
    cvar_cost = cvar(costs, cfg.risk_alpha)
    return {
        "expected_cost": mean_cost,
        "cvar": cvar_cost,
        "objective": mean_cost + cfg.risk_lambda * cvar_cost,
    }


def budget_used(claims: Sequence[Claim], decisions: Dict[str, int], cfg: ModelConfig) -> float:
    return sum(settlement_cost(c, decisions, cfg) for c in claims if decisions[c.claim_id] == 1)


def is_feasible(claims: Sequence[Claim], decisions: Dict[str, int], cfg: ModelConfig) -> bool:
    return budget_used(claims, decisions, cfg) <= cfg.budget_usd + 1e-6
