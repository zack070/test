"""
Reference rule engine for cross-border withholding tax computation.

This module is the authoritative specification of every rule, including
every boundary convention -- it is the source the instruction.md
rulebook is written from, and it is used to build the sealed ground
truth. Every ambiguity the idea-checker flagged as a risk is resolved
explicitly below, not left implicit.

RULES
=====

Payer jurisdiction is fixed and single ("HOMELAND") -- this is one
company's treasury function, not a multi-payer system.

Statutory rate: a fixed rate (config["statutory_rate"]) applies to any
payment absent treaty relief.

Treaty relief: a jurisdiction may be a treaty partner of HOMELAND, each
with its own treaty rate (config["treaty_partners"]: jurisdiction ->
rate). A jurisdiction not in this table has no treaty with HOMELAND.

Ownership look-through (resolves which jurisdiction governs treaty
eligibility for a given payment, evaluated AS OF that payment's own
date -- not once per payee, since ownership stakes change over the
year):

    relevant_parent(entity, date):
        owner, stake = the ownership record for `entity` whose
            effective_from <= date < effective_to (at most one such
            record exists per entity; see data invariants below)
        if no such record exists (entity has no owner on record as of
            that date): entity itself is the relevant parent.
        if stake > 50: relevant_parent(owner, date)   -- keep climbing
        if stake <= 50: owner is the relevant parent   -- STOP HERE
            (exactly 50% does NOT continue climbing; the owner at the
            50%-or-below link is the relevant parent, not the entity
            being evaluated and not anyone further up).

    The relevant parent's jurisdiction is looked up in the treaty
    table. If it is a treaty partner AND the payment's holding-period
    test (below) is satisfied, the treaty rate applies. Otherwise the
    statutory rate applies. There is no separate "payee's own
    jurisdiction" check -- the relevant parent computation already
    covers the payee itself in the base case (no owner on record).

Holding-period test: holding_days = (payment_date - acquisition_date)
    in whole calendar days. The test is satisfied if and only if
    holding_days >= 365 (inclusive -- exactly 365 days qualifies).

Cumulative annual threshold (retroactive re-rating): for each payee and
    calendar year (grouped by the payment_date's calendar year; years
    never combine), sum every payment's USD-converted amount. If that
    sum is STRICTLY GREATER than config["threshold_usd"] (a sum
    exactly equal to the threshold does NOT trigger this), every
    payment to that payee in that calendar year -- including the one
    that crossed the threshold, and including ones already computed at
    a treaty rate -- is re-rated to the statutory rate. The true-up
    owed on a re-rated payment is (statutory_rate - original_rate) *
    original payment amount (zero if the payment was already at
    statutory rate). Only the FINAL applicable rate (after this
    re-rating, if triggered) is used for the reported liability;
    "original rate" is tracked separately only to compute the true-up.

Currency conversion: every amount is converted to USD using the rate
    for the calendar month containing the payment's own date (year and
    month; the rate table has exactly one rate per currency per
    calendar month, so there is never a choice between two rates or a
    need to interpolate). This monthly rate is used for BOTH the
    threshold-sum computation and the reported USD liability figures.

Rounding: intermediate computation (rate lookups, day counts, USD
    conversion, threshold sums) is carried in full floating-point
    precision. Rounding to 2 decimal places (standard round-half-up)
    happens exactly once, at the very end, on each of the three
    reported figures per payment (initial_withholding_usd,
    final_withholding_usd, true_up_usd) and once on the grand total.
    Never round an intermediate value and then use the rounded value in
    a further computation.

DATA INVARIANTS (guaranteed by the generator, not something a solver
must defend against): ownership records for a given (owner, owned)
... no wait, records are per OWNED entity: for any entity, its
ownership records partition time with no gaps and no overlaps --
at any date, at most one record covers that entity, and if the entity
has an owner at all during the scenario's time span, exactly one record
covers every date in that span. Payments never fall exactly on a
record's effective_to boundary in a way that's ambiguous (effective_to
is exclusive, so effective_to itself belongs to the NEXT record or to
"no owner"). No payment's holding_days is exactly the boundary between
two different rate outcomes in a way that depends on an unstated
day-counting convention (day counts are always whole calendar days,
no time-of-day or timezone component anywhere in the data).
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from datetime import date as Date
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class OwnershipRecord:
    owner: str
    owned: str
    stake_pct: float
    effective_from: Date
    effective_to: Date  # exclusive


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
    entities: Dict[str, str]  # entity_id -> jurisdiction
    ownership: List[OwnershipRecord]
    payments: List[Payment]
    fx_rates: Dict[Tuple[str, int, int], float]  # (currency, year, month) -> rate to USD
    statutory_rate: float
    treaty_partners: Dict[str, float]  # jurisdiction -> treaty rate
    threshold_usd: float
    holding_period_days: int = 365


def _round2(x: float) -> float:
    # Standard round-half-up at 2 decimals, applied only at output time.
    import decimal
    return float(decimal.Decimal(str(x)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def fx_rate(scenario: ScenarioData, currency: str, on_date: Date) -> float:
    return scenario.fx_rates[(currency, on_date.year, on_date.month)]


def relevant_parent(scenario: ScenarioData, entity: str, on_date: Date, _depth: int = 0) -> str:
    if _depth > len(scenario.entities) + 2:
        raise RuntimeError(f"ownership cycle detected involving {entity}")
    owner_record = None
    for rec in scenario.ownership:
        if rec.owned == entity and rec.effective_from <= on_date < rec.effective_to:
            owner_record = rec
            break
    if owner_record is None:
        return entity
    if owner_record.stake_pct > 50:
        return relevant_parent(scenario, owner_record.owner, on_date, _depth + 1)
    return owner_record.owner


def holding_days(payment: Payment) -> int:
    return (payment.payment_date - payment.acquisition_date).days


def base_rate_for_payment(scenario: ScenarioData, payment: Payment) -> Tuple[float, str]:
    """Returns (rate, relevant_parent_jurisdiction) BEFORE any threshold re-rating."""
    parent = relevant_parent(scenario, payment.payee, payment.payment_date)
    parent_jur = scenario.entities.get(parent, parent)
    treaty_rate = scenario.treaty_partners.get(parent_jur)
    if treaty_rate is not None and holding_days(payment) >= scenario.holding_period_days:
        return treaty_rate, parent_jur
    return scenario.statutory_rate, parent_jur


def compute_report(scenario: ScenarioData) -> Dict:
    # Pass 1: base (pre-threshold) rate and USD amount for every payment.
    base_rate: Dict[str, float] = {}
    usd_amount: Dict[str, float] = {}
    for p in scenario.payments:
        rate, _ = base_rate_for_payment(scenario, p)
        base_rate[p.payment_id] = rate
        usd_amount[p.payment_id] = p.amount * fx_rate(scenario, p.currency, p.payment_date)

    # Pass 2: cumulative per-payee-per-year USD total, determine breach.
    running: Dict[Tuple[str, int], float] = {}
    for p in scenario.payments:
        key = (p.payee, p.payment_date.year)
        running[key] = running.get(key, 0.0) + usd_amount[p.payment_id]
    breached = {key for key, total in running.items() if total > scenario.threshold_usd}

    # Pass 3: final rate (after retroactive re-rating) and reported figures.
    lines = []
    grand_total = 0.0
    for p in scenario.payments:
        key = (p.payee, p.payment_date.year)
        initial_rate = base_rate[p.payment_id]
        final_rate = scenario.statutory_rate if key in breached else initial_rate
        initial_withholding = usd_amount[p.payment_id] * initial_rate
        final_withholding = usd_amount[p.payment_id] * final_rate
        true_up = final_withholding - initial_withholding
        lines.append({
            "payment_id": p.payment_id,
            "payee": p.payee,
            "initial_rate": initial_rate,
            "final_rate": final_rate,
            "initial_withholding_usd": _round2(initial_withholding),
            "final_withholding_usd": _round2(final_withholding),
            "true_up_usd": _round2(true_up),
        })
        grand_total += final_withholding

    return {
        "payments": lines,
        "total_liability_usd": _round2(grand_total),
    }


# ---------------------------------------------------------------- I/O

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
