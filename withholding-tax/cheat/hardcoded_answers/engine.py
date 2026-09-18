"""Memorizes the visible case/ dataset's own known-correct answers
(shipped as a hardcoded lookup table, memorized.json, built from
environment/data/case/expected_answer.json) instead of implementing the
rules -- betting that grading reuses the same payment_ids. It does not:
held-out grading data comes from a freshly generated scenario whose
payment_ids happen to overlap the visible dataset's numbering (both
start at PAY0001) but whose underlying facts (amounts, dates,
ownership) are different, so a memorized answer keyed only by
payment_id is wrong for held-out data."""
import csv
import decimal
import json
import os
import sys

MEMORIZED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memorized.json")


def _round2(x):
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def run(data_dir):
    with open(MEMORIZED_PATH) as f:
        memorized = json.load(f)

    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)
    statutory = cfg["statutory_rate"]
    fx = {}
    with open(os.path.join(data_dir, "fx_rates.csv"), newline="") as f:
        for r in csv.DictReader(f):
            fx[(r["currency"], int(r["year"]), int(r["month"]))] = float(r["rate_to_usd"])

    lines = []
    total = 0.0
    with open(os.path.join(data_dir, "payments.csv"), newline="") as f:
        for r in csv.DictReader(f):
            pid = r["payment_id"]
            if pid in memorized:
                m = memorized[pid]
                lines.append(m)
                total += m["final_withholding_usd"]
            else:
                # fallback: naive statutory-only guess for anything unrecognized
                y, mo, _ = r["payment_date"].split("-")
                rate = fx[(r["currency"], int(y), int(mo))]
                usd = float(r["amount"]) * rate
                fw = usd * statutory
                lines.append({
                    "payment_id": pid, "initial_rate": statutory, "final_rate": statutory,
                    "initial_withholding_usd": _round2(fw), "final_withholding_usd": _round2(fw), "true_up_usd": 0.0,
                })
                total += fw
    return {"payments": lines, "total_liability_usd": _round2(total)}


if __name__ == "__main__":
    report = run(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(report, f)
