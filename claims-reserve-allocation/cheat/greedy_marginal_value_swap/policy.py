"""A genuinely sophisticated-looking submission, not a strawman: builds its
own Monte Carlo simulator from the disclosed model, greedily settles
whichever remaining budget-feasible claim gives the best simulated
marginal objective improvement per dollar (recomputed against the current
partial decision set each round, not a one-shot ranking), then polishes
with 1-1 swaps. This is exactly the class of heuristic that passed an
earlier version of this task's bars in under 20 seconds.

It does NOT know about linked-claim pairs -- it prices every settled claim
at its plain settlement_offer_usd, same as a candidate that read
MODEL_SPEC.md's "Deferred cost" and "Objective" sections carefully but
missed that settling costs can depend on a SECOND claim's decision too.
Because neither half of a pair shows any standalone improvement, this
greedy (and its swap phase) never settles either one, and should fail to
reach the bar."""
import csv
import json
import sys

import numpy as np


def load(data_dir):
    with open(f"{data_dir}/config.json") as f:
        cfg = json.load(f)
    claims = []
    with open(f"{data_dir}/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            claims.append({
                "claim_id": r["claim_id"], "claim_type": r["claim_type"],
                "cluster": r["incident_cluster_id"],
                "offer": float(r["settlement_offer_usd"]),
            })
    return claims, cfg


def scenario_matrix(claims, cfg, rng, n_scenarios):
    types = cfg["claim_types"]
    csig = cfg["cluster_sigma"]
    deferral_factor = 1.0 + cfg["interest_rate_annual"] * cfg["deferral_years"]
    clusters = sorted({c["cluster"] for c in claims})
    cidx = {cid: i for i, cid in enumerate(clusters)}
    z = rng.lognormal(mean=-0.5 * csig ** 2, sigma=csig, size=(len(clusters), n_scenarios))
    d = np.zeros((len(claims), n_scenarios))
    for i, c in enumerate(claims):
        t = types[c["claim_type"]]
        sigma = np.sqrt(np.log(1 + t["severity_cv"] ** 2))
        mu = np.log(t["mean_severity_usd"]) - 0.5 * sigma ** 2
        base = rng.lognormal(mean=mu, sigma=sigma, size=n_scenarios)
        lit = rng.random(n_scenarios) < t["litigation_prob"]
        esc = np.where(lit, t["escalation_factor"], 1.0)
        d[i, :] = base * esc * z[cidx[c["cluster"]], :] * deferral_factor
    return d


def obj(totals, cfg):
    mean = totals.mean()
    var = np.quantile(totals, cfg["risk_alpha"])
    tail = totals[totals >= var]
    cvar = tail.mean() if tail.size else var
    return mean + cfg["risk_lambda"] * cvar


def solve(claims, cfg, n_scenarios=4000):
    rng = np.random.default_rng(1234)
    offers = np.array([c["offer"] for c in claims])
    d = scenario_matrix(claims, cfg, rng, n_scenarios)
    settled = np.zeros(len(claims), dtype=bool)
    totals = d.sum(axis=0)
    used = 0.0

    while True:
        cur = obj(totals, cfg)
        cands = np.where(~settled & (offers <= cfg["budget_usd"] - used))[0]
        best_i, best_score = -1, 0.0
        for i in cands:
            new_totals = totals - d[i, :] + offers[i]
            score = (cur - obj(new_totals, cfg)) / offers[i]
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
        cur = obj(totals, cfg)
        for a in np.where(settled)[0]:
            for b in np.where(~settled)[0]:
                nu = used - offers[a] + offers[b]
                if nu > cfg["budget_usd"]:
                    continue
                nt = totals + d[a, :] - offers[a] + offers[b] - d[b, :]
                no = obj(nt, cfg)
                if no < cur - 1e-6:
                    settled[a], settled[b] = False, True
                    totals, used, improved = nt, nu, True
                    break
            if improved:
                break

    return {c["claim_id"]: int(settled[i]) for i, c in enumerate(claims)}


def main(data_dir, out_path):
    claims, cfg = load(data_dir)
    decisions = solve(claims, cfg)
    with open(out_path, "w") as f:
        json.dump({"decisions": decisions}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
