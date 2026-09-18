"""Builds the small worked example shipped to the agent with its answer
shown, so the agent can validate its understanding of every rule against
a known-correct case before tackling the real (much larger) dataset in
environment/data/case/. Six payments, one per rule behavior, hand-picked
rather than randomly generated so each one's reasoning is traceable in
one line.
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from scenario_gen import Builder, OwnershipRow  # noqa: E402
import rule_engine as eng  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "data", "worked_example")

STATUTORY_RATE = 0.30
TREATY_PARTNERS = {"JUR-DE": 0.10, "JUR-SG": 0.08}
THRESHOLD_USD = 500_000.0


def build():
    b = Builder()

    # 1. Simple treaty case: no owner, treaty jurisdiction, long holding, well under threshold.
    e1 = b.new_entity("JUR-DE")
    b.new_payment(e1, 100_000.0, "USD", date(2024, 6, 1), date(2022, 1, 1))

    # 2. Simple no-treaty case: no owner, jurisdiction has no treaty at all.
    e2 = b.new_entity("JUR-KY")
    b.new_payment(e2, 100_000.0, "USD", date(2024, 6, 1), date(2022, 1, 1))

    # 3. Short holding period: treaty jurisdiction, but held less than 365 days.
    e3 = b.new_entity("JUR-DE")
    b.new_payment(e3, 100_000.0, "USD", date(2024, 6, 1), date(2024, 1, 1))  # 152 days

    # 4. Ownership look-through reaches a no-treaty grandparent: payee's
    #    immediate owner holds 80% (>50%, look-through continues) and
    #    that owner's own jurisdiction is JUR-KY (no treaty).
    e4 = b.new_entity("JUR-SG")  # payee's own jurisdiction is irrelevant once look-through applies
    owner4 = b.new_entity("JUR-KY")
    b.ownership.append(OwnershipRow(owner4, e4, 80.0, date(2024, 1, 1), date(2025, 1, 1)))
    b.new_payment(e4, 100_000.0, "USD", date(2024, 6, 1), date(2022, 1, 1))

    # 5. Ownership look-through stops at a 40% owner: the walk stops
    #    there (40% <= 50%), so THAT owner's jurisdiction (treaty)
    #    governs, regardless of what's further up the chain.
    e5 = b.new_entity("JUR-KY")
    owner5 = b.new_entity("JUR-DE")
    grandparent5 = b.new_entity("JUR-KY")
    b.ownership.append(OwnershipRow(owner5, e5, 40.0, date(2024, 1, 1), date(2025, 1, 1)))
    b.ownership.append(OwnershipRow(grandparent5, owner5, 100.0, date(2024, 1, 1), date(2025, 1, 1)))
    b.new_payment(e5, 100_000.0, "USD", date(2024, 6, 1), date(2022, 1, 1))

    # 6. Cumulative threshold breach: two payments to the same payee,
    #    each individually treaty-eligible, whose combined USD total
    #    exceeds THRESHOLD_USD -- both get retroactively re-rated to
    #    statutory, including the first one (already "paid" at treaty
    #    rate), which owes a true-up.
    e6 = b.new_entity("JUR-DE")
    b.new_payment(e6, 300_000.0, "USD", date(2024, 3, 1), date(2022, 1, 1))
    b.new_payment(e6, 300_000.0, "USD", date(2024, 7, 1), date(2022, 1, 1))

    return b


def write(b):
    os.makedirs(OUT_DIR, exist_ok=True)
    import csv
    import json

    with open(os.path.join(OUT_DIR, "entities.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "jurisdiction"])
        for e in sorted(b.entities.values(), key=lambda e: e.entity_id):
            w.writerow([e.entity_id, e.jurisdiction])

    with open(os.path.join(OUT_DIR, "ownership.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "owned", "stake_pct", "effective_from", "effective_to"])
        for o in sorted(b.ownership, key=lambda o: (o.owned, o.effective_from)):
            w.writerow([o.owner, o.owned, o.stake_pct, o.effective_from.isoformat(), o.effective_to.isoformat()])

    with open(os.path.join(OUT_DIR, "payments.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["payment_id", "payee", "amount", "currency", "payment_date", "acquisition_date"])
        for p in sorted(b.payments, key=lambda p: p.payment_id):
            w.writerow([p.payment_id, p.payee, p.amount, p.currency, p.payment_date.isoformat(), p.acquisition_date.isoformat()])

    with open(os.path.join(OUT_DIR, "fx_rates.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["currency", "year", "month", "rate_to_usd"])
        for m in range(1, 13):
            w.writerow(["USD", 2024, m, 1.0])

    with open(os.path.join(OUT_DIR, "config.json"), "w") as f:
        json.dump({
            "statutory_rate": STATUTORY_RATE,
            "treaty_partners": TREATY_PARTNERS,
            "threshold_usd": THRESHOLD_USD,
            "holding_period_days": 365,
        }, f, indent=2)


if __name__ == "__main__":
    b = build()
    write(b)
    sc = eng.load_scenario(OUT_DIR)
    report = eng.compute_report(sc)
    with open(os.path.join(OUT_DIR, "expected_answer.json"), "w") as f:
        import json
        json.dump(report, f, indent=2)
    print("wrote worked_example/, total =", report["total_liability_usd"])
    for line in report["payments"]:
        print(" ", line)
