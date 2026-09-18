"""Builds every cheat/ report.json from the real case dataset, using the
naive computations already validated in dev/probes.py plus a few schema/
format attacks. Each is then run through dev/local_harness.sh and its
measured result is recorded in cheat/README.md -- see that file for the
numbers, this script only builds the files.
"""
import sys
import os
import json
import decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_engine as eng  # noqa: E402
from probes import (  # noqa: E402
    naive_once_per_payee_parent, naive_no_retroactive_threshold, naive_both,
    naive_always_statutory, naive_always_treaty_if_any_partner_reachable,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASE_DIR = os.path.join(ROOT, "environment", "data", "case")
CHEAT_DIR = os.path.join(ROOT, "cheat")


def r2(x):
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def full_report_at_flat_rate(sc, per_payment_rate_fn):
    """Builds a full per-payment report (not just a total) using a
    caller-supplied per-payment base-rate function, with no retroactive
    threshold re-rating applied (final == initial)."""
    lines = []
    total = 0.0
    for p in sc.payments:
        rate = per_payment_rate_fn(p)
        usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
        fw = usd * rate
        lines.append({
            "payment_id": p.payment_id, "initial_rate": rate, "final_rate": rate,
            "initial_withholding_usd": r2(fw), "final_withholding_usd": r2(fw), "true_up_usd": 0.0,
        })
        total += fw
    return {"payments": lines, "total_liability_usd": r2(total)}


def main():
    sc = eng.load_scenario(CASE_DIR)

    def write(name, report):
        d = os.path.join(CHEAT_DIR, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "report.json"), "w") as f:
            json.dump(report, f, indent=2)

    # 1. Empty / malformed JSON.
    write("empty_object", {})

    # 2. Missing the 'payments' key entirely, just a plausible-looking total.
    write("total_only_no_lines", {"total_liability_usd": 4_000_100.91})

    # 3. All-zero report (every line zero, correct schema).
    zero_lines = [
        {"payment_id": p.payment_id, "initial_rate": 0.0, "final_rate": 0.0,
         "initial_withholding_usd": 0.0, "final_withholding_usd": 0.0, "true_up_usd": 0.0}
        for p in sc.payments
    ]
    write("all_zero", {"payments": zero_lines, "total_liability_usd": 0.0})

    # 4. Naive: resolves relevant parent once per payee instead of per payment date.
    from datetime import date as Date
    year = sc.payments[0].payment_date.year
    jan1 = Date(year, 1, 1)
    parent_cache = {}

    def once_per_payee_rate(p):
        if p.payee not in parent_cache:
            parent_cache[p.payee] = eng.relevant_parent(sc, p.payee, jan1)
        parent = parent_cache[p.payee]
        parent_jur = sc.entities.get(parent, parent)
        treaty_rate = sc.treaty_partners.get(parent_jur)
        if treaty_rate is not None and eng.holding_days(p) >= sc.holding_period_days:
            return treaty_rate
        return sc.statutory_rate

    write("naive_once_per_payee_parent", full_report_at_flat_rate(sc, once_per_payee_rate))

    # 5. Naive: correct per-payment rate, but never applies the cumulative threshold.
    def correct_base_rate(p):
        rate, _ = eng.base_rate_for_payment(sc, p)
        return rate

    write("naive_no_retroactive_threshold", full_report_at_flat_rate(sc, correct_base_rate))

    # 6. Naive: always statutory (a "when in doubt, be conservative" constant strategy).
    write("naive_always_statutory", full_report_at_flat_rate(sc, lambda p: sc.statutory_rate))

    # 7. Naive: always the best available treaty rate (a constant-optimistic strategy).
    best_rate = min(sc.treaty_partners.values())
    write("naive_always_best_treaty", full_report_at_flat_rate(sc, lambda p: best_rate))

    # 8. Correct on every payment except one, dropped entirely (partial submission).
    correct = eng.compute_report(sc)
    partial = {"payments": correct["payments"][:-1], "total_liability_usd": correct["total_liability_usd"]}
    write("missing_one_payment", partial)

    # 9. Correct total, but individual lines wrong (total-only accuracy, no per-line rigor).
    #    Distributes the correct grand total evenly across all payments regardless of
    #    each one's actual facts -- tests that the verifier checks lines, not just the total.
    n = len(sc.payments)
    even_share = r2(correct["total_liability_usd"] / n)
    even_lines = [
        {"payment_id": p.payment_id, "initial_rate": None, "final_rate": None,
         "initial_withholding_usd": even_share, "final_withholding_usd": even_share, "true_up_usd": 0.0}
        for p in sc.payments
    ]
    write("correct_total_wrong_lines", {"payments": even_lines, "total_liability_usd": correct["total_liability_usd"]})

    print("wrote all cheat/ report.json files")


if __name__ == "__main__":
    main()
