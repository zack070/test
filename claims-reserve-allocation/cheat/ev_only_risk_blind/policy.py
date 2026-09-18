"""The 'decent but risk-blind' baseline: exact 0/1 knapsack optimal for
expected value alone (via MILP), completely ignoring cluster correlation
and the CVaR term. This is meant to fail the bar -- it's the concrete
proof that optimizing expected cost alone isn't enough."""
import csv
import json
import math
import sys

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


def expected_deferred_cost(claim_type, cfg):
    t = cfg["claim_types"][claim_type]
    expected_escalation = 1.0 + t["litigation_prob"] * (t["escalation_factor"] - 1.0)
    deferral_factor = 1.0 + cfg["interest_rate_annual"] * cfg["deferral_years"]
    return t["mean_severity_usd"] * expected_escalation * deferral_factor


def main(data_dir, out_path):
    with open(f"{data_dir}/config.json") as f:
        cfg = json.load(f)

    rows = []
    with open(f"{data_dir}/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    offers = np.array([float(r["settlement_offer_usd"]) for r in rows])
    savings = np.array([
        expected_deferred_cost(r["claim_type"], cfg) - float(r["settlement_offer_usd"])
        for r in rows
    ])

    n = len(rows)
    c_obj = -savings
    budget_constraint = LinearConstraint(offers.reshape(1, -1), -np.inf, cfg["budget_usd"])
    res = milp(c_obj, constraints=[budget_constraint], bounds=Bounds(0, 1), integrality=np.ones(n))
    x = np.round(res.x).astype(int)

    decisions = {rows[i]["claim_id"]: int(x[i]) for i in range(n)}
    with open(out_path, "w") as f:
        json.dump({"decisions": decisions}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
