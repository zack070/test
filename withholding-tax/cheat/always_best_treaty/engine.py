import csv
import decimal
import json
import os
import sys


def _round2(x):
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def run(data_dir):
    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)
    best_rate = min(cfg["treaty_partners"].values())

    fx = {}
    with open(os.path.join(data_dir, "fx_rates.csv"), newline="") as f:
        for r in csv.DictReader(f):
            fx[(r["currency"], int(r["year"]), int(r["month"]))] = float(r["rate_to_usd"])

    lines = []
    total = 0.0
    with open(os.path.join(data_dir, "payments.csv"), newline="") as f:
        for r in csv.DictReader(f):
            y, m, _ = r["payment_date"].split("-")
            rate = fx[(r["currency"], int(y), int(m))]
            usd = float(r["amount"]) * rate
            fw = usd * best_rate
            lines.append({
                "payment_id": r["payment_id"], "initial_rate": best_rate, "final_rate": best_rate,
                "initial_withholding_usd": _round2(fw), "final_withholding_usd": _round2(fw), "true_up_usd": 0.0,
            })
            total += fw
    return {"payments": lines, "total_liability_usd": _round2(total)}


if __name__ == "__main__":
    report = run(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(report, f)
