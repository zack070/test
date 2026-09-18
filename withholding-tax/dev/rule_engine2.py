"""Second, independently-coded implementation of the withholding-tax
rulebook (see dev/rule_engine.py for the authoritative rule text this
also implements). Built with a genuinely different structure -- an
iterative, precomputed ownership timeline instead of per-call recursion,
and a single date-sorted pass per payee instead of a separate breach-set
lookup -- specifically so a bug shared between "the reference" and "the
thing the ground truth is built from" can't hide by being the same code
twice. Cross-checked against rule_engine.py on generated scenarios; see
dev/cross_check.py.
"""
from __future__ import annotations

import csv
import json
import math
import os
from datetime import date as Date
from typing import Dict, List, Tuple


def _round2(x: float) -> float:
    sign = -1.0 if x < 0 else 1.0
    return sign * math.floor(abs(x) * 100.0 + 0.5) / 100.0


class Engine:
    def __init__(self, entities, ownership_rows, payments_rows, fx_rows,
                 statutory_rate, treaty_partners, threshold_usd, holding_period_days=365):
        self.entities = dict(entities)
        self.statutory_rate = statutory_rate
        self.treaty_partners = dict(treaty_partners)
        self.threshold_usd = threshold_usd
        self.holding_period_days = holding_period_days
        self.fx = {(c, y, m): r for c, y, m, r in fx_rows}

        # Precompute, per owned-entity, a chronologically sorted timeline
        # of (effective_from, effective_to, owner, stake) -- a linear
        # scan through this list finds the covering record for any date.
        self.timeline: Dict[str, List[Tuple[Date, Date, str, float]]] = {}
        for owner, owned, stake, eff_from, eff_to in ownership_rows:
            self.timeline.setdefault(owned, []).append((eff_from, eff_to, owner, stake))
        for owned in self.timeline:
            self.timeline[owned].sort(key=lambda r: r[0])

        self.payments = payments_rows  # list of dicts

    def _owner_on(self, entity: str, on_date: Date):
        for eff_from, eff_to, owner, stake in self.timeline.get(entity, []):
            if eff_from <= on_date < eff_to:
                return owner, stake
        return None

    def relevant_parent(self, entity: str, on_date: Date) -> str:
        seen = 0
        current = entity
        while True:
            seen += 1
            if seen > len(self.entities) + 5:
                raise RuntimeError(f"ownership cycle involving {entity}")
            found = self._owner_on(current, on_date)
            if found is None:
                return current
            owner, stake = found
            if stake > 50.0:
                current = owner
                continue
            return owner

    def rate_for(self, payee: str, payment_date: Date, acquisition_date: Date):
        parent = self.relevant_parent(payee, payment_date)
        parent_jur = self.entities.get(parent, parent)
        treaty_rate = self.treaty_partners.get(parent_jur)
        days_held = (payment_date - acquisition_date).days
        if treaty_rate is not None and days_held >= self.holding_period_days:
            return treaty_rate
        return self.statutory_rate

    def compute(self) -> Dict:
        by_payee_year: Dict[Tuple[str, int], List[dict]] = {}
        for p in self.payments:
            key = (p["payee"], p["payment_date"].year)
            by_payee_year.setdefault(key, []).append(p)

        lines = []
        grand_total = 0.0
        for key, group in by_payee_year.items():
            group_sorted = sorted(group, key=lambda p: p["payment_date"])
            running_total = 0.0
            enriched = []
            for p in group_sorted:
                rate = self.rate_for(p["payee"], p["payment_date"], p["acquisition_date"])
                usd = p["amount"] * self.fx[(p["currency"], p["payment_date"].year, p["payment_date"].month)]
                running_total += usd
                enriched.append((p, rate, usd))
            breached = running_total > self.threshold_usd
            for p, initial_rate, usd in enriched:
                final_rate = self.statutory_rate if breached else initial_rate
                initial_wh = usd * initial_rate
                final_wh = usd * final_rate
                lines.append({
                    "payment_id": p["payment_id"],
                    "payee": p["payee"],
                    "initial_rate": initial_rate,
                    "final_rate": final_rate,
                    "initial_withholding_usd": _round2(initial_wh),
                    "final_withholding_usd": _round2(final_wh),
                    "true_up_usd": _round2(final_wh - initial_wh),
                })
                grand_total += final_wh

        lines.sort(key=lambda ln: ln["payment_id"])
        return {"payments": lines, "total_liability_usd": _round2(grand_total)}


def load_and_compute(data_dir: str) -> Dict:
    def parse_date(s: str) -> Date:
        y, m, d = s.split("-")
        return Date(int(y), int(m), int(d))

    entities = {}
    with open(os.path.join(data_dir, "entities.csv"), newline="") as f:
        for r in csv.DictReader(f):
            entities[r["entity_id"]] = r["jurisdiction"]

    ownership_rows = []
    with open(os.path.join(data_dir, "ownership.csv"), newline="") as f:
        for r in csv.DictReader(f):
            ownership_rows.append((r["owner"], r["owned"], float(r["stake_pct"]),
                                    parse_date(r["effective_from"]), parse_date(r["effective_to"])))

    payments_rows = []
    with open(os.path.join(data_dir, "payments.csv"), newline="") as f:
        for r in csv.DictReader(f):
            payments_rows.append({
                "payment_id": r["payment_id"], "payee": r["payee"], "amount": float(r["amount"]),
                "currency": r["currency"], "payment_date": parse_date(r["payment_date"]),
                "acquisition_date": parse_date(r["acquisition_date"]),
            })

    fx_rows = []
    with open(os.path.join(data_dir, "fx_rates.csv"), newline="") as f:
        for r in csv.DictReader(f):
            fx_rows.append((r["currency"], int(r["year"]), int(r["month"]), float(r["rate_to_usd"])))

    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)

    engine = Engine(
        entities=entities, ownership_rows=ownership_rows, payments_rows=payments_rows, fx_rows=fx_rows,
        statutory_rate=cfg["statutory_rate"], treaty_partners=cfg["treaty_partners"],
        threshold_usd=cfg["threshold_usd"], holding_period_days=cfg.get("holding_period_days", 365),
    )
    return engine.compute()
