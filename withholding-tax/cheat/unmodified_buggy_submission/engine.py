"""
Withholding tax computation pipeline.

This is supposed to implement RULEBOOK.md exactly. It was written by
someone who understood the rules but introduced a few bugs along the
way -- the kind of mistakes a competent engineer plausibly makes, not
absurd or arbitrary ones. Your job is to find and fix them so this
pipeline's output is actually correct, not just structurally reasonable.

Run it with: python3 -m pipeline.engine <data_dir> <output_path>

It reads entities.csv, ownership.csv, payments.csv, fx_rates.csv, and
config.json from <data_dir> (see RULEBOOK.md for the exact formats) and
writes the reconciliation report to <output_path>.
"""
from __future__ import annotations

import csv
import decimal
import json
import os
import sys
from dataclasses import dataclass
from datetime import date as Date
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class OwnershipRecord:
    owner: str
    owned: str
    stake_pct: float
    effective_from: Date
    effective_to: Date


@dataclass(frozen=True)
class Payment:
    payment_id: str
    payee: str
    amount: float
    currency: str
    payment_date: Date
    acquisition_date: Date


@dataclass
class ScenarioData:
    entities: Dict[str, str]
    ownership: List[OwnershipRecord]
    payments: List[Payment]
    fx_rates: Dict[Tuple[str, int, int], float]
    statutory_rate: float
    treaty_partners: Dict[str, float]
    threshold_usd: float
    holding_period_days: int = 365


def _round2(x: float) -> float:
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def fx_rate(scenario: ScenarioData, currency: str, on_date: Date) -> float:
    return scenario.fx_rates[(currency, on_date.year, on_date.month)]


_parent_cache: Dict[str, str] = {}


def relevant_parent(scenario: ScenarioData, entity: str, on_date: Date) -> str:
    if entity in _parent_cache:
        return _parent_cache[entity]

    def resolve(current: str, depth: int = 0) -> str:
        if depth > len(scenario.entities) + 2:
            raise RuntimeError(f"ownership cycle detected involving {current}")
        owner_record = None
        for rec in scenario.ownership:
            if rec.owned == current and rec.effective_from <= on_date < rec.effective_to:
                owner_record = rec
                break
        if owner_record is None:
            return current
        if owner_record.stake_pct > 50:
            return resolve(owner_record.owner, depth + 1)
        return owner_record.owner

    result = resolve(entity)
    _parent_cache[entity] = result
    return result


def holding_days(payment: Payment) -> int:
    return (payment.payment_date - payment.acquisition_date).days


def base_rate_for_payment(scenario: ScenarioData, payment: Payment) -> float:
    parent = relevant_parent(scenario, payment.payee, payment.payment_date)
    parent_jur = scenario.entities.get(parent, parent)
    treaty_rate = scenario.treaty_partners.get(parent_jur)
    if treaty_rate is not None and holding_days(payment) >= scenario.holding_period_days:
        return treaty_rate
    return scenario.statutory_rate


def compute_report(scenario: ScenarioData) -> Dict:
    base_rate: Dict[str, float] = {}
    usd_amount: Dict[str, float] = {}
    for p in scenario.payments:
        base_rate[p.payment_id] = base_rate_for_payment(scenario, p)
        usd_amount[p.payment_id] = p.amount * fx_rate(scenario, p.currency, p.payment_date)

    by_payee_year: Dict[Tuple[str, int], List[Payment]] = {}
    for p in scenario.payments:
        key = (p.payee, p.payment_date.year)
        by_payee_year.setdefault(key, []).append(p)

    final_rate: Dict[str, float] = {}
    for key, group in by_payee_year.items():
        group_sorted = sorted(group, key=lambda p: p.payment_date)
        running_total = 0.0
        crossed = False
        for p in group_sorted:
            running_total += usd_amount[p.payment_id]
            if running_total >= scenario.threshold_usd:
                crossed = True
            # Applies statutory rate from the crossing point onward, but
            # never goes back to fix payments already processed earlier
            # in this same loop before the threshold was crossed.
            final_rate[p.payment_id] = scenario.statutory_rate if crossed else base_rate[p.payment_id]

    lines = []
    grand_total = 0.0
    for p in scenario.payments:
        initial_rate = base_rate[p.payment_id]
        initial_withholding = usd_amount[p.payment_id] * initial_rate
        final_withholding = usd_amount[p.payment_id] * final_rate[p.payment_id]
        true_up = final_withholding - initial_withholding
        lines.append({
            "payment_id": p.payment_id,
            "initial_rate": initial_rate,
            "final_rate": final_rate[p.payment_id],
            "initial_withholding_usd": _round2(initial_withholding),
            "final_withholding_usd": _round2(final_withholding),
            "true_up_usd": _round2(true_up),
        })
        grand_total += final_withholding

    return {
        "payments": lines,
        "total_liability_usd": _round2(grand_total),
    }


def load_scenario(data_dir: str) -> ScenarioData:
    def parse_date(s: str) -> Date:
        y, m, d = s.split("-")
        return Date(int(y), int(m), int(d))

    entities = {}
    with open(os.path.join(data_dir, "entities.csv"), newline="") as f:
        for r in csv.DictReader(f):
            entities[r["entity_id"]] = r["jurisdiction"]

    ownership = []
    with open(os.path.join(data_dir, "ownership.csv"), newline="") as f:
        for r in csv.DictReader(f):
            ownership.append(OwnershipRecord(
                owner=r["owner"], owned=r["owned"], stake_pct=float(r["stake_pct"]),
                effective_from=parse_date(r["effective_from"]), effective_to=parse_date(r["effective_to"]),
            ))

    payments = []
    with open(os.path.join(data_dir, "payments.csv"), newline="") as f:
        for r in csv.DictReader(f):
            payments.append(Payment(
                payment_id=r["payment_id"], payee=r["payee"], amount=float(r["amount"]),
                currency=r["currency"], payment_date=parse_date(r["payment_date"]),
                acquisition_date=parse_date(r["acquisition_date"]),
            ))

    fx_rates = {}
    with open(os.path.join(data_dir, "fx_rates.csv"), newline="") as f:
        for r in csv.DictReader(f):
            fx_rates[(r["currency"], int(r["year"]), int(r["month"]))] = float(r["rate_to_usd"])

    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)

    return ScenarioData(
        entities=entities, ownership=ownership, payments=payments, fx_rates=fx_rates,
        statutory_rate=cfg["statutory_rate"], treaty_partners=cfg["treaty_partners"],
        threshold_usd=cfg["threshold_usd"], holding_period_days=cfg.get("holding_period_days", 365),
    )


def run(data_dir: str) -> Dict:
    _parent_cache.clear()
    scenario = load_scenario(data_dir)
    return compute_report(scenario)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 -m pipeline.engine <data_dir> <output_path>", file=sys.stderr)
        sys.exit(1)
    report = run(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {sys.argv[2]}: total_liability_usd={report['total_liability_usd']}")
