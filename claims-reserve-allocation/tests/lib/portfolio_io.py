"""Load a portfolio (claims.csv + config.json) the same way the candidate
policy is expected to, so grading uses the exact same data the candidate saw."""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, List

from model import Claim, ClaimTypeParams, ModelConfig


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
        linked_settlement_discount=cfg_json.get("linked_settlement_discount", 0.0),
    )
    claims: List[Claim] = []
    with open(os.path.join(data_dir, "claims.csv"), newline="") as f:
        for r in csv.DictReader(f):
            claims.append(Claim(
                claim_id=r["claim_id"], claim_type=r["claim_type"],
                incident_cluster_id=r["incident_cluster_id"],
                settlement_offer_usd=float(r["settlement_offer_usd"]),
                linked_claim_id=r.get("linked_claim_id", "") or "",
            ))
    return {"claims": claims, "config": cfg}
