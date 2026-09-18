"""Portfolio generator for claims-reserve-allocation.

Deliberately builds in a "concentrated cluster" trap: a small number of large
incident clusters whose claims have moderate (not top-ranked) per-dollar
savings, so an expected-value-only optimizer tends to leave that whole
cluster deferred -- concentrating correlated tail risk there -- while a
risk-aware optimizer should trade some expected value to peel off part of
that exposure. Whether this actually produces a measurable gap is checked
empirically in calibrate.py, not assumed here.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from model import Claim, ClaimTypeParams, ModelConfig, expected_deferred_cost  # noqa: E402

CLAIM_TYPES: Dict[str, ClaimTypeParams] = {
    "AUTO": ClaimTypeParams(mean_severity_usd=15000.0, severity_cv=0.4, litigation_prob=0.10, escalation_factor=1.5),
    "PROPERTY": ClaimTypeParams(mean_severity_usd=40000.0, severity_cv=0.6, litigation_prob=0.15, escalation_factor=1.8),
    "LIABILITY": ClaimTypeParams(mean_severity_usd=90000.0, severity_cv=0.9, litigation_prob=0.25, escalation_factor=2.2),
}

CLUSTER_SIGMA = 0.9
INTEREST_RATE_ANNUAL = 0.06
DEFERRAL_YEARS = 1.0
RISK_ALPHA = 0.95
RISK_LAMBDA = 3.0

DEFAULT_TRAP_CLUSTERS = [25, 20]
DEFAULT_BUDGET_FRACTION = 0.40
DEFAULT_TRAP_DISCOUNT_RANGE = (0.83, 0.85)
DEFAULT_N_SINGLETON_ISH = 120

TYPE_WEIGHTS = {"AUTO": 0.50, "PROPERTY": 0.33, "LIABILITY": 0.17}


def base_config(budget_usd: float) -> ModelConfig:
    return ModelConfig(
        claim_types=CLAIM_TYPES, cluster_sigma=CLUSTER_SIGMA,
        interest_rate_annual=INTEREST_RATE_ANNUAL, deferral_years=DEFERRAL_YEARS,
        risk_alpha=RISK_ALPHA, risk_lambda=RISK_LAMBDA, budget_usd=budget_usd,
    )


def _draw_type(rng: np.random.Generator) -> str:
    names = list(TYPE_WEIGHTS.keys())
    probs = list(TYPE_WEIGHTS.values())
    return names[rng.choice(len(names), p=probs)]


def generate_portfolio(
    seed: int,
    n_singleton_ish: int = DEFAULT_N_SINGLETON_ISH,
    trap_clusters: List[int] = None,
    budget_fraction: float = DEFAULT_BUDGET_FRACTION,
    trap_discount_range=DEFAULT_TRAP_DISCOUNT_RANGE,
    normal_discount_range=(0.50, 0.85),
) -> Dict:
    if trap_clusters is None:
        trap_clusters = list(DEFAULT_TRAP_CLUSTERS)
    """trap_clusters: sizes of the deliberately large, moderate-ratio clusters
    (e.g. [10, 8] for two traps of size 10 and 8). n_singleton_ish: number of
    additional claims spread across small clusters (size 1-3)."""
    rng = np.random.default_rng(seed)
    claims: List[Claim] = []
    cluster_counter = 0

    def new_cluster_id() -> str:
        nonlocal cluster_counter
        cluster_counter += 1
        return f"CLU{cluster_counter:04d}"

    claim_counter = 0

    def new_claim_id() -> str:
        nonlocal claim_counter
        claim_counter += 1
        return f"CLM{claim_counter:04d}"

    # Trap clusters: many correlated claims of the *weakest-ratio* type
    # (AUTO: lowest expected escalation, so it has the lowest possible
    # savings ratio at any given discount) each priced at the top of the
    # discount range (worst deal, lowest ratio for that type). This pins
    # every trap claim's EV-only ratio near the bottom of the entire
    # portfolio's ranking -- reliably excluded by an EV-only optimizer --
    # while the sheer count sharing one cluster factor still gives the
    # cluster large *correlated* dollar exposure (no diversification
    # benefit within the cluster), which is what should matter to a
    # risk-aware optimizer even though it's invisible to an EV-only one.
    for size in trap_clusters:
        cid = new_cluster_id()
        for _ in range(size):
            ctype = "AUTO"
            discount = rng.uniform(*trap_discount_range)
            offer = discount * CLAIM_TYPES[ctype].mean_severity_usd
            claims.append(Claim(new_claim_id(), ctype, cid, round(offer, 2)))

    # Ordinary claims: small clusters (size 1-3), full discount range.
    remaining = n_singleton_ish
    while remaining > 0:
        size = min(remaining, int(rng.choice([1, 1, 1, 2, 2, 3], size=1)[0]))
        cid = new_cluster_id()
        for _ in range(size):
            ctype = _draw_type(rng)
            discount = rng.uniform(*normal_discount_range)
            offer = discount * CLAIM_TYPES[ctype].mean_severity_usd
            claims.append(Claim(new_claim_id(), ctype, cid, round(offer, 2)))
        remaining -= size

    total_offer = sum(c.settlement_offer_usd for c in claims)
    budget_usd = round(budget_fraction * total_offer, 2)
    cfg = base_config(budget_usd)
    return {"claims": claims, "config": cfg}


def write_portfolio(portfolio: Dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    claims: List[Claim] = portfolio["claims"]
    cfg: ModelConfig = portfolio["config"]

    with open(os.path.join(out_dir, "claims.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["claim_id", "claim_type", "incident_cluster_id", "settlement_offer_usd"])
        for c in claims:
            w.writerow([c.claim_id, c.claim_type, c.incident_cluster_id, f"{c.settlement_offer_usd:.2f}"])

    config = {
        "claim_types": {
            name: {
                "mean_severity_usd": t.mean_severity_usd,
                "severity_cv": t.severity_cv,
                "litigation_prob": t.litigation_prob,
                "escalation_factor": t.escalation_factor,
            }
            for name, t in cfg.claim_types.items()
        },
        "cluster_sigma": cfg.cluster_sigma,
        "interest_rate_annual": cfg.interest_rate_annual,
        "deferral_years": cfg.deferral_years,
        "risk_alpha": cfg.risk_alpha,
        "risk_lambda": cfg.risk_lambda,
        "budget_usd": cfg.budget_usd,
    }
    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)


def load_portfolio(data_dir: str) -> Dict:
    with open(os.path.join(data_dir, "config.json")) as f:
        cfg_json = json.load(f)
    claim_types = {
        name: ClaimTypeParams(**params) for name, params in cfg_json["claim_types"].items()
    }
    cfg = ModelConfig(
        claim_types=claim_types,
        cluster_sigma=cfg_json["cluster_sigma"],
        interest_rate_annual=cfg_json["interest_rate_annual"],
        deferral_years=cfg_json["deferral_years"],
        risk_alpha=cfg_json["risk_alpha"],
        risk_lambda=cfg_json["risk_lambda"],
        budget_usd=cfg_json["budget_usd"],
    )
    claims: List[Claim] = []
    with open(os.path.join(data_dir, "claims.csv"), newline="") as f:
        for r in csv.DictReader(f):
            claims.append(Claim(
                claim_id=r["claim_id"], claim_type=r["claim_type"],
                incident_cluster_id=r["incident_cluster_id"],
                settlement_offer_usd=float(r["settlement_offer_usd"]),
            ))
    return {"claims": claims, "config": cfg}
