"""Feasibility spike: does a linked-pair discount defeat greedy+1-1-swap
while remaining findable by exhaustive pair search? Toy-scale test before
touching the real bundle."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
from model import Claim, ClaimTypeParams, ModelConfig

CLAIM_TYPES = {
    "AUTO": ClaimTypeParams(mean_severity_usd=15000.0, severity_cv=0.4, litigation_prob=0.10, escalation_factor=1.5),
}
cfg = ModelConfig(claim_types=CLAIM_TYPES, cluster_sigma=0.9, interest_rate_annual=0.06,
                   deferral_years=1.0, risk_alpha=0.95, risk_lambda=3.0, budget_usd=50000.0)

# 20 ordinary claims (attractive, good ratio) + 2 "linked pair" claims (poor alone, priced near/above expected deferred cost)
rng = np.random.default_rng(1)
claims = []
for i in range(20):
    offer = rng.uniform(0.55, 0.80) * 15000.0
    claims.append(Claim(f"C{i}", "AUTO", f"CLU{i}", round(offer, 2)))

# linked pair: priced at 0.98x mean severity each (poor deal alone), same cluster as each other
PAIR_A, PAIR_B = "PAIRA", "PAIRB"
claims.append(Claim(PAIR_A, "AUTO", "CLU_PAIR", round(0.98 * 15000.0, 2)))
claims.append(Claim(PAIR_B, "AUTO", "CLU_PAIR", round(0.98 * 15000.0, 2)))

LINKED_DISCOUNT = 0.30  # 30% off each, but only if BOTH settled

def expected_deferred_cost(claim, cfg):
    t = cfg.claim_types[claim.claim_type]
    ee = 1.0 + t.litigation_prob * (t.escalation_factor - 1.0)
    return t.mean_severity_usd * ee * cfg.deferral_factor

def cost_if_settled(cid, decisions, offers, linked):
    base = offers[cid]
    if cid in linked:
        partner = linked[cid]
        if decisions.get(partner, 0) == 1:
            return base * (1 - LINKED_DISCOUNT)
    return base

def objective_toy(decisions, claims, cfg, offers, linked, rng, n=8000):
    cluster_ids = sorted({c.incident_cluster_id for c in claims})
    cidx = {c: i for i, c in enumerate(cluster_ids)}
    z = rng.lognormal(mean=cfg.cluster_lognormal_mu, sigma=cfg.cluster_lognormal_sigma, size=(len(cluster_ids), n))
    totals = np.zeros(n)
    for c in claims:
        if decisions.get(c.claim_id, 0) == 1:
            totals += cost_if_settled(c.claim_id, decisions, offers, linked)
        else:
            t = cfg.claim_types[c.claim_type]
            base = rng.lognormal(mean=t.lognormal_mu, sigma=t.lognormal_sigma, size=n)
            lit = rng.random(n) < t.litigation_prob
            esc = np.where(lit, t.escalation_factor, 1.0)
            totals += base * esc * z[cidx[c.incident_cluster_id], :] * cfg.deferral_factor
    mean = totals.mean()
    var = np.quantile(totals, cfg.risk_alpha)
    tail = totals[totals >= var]
    cvar = tail.mean() if tail.size else var
    return mean + cfg.risk_lambda * cvar

offers = {c.claim_id: c.settlement_offer_usd for c in claims}
linked = {PAIR_A: PAIR_B, PAIR_B: PAIR_A}

# Greedy by marginal gain per dollar (mirrors the reviewer's heuristic, adapted for linked pricing)
settled = {c.claim_id: 0 for c in claims}
used = 0.0
rng_eval = np.random.default_rng(42)
while True:
    cur = objective_toy(settled, claims, cfg, offers, linked, np.random.default_rng(7), 8000)
    best_id, best_score = None, 0.0
    for c in claims:
        if settled[c.claim_id] == 1:
            continue
        cost = cost_if_settled(c.claim_id, settled, offers, linked)
        if used + cost > cfg.budget_usd:
            continue
        cand = dict(settled); cand[c.claim_id] = 1
        new_obj = objective_toy(cand, claims, cfg, offers, linked, np.random.default_rng(7), 8000)
        gain = cur - new_obj
        score = gain / cost
        if score > best_score:
            best_score, best_id = score, c.claim_id
    if best_id is None:
        break
    settled[best_id] = 1
    used += cost_if_settled(best_id, settled, offers, linked)

print("Greedy result: PAIRA settled?", settled[PAIR_A], "PAIRB settled?", settled[PAIR_B])
greedy_obj = objective_toy(settled, claims, cfg, offers, linked, np.random.default_rng(999), 30000)
print("Greedy objective:", greedy_obj)

# Now force-settle the pair (simulating a solver that DOES find the joint benefit) and compare
forced = dict(settled)
# make room in budget by dropping cheapest currently-settled claims if needed
pair_cost = cost_if_settled(PAIR_A, {PAIR_A:1, PAIR_B:1}, offers, linked) + cost_if_settled(PAIR_B, {PAIR_A:1, PAIR_B:1}, offers, linked)
forced[PAIR_A] = 1; forced[PAIR_B] = 1
total_used = sum(cost_if_settled(cid, forced, offers, linked) for cid in forced if forced[cid]==1)
# drop lowest-value currently settled ordinary claims until feasible
ordinary_settled = [c.claim_id for c in claims if c.claim_id not in (PAIR_A,PAIR_B) and forced.get(c.claim_id,0)==1]
ordinary_settled.sort(key=lambda cid: offers[cid])  # drop cheapest first (arbitrary simple fix for the spike)
i = 0
while total_used > cfg.budget_usd and i < len(ordinary_settled):
    forced[ordinary_settled[i]] = 0
    total_used = sum(cost_if_settled(cid, forced, offers, linked) for cid in forced if forced[cid]==1)
    i += 1
forced_obj = objective_toy(forced, claims, cfg, offers, linked, np.random.default_rng(999), 30000)
print("Forced-pair objective:", forced_obj, "(budget used:", total_used, ")")
print("Improvement from finding the pair:", greedy_obj - forced_obj, f"({(greedy_obj-forced_obj)/greedy_obj*100:.2f}%)")
