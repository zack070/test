"""Build every dataset in the bundle: worked_example, case (visible),
held_out_1, held_out_2 (sealed). For the sealed sets, also computes and
writes the reference (eval seed + pass bar), calibrated from measured
naive/ev_optimal/risk_aware objectives on that exact portfolio -- never
asserted.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from generator import generate_portfolio, write_portfolio  # noqa: E402
from model import objective  # noqa: E402
from solvers import ev_optimal, naive_greedy, risk_aware  # noqa: E402
from greedy_swap_solver import greedy_swap  # noqa: E402

BUNDLE_ROOT = os.path.join(os.path.dirname(__file__), "..")
EVAL_N_PATHS_CALIBRATION = 80000
EVAL_N_PATHS_SEALED = 150000
SOLVER_N_SCENARIOS = 2000


def calibrate_and_write_reference(name: str, seed: int, out_input_dir: str, out_reference_dir: str):
    p = generate_portfolio(seed=seed)
    claims, cfg = p["claims"], p["config"]
    write_portfolio(p, out_input_dir)

    d_naive = naive_greedy(claims, cfg)
    d_ev = ev_optimal(claims, cfg)
    d_gs = greedy_swap(claims, cfg, np.random.default_rng(seed + 4000), n_scenarios=4000)
    d_risk = risk_aware(claims, cfg, np.random.default_rng(seed + 5000), n_scenarios=SOLVER_N_SCENARIOS)

    eval_seed = seed + 900000
    eval_rng = lambda: np.random.default_rng(eval_seed)  # noqa: E731
    r_naive = objective(claims, d_naive, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)
    r_ev = objective(claims, d_ev, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)
    r_gs = objective(claims, d_gs, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)
    r_risk = objective(claims, d_risk, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)

    # The bar must sit below BOTH: (a) the classic EV-only, correlation-blind
    # knapsack, and (b) a genuinely strong pair-blind heuristic (greedy by
    # simulated marginal objective gain per dollar + 1-1 swaps -- this is
    # what an earlier version of this bundle's bar failed to rule out).
    # Whichever of the two gives the stricter (lower) bar wins, so neither
    # baseline can slip through.
    bar_vs_ev = r_ev["objective"] - 0.5 * (r_ev["objective"] - r_risk["objective"])
    bar_vs_gs = r_risk["objective"] + 0.35 * (r_gs["objective"] - r_risk["objective"])
    bar = min(bar_vs_ev, bar_vs_gs)
    gap_pct = (r_ev["objective"] - r_risk["objective"]) / r_ev["objective"] * 100
    gap_gs_pct = (r_gs["objective"] - r_risk["objective"]) / r_gs["objective"] * 100

    print(f"[{name}] n_claims={len(claims)} naive={r_naive['objective']:.0f} "
          f"ev_optimal={r_ev['objective']:.0f} greedy_swap={r_gs['objective']:.0f} "
          f"risk_aware={r_risk['objective']:.0f} gap_vs_ev%={gap_pct:.2f} "
          f"gap_vs_gs%={gap_gs_pct:.2f} bar={bar:.0f} "
          f"(ev_would_pass={r_ev['objective']<=bar} gs_would_pass={r_gs['objective']<=bar})")

    os.makedirs(out_reference_dir, exist_ok=True)
    with open(os.path.join(out_reference_dir, f"{name}_reference.json"), "w") as f:
        json.dump({
            "eval_seed": eval_seed,
            "eval_n_paths": EVAL_N_PATHS_SEALED,
            "pass_bar_objective": round(bar, 2),
            "_calibration_measured": {
                "naive_objective": round(r_naive["objective"], 2),
                "ev_optimal_objective": round(r_ev["objective"], 2),
                "greedy_swap_objective": round(r_gs["objective"], 2),
                "risk_aware_objective": round(r_risk["objective"], 2),
                "gap_vs_ev_pct": round(gap_pct, 3),
                "gap_vs_greedy_swap_pct": round(gap_gs_pct, 3),
            },
        }, f, indent=2)


def build_visible(name: str, seed: int, n_singleton_ish: int, trap_clusters, out_dir: str):
    p = generate_portfolio(seed=seed, n_singleton_ish=n_singleton_ish, trap_clusters=trap_clusters)
    claims, cfg = p["claims"], p["config"]
    write_portfolio(p, out_dir)

    d_naive = naive_greedy(claims, cfg)
    d_ev = ev_optimal(claims, cfg)
    d_settle_nothing = {c.claim_id: 0 for c in claims}

    eval_rng = lambda: np.random.default_rng(seed + 700000)  # noqa: E731
    r_naive = objective(claims, d_naive, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)
    r_ev = objective(claims, d_ev, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)
    r_nothing = objective(claims, d_settle_nothing, cfg, eval_rng(), EVAL_N_PATHS_CALIBRATION)

    print(f"[{name}] n_claims={len(claims)} settle_nothing={r_nothing['objective']:.0f} "
          f"naive_ratio_greedy={r_naive['objective']:.0f} ev_optimal={r_ev['objective']:.0f}")

    with open(os.path.join(out_dir, "reference_metrics.json"), "w") as f:
        json.dump({
            "note": (
                "Measured objective for three example policies (settle_nothing, "
                "naive_ratio_greedy, ev_optimal_knapsack), for calibrating your "
                "own simulator against -- NOT the task's answer. There is no "
                "single correct decision set; you are scored on the objective "
                "your own policy achieves."
            ),
            "settle_nothing": {k: round(v, 2) for k, v in r_nothing.items()},
            "naive_ratio_greedy": {k: round(v, 2) for k, v in r_naive.items()},
            "ev_optimal_knapsack": {k: round(v, 2) for k, v in r_ev.items()},
        }, f, indent=2)


def main():
    build_visible(
        "worked_example", seed=50, n_singleton_ish=16, trap_clusters=[4, 3],
        out_dir=os.path.join(BUNDLE_ROOT, "environment/data/worked_example"),
    )
    build_visible(
        "case", seed=100, n_singleton_ish=120, trap_clusters=[25, 20],
        out_dir=os.path.join(BUNDLE_ROOT, "environment/data/case"),
    )
    calibrate_and_write_reference(
        "held_out_1", seed=901,
        out_input_dir=os.path.join(BUNDLE_ROOT, "tests/sealed/inputs/held_out_1"),
        out_reference_dir=os.path.join(BUNDLE_ROOT, "tests/sealed/reference"),
    )
    calibrate_and_write_reference(
        "held_out_2", seed=902,
        out_input_dir=os.path.join(BUNDLE_ROOT, "tests/sealed/inputs/held_out_2"),
        out_reference_dir=os.path.join(BUNDLE_ROOT, "tests/sealed/reference"),
    )


if __name__ == "__main__":
    main()
