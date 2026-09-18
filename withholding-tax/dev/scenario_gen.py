"""
Scenario generator for withholding-tax sample/held-out scenarios.

Embeds two independently-validated traps (see dev/spike.py and
dev/spike2_ownership.py) on dedicated, non-overlapping payees so each
trap's tested property carries over cleanly into a full scenario, plus
filler payees with unambiguous treatment for volume/realism, plus a
handful of exact-boundary cases (holding period == 365 days, cumulative
total == threshold exactly, ownership stake == 50% exactly) that exist
specifically so the ablation checks in dev/ablation.py have something
real to probe. All entity/payment IDs are neutral and sequential --
never named in a way that reveals which are traps and which are filler
(see the sibling cash-sweep bundle's cheat/README.md for why this
matters: an obligation/payment ID that spells out its own role is a
side channel, not a detail).
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

JURISDICTIONS_TREATY = {
    "JUR-DE": 0.10, "JUR-FR": 0.12, "JUR-SG": 0.08, "JUR-LU": 0.05,
}
JURISDICTIONS_NO_TREATY = ["JUR-KY", "JUR-BVI", "JUR-PA", "JUR-BR"]
ALL_JURISDICTIONS = list(JURISDICTIONS_TREATY) + JURISDICTIONS_NO_TREATY
CURRENCIES = ["EUR", "GBP", "SGD", "BRL", "AUD"]
STATUTORY_RATE = 0.30
THRESHOLD_USD = 500_000.0
HOLDING_PERIOD_DAYS = 365
YEAR = 2024


@dataclass
class Entity:
    entity_id: str
    jurisdiction: str


@dataclass
class OwnershipRow:
    owner: str
    owned: str
    stake_pct: float
    effective_from: date
    effective_to: date


@dataclass
class PaymentRow:
    payment_id: str
    payee: str
    amount: float
    currency: str
    payment_date: date
    acquisition_date: date


@dataclass
class Builder:
    entities: Dict[str, Entity] = field(default_factory=dict)
    ownership: List[OwnershipRow] = field(default_factory=list)
    payments: List[PaymentRow] = field(default_factory=list)
    _entity_seq: int = 0
    _payment_seq: int = 0

    def new_entity(self, jurisdiction: str) -> str:
        self._entity_seq += 1
        eid = f"ENT{self._entity_seq:04d}"
        self.entities[eid] = Entity(eid, jurisdiction)
        return eid

    def new_payment(self, payee: str, amount: float, currency: str, payment_date: date, acquisition_date: date) -> str:
        self._payment_seq += 1
        pid = f"PAY{self._payment_seq:04d}"
        self.payments.append(PaymentRow(pid, payee, amount, currency, payment_date, acquisition_date))
        return pid


def _d(y, m, d_):
    return date(y, m, d_)


def _with_cents(rng: random.Random, base: float) -> float:
    """Adds a few random cents to an otherwise round amount so that
    amount * fx_rate essentially never lands on an exact 2-decimal value
    by coincidence -- needed so the round_intermediate ablation (rounding
    before vs. after applying the rate) has something real to catch."""
    return round(base + rng.uniform(0.0, 99.0), 2)


def embed_threshold_gadget(b: Builder, rng: random.Random, currency: str):
    """Payee whose payments individually qualify for treaty rate, but
    whose cumulative USD total crosses THRESHOLD_USD partway through the
    year -- validated (dev/spike.py) to require retroactive re-rating of
    already-processed payments, not just the triggering one."""
    jur = rng.choice(list(JURISDICTIONS_TREATY))
    payee = b.new_entity(jur)  # no owner record -> payee itself is its own relevant parent
    acquisition = _d(YEAR - 2, 1, 1)  # well over a year before any payment -> holding period always satisfied
    # Amounts are in the payment's own (foreign) currency and get
    # converted to USD at whatever that currency's rate happens to be
    # (base FX rate is drawn from [0.7, 1.4], with up to +-12% monthly
    # wobble on top -- worst case around 0.6). Three payments must clear
    # THRESHOLD_USD even at that worst case, or the embedded trap
    # silently fails to fire depending on which currency/seed it drew:
    # 3 * 290,000 * 0.6 = 522,000 > 500,000 with real margin.
    per_payment = _with_cents(rng, rng.choice([290_000.0, 310_000.0, 330_000.0]))
    n_payments = 3
    months = sorted(rng.sample(range(2, 11), n_payments))
    for m in months:
        b.new_payment(payee, per_payment, currency, _d(YEAR, m, rng.randint(1, 27)), acquisition)
    return payee


def embed_ownership_timing_gadget(b: Builder, rng: random.Random, currency: str):
    """Payee owned by an intermediate entity whose stake crosses the 50%
    boundary partway through the year; the intermediate entity's own
    jurisdiction has a treaty, its own parent's does not -- validated
    (dev/spike2_ownership.py) to require resolving the relevant parent
    separately per payment date, not once for the payee."""
    treaty_jur = rng.choice(list(JURISDICTIONS_TREATY))
    no_treaty_jur = rng.choice(JURISDICTIONS_NO_TREATY)
    payee = b.new_entity(rng.choice(ALL_JURISDICTIONS))
    mid = b.new_entity(treaty_jur)
    top = b.new_entity(no_treaty_jur)

    switch_month = rng.choice([5, 6, 7, 8])
    switch_date = _d(YEAR, switch_month, 1)
    high_stake = rng.choice([55.0, 60.0, 70.0])
    low_stake = rng.choice([30.0, 40.0, 45.0])
    b.ownership.append(OwnershipRow(mid, payee, high_stake, _d(YEAR, 1, 1), switch_date))
    b.ownership.append(OwnershipRow(mid, payee, low_stake, switch_date, _d(YEAR + 1, 1, 1)))
    b.ownership.append(OwnershipRow(top, mid, 100.0, _d(YEAR, 1, 1), _d(YEAR + 1, 1, 1)))

    acquisition = _d(YEAR - 2, 1, 1)
    amount = _with_cents(rng, rng.choice([80_000.0, 100_000.0, 120_000.0]))
    before_month = rng.randint(2, switch_month - 1) if switch_month > 2 else 2
    after_month = rng.randint(switch_month, 11)
    b.new_payment(payee, amount, currency, _d(YEAR, before_month, rng.randint(1, 27)), acquisition)
    b.new_payment(payee, amount, currency, _d(YEAR, after_month, rng.randint(1, 27)), acquisition)
    return payee


def embed_filler(b: Builder, rng: random.Random, currency: str):
    """A payee with unambiguous treatment: either clearly treaty-eligible
    throughout (no owner, treaty jurisdiction, long holding period, well
    under threshold) or clearly not (no-treaty jurisdiction, or a short
    holding period) -- adds volume and realism without adding difficulty."""
    kind = rng.choice(["clear_treaty", "clear_no_treaty_jurisdiction", "clear_short_holding"])
    amount = _with_cents(rng, rng.choice([30_000.0, 50_000.0, 70_000.0]))
    pay_date = _d(YEAR, rng.randint(2, 11), rng.randint(1, 27))
    if kind == "clear_treaty":
        payee = b.new_entity(rng.choice(list(JURISDICTIONS_TREATY)))
        acquisition = _d(YEAR - 2, 1, 1)
    elif kind == "clear_no_treaty_jurisdiction":
        payee = b.new_entity(rng.choice(JURISDICTIONS_NO_TREATY))
        acquisition = _d(YEAR - 2, 1, 1)
    else:
        payee = b.new_entity(rng.choice(list(JURISDICTIONS_TREATY)))
        acquisition = pay_date - timedelta(days=rng.randint(30, 300))  # < 365 days
    b.new_payment(payee, amount, currency, pay_date, acquisition)


def embed_boundary_cases(b: Builder, rng: random.Random, currency: str):
    """Exact-boundary cases the ablation checks probe: holding period of
    precisely 365 days (qualifies) and 364 days (does not); an ownership
    stake of precisely 50% (does NOT continue the look-through -- the
    50%-holder itself is the relevant parent); a cumulative total that
    lands exactly on THRESHOLD_USD (does not trigger re-rating)."""
    treaty_jur = rng.choice(list(JURISDICTIONS_TREATY))

    payee_365 = b.new_entity(treaty_jur)
    pay_date = _d(YEAR, 9, 1)
    b.new_payment(payee_365, 40_000.0, currency, pay_date, pay_date - timedelta(days=365))

    payee_364 = b.new_entity(treaty_jur)
    b.new_payment(payee_364, 40_000.0, currency, pay_date, pay_date - timedelta(days=364))

    # Paid in "USD" (the reporting currency itself, rate fixed at 1.0 --
    # see write_scenario) specifically so this amount survives currency
    # conversion exactly, landing precisely on THRESHOLD_USD rather than
    # some FX-shifted value close to it.
    payee_exact_threshold = b.new_entity(treaty_jur)
    b.new_payment(payee_exact_threshold, THRESHOLD_USD, "USD", _d(YEAR, 4, 1), _d(YEAR - 2, 1, 1))

    payee_50 = b.new_entity(rng.choice(ALL_JURISDICTIONS))
    owner_at_50 = b.new_entity(treaty_jur)  # if the walk incorrectly continued past exactly 50%, this would matter
    grandparent_no_treaty = b.new_entity(rng.choice(JURISDICTIONS_NO_TREATY))
    b.ownership.append(OwnershipRow(owner_at_50, payee_50, 50.0, _d(YEAR, 1, 1), _d(YEAR + 1, 1, 1)))
    b.ownership.append(OwnershipRow(grandparent_no_treaty, owner_at_50, 100.0, _d(YEAR, 1, 1), _d(YEAR + 1, 1, 1)))
    b.new_payment(payee_50, 40_000.0, currency, _d(YEAR, 6, 1), _d(YEAR - 2, 1, 1))


def generate_scenario(seed: int, n_threshold_gadgets: int, n_ownership_gadgets: int, n_filler: int,
                       include_boundary_cases: bool = True, fx_seed: int = None) -> Builder:
    rng = random.Random(seed)
    b = Builder()
    threshold_payees = []
    ownership_payees = []
    for _ in range(n_threshold_gadgets):
        threshold_payees.append(embed_threshold_gadget(b, rng, rng.choice(CURRENCIES)))
    for _ in range(n_ownership_gadgets):
        ownership_payees.append(embed_ownership_timing_gadget(b, rng, rng.choice(CURRENCIES)))
    for _ in range(n_filler):
        embed_filler(b, rng, rng.choice(CURRENCIES))
    if include_boundary_cases:
        embed_boundary_cases(b, rng, rng.choice(CURRENCIES))

    _verify_gadgets_fire(b, threshold_payees, ownership_payees, fx_seed=fx_seed if fx_seed is not None else seed)
    return b


def _verify_gadgets_fire(b: Builder, threshold_payees, ownership_payees, fx_seed: int):
    """Hard assertion, not a hope: every embedded gadget must actually
    produce its intended tension once currency conversion is applied --
    a threshold gadget must genuinely breach, an ownership-timing gadget
    must genuinely produce two DIFFERENT rates for its two payments.
    Regenerating into a temp dir to run this through the real engine
    (with real FX rates) rather than re-deriving the logic here."""
    import tempfile
    import rule_engine as eng
    with tempfile.TemporaryDirectory() as tmp:
        write_scenario(b, tmp, fx_seed=fx_seed)
        sc = eng.load_scenario(tmp)

        running = {}
        for p in sc.payments:
            usd = p.amount * eng.fx_rate(sc, p.currency, p.payment_date)
            key = (p.payee, p.payment_date.year)
            running[key] = running.get(key, 0.0) + usd
        for payee in threshold_payees:
            total = sum(v for (pe, _), v in running.items() if pe == payee)
            assert total > sc.threshold_usd, (
                f"threshold gadget payee {payee} totaled {total:,.2f}, did not clear "
                f"threshold {sc.threshold_usd:,.2f} -- the embedded trap silently failed to fire"
            )

        by_payee = {}
        for p in sc.payments:
            by_payee.setdefault(p.payee, []).append(p)
        for payee in ownership_payees:
            rates = [eng.base_rate_for_payment(sc, p)[0] for p in by_payee[payee]]
            assert len(set(rates)) > 1, (
                f"ownership-timing gadget payee {payee} got the same rate {rates[0]} on both "
                f"payments -- the embedded trap silently failed to fire"
            )


def write_scenario(b: Builder, out_dir: str, fx_seed: int) -> None:
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "entities.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "jurisdiction"])
        for e in sorted(b.entities.values(), key=lambda e: e.entity_id):
            w.writerow([e.entity_id, e.jurisdiction])

    with open(os.path.join(out_dir, "ownership.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner", "owned", "stake_pct", "effective_from", "effective_to"])
        for o in sorted(b.ownership, key=lambda o: (o.owned, o.effective_from)):
            w.writerow([o.owner, o.owned, o.stake_pct, o.effective_from.isoformat(), o.effective_to.isoformat()])

    with open(os.path.join(out_dir, "payments.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["payment_id", "payee", "amount", "currency", "payment_date", "acquisition_date"])
        for p in sorted(b.payments, key=lambda p: p.payment_id):
            w.writerow([p.payment_id, p.payee, p.amount, p.currency, p.payment_date.isoformat(), p.acquisition_date.isoformat()])

    with open(os.path.join(out_dir, "fx_rates.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["currency", "year", "month", "rate_to_usd"])
        rng = random.Random(fx_seed)
        for cur in CURRENCIES:
            base = rng.uniform(0.7, 1.4)
            for m in range(1, 13):
                rate = round(base * (1.0 + 0.01 * rng.uniform(-1, 1) * m), 5)
                w.writerow([cur, YEAR, m, rate])
        # USD is the reporting currency itself -- always converts 1:1.
        for m in range(1, 13):
            w.writerow(["USD", YEAR, m, 1.0])

    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump({
            "statutory_rate": STATUTORY_RATE,
            "treaty_partners": JURISDICTIONS_TREATY,
            "threshold_usd": THRESHOLD_USD,
            "holding_period_days": HOLDING_PERIOD_DAYS,
        }, f, indent=2)
