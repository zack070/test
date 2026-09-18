"""
Structural scenario generator for cash-sweep sample/held-out scenarios.

Builds a full trading day by embedding several independently-verified
swap-tension gadgets (dev/find_swap_gadget.search(), each already
confirmed to beat every tested greedy probe by a comfortable margin AND
to be reachable exactly by a genuinely online policy -- see
dev/verify_online_reference.py) on their own disjoint currency quartets,
padding with easy single-route filler obligations and a few mid-day
credits so the day reads like a real desk's day, not a bipartite-matching
puzzle wearing a business costume. Each gadget's 4 currencies (2 funding
sources, 2 obligation sinks) are dedicated to that gadget alone -- no
sharing across gadgets or with filler -- so the exhaustively-verified
528-instance property (greedy always fails, a correctly-deferring online
policy always reaches the true optimum) carries over into the full
scenario without any unverified cross-gadget interaction.
"""
from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "environment", "sim"))
from simulator import CreditSpec, ObligationSpec  # noqa: E402
from find_swap_gadget import search as search_gadgets  # noqa: E402

HOME = "USD"
SPOKE_POOL = [
    "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "SGD", "HKD", "NZD",
    "SEK", "NOK", "MXN", "ZAR", "INR", "BRL", "DKK", "PLN", "THB",
]


@dataclass
class Scenario:
    currencies: List[str]
    spread_cheap: Dict[Tuple[str, str], float]
    spread_expensive: Dict[Tuple[str, str], float]
    cutoff_time: Dict[Tuple[str, str], int]
    starting_balances: Dict[str, float]
    credits: List[CreditSpec]
    obligations: List[ObligationSpec]
    horizon: int
    gadget_count: int = 0
    filler_count: int = 0


def _embed_gadget(sc_currencies, spread_cheap, spread_expensive, cutoff_time,
                   starting_balances, obligations, gadget, src_a, src_b, sink_c, sink_d,
                   time_offset, idx, rng):
    sc_currencies.update([src_a, src_b, sink_c, sink_d])
    pairs = {
        (src_a, sink_c): gadget["r_ac"],
        (src_a, sink_d): gadget["r_ad"],
        (src_b, sink_c): gadget["r_bc"],
        (src_b, sink_d): gadget["r_bd"],
    }
    cutoff = time_offset + gadget["cutoff"]
    for pair, cheap in pairs.items():
        spread_cheap[pair] = cheap
        spread_expensive[pair] = round(cheap * rng.uniform(2.2, 3.5), 5)
        cutoff_time[pair] = cutoff
    starting_balances[src_a] = starting_balances.get(src_a, 0.0) + gadget["amount"]
    starting_balances[src_b] = starting_balances.get(src_b, 0.0) + gadget["amount"]
    obligations.append(ObligationSpec(
        f"GADGET{idx}_C", sink_c, gadget["amount"],
        due_time=time_offset + gadget["due"], arrival_time=time_offset + gadget["arr_c"],
    ))
    obligations.append(ObligationSpec(
        f"GADGET{idx}_D", sink_d, gadget["amount"],
        due_time=time_offset + gadget["due"], arrival_time=time_offset + gadget["arr_d"],
    ))
    return cutoff, time_offset + gadget["due"]


def _add_filler(sc_currencies, spread_cheap, spread_expensive, cutoff_time,
                 starting_balances, obligations, sink, amount, rate, cutoff,
                 due_time, arrival_time, idx):
    sc_currencies.add(sink)
    pair = (HOME, sink)
    spread_cheap[pair] = rate
    spread_expensive[pair] = round(rate * 2.5, 5)
    cutoff_time[pair] = cutoff
    obligations.append(ObligationSpec(f"FILL{idx}", sink, amount, due_time=due_time, arrival_time=arrival_time))


def generate_scenario(seed: int, n_gadgets: int, n_filler: int, home_balance: float,
                       mid_day_credit: bool, gadget_pool_trials: int = 2000) -> Scenario:
    rng = random.Random(seed)
    gadgets = search_gadgets(n_trials=gadget_pool_trials, seed=seed)
    rng.shuffle(gadgets)
    if len(gadgets) < n_gadgets:
        raise ValueError(f"only found {len(gadgets)} verified gadgets, need {n_gadgets}")

    sc_currencies = {HOME}
    spread_cheap: Dict[Tuple[str, str], float] = {}
    spread_expensive: Dict[Tuple[str, str], float] = {}
    cutoff_time: Dict[Tuple[str, str], int] = {}
    starting_balances: Dict[str, float] = {HOME: home_balance}
    obligations: List[ObligationSpec] = []
    credits: List[CreditSpec] = []

    spoke_pool = list(SPOKE_POOL)
    rng.shuffle(spoke_pool)
    pool_iter = iter(spoke_pool)

    latest_due = 0
    gadget_time_step = rng.choice([90, 110, 140])
    for i in range(n_gadgets):
        gadget = gadgets[i]
        src_a, src_b, sink_c, sink_d = next(pool_iter), next(pool_iter), next(pool_iter), next(pool_iter)
        time_offset = i * gadget_time_step
        cutoff, due = _embed_gadget(
            sc_currencies, spread_cheap, spread_expensive, cutoff_time,
            starting_balances, obligations, gadget, src_a, src_b, sink_c, sink_d,
            time_offset, i, rng,
        )
        latest_due = max(latest_due, due)

    for i in range(n_filler):
        sink = next(pool_iter, None)
        if sink is None:
            sink = f"FIL{i}"
        amount = rng.choice([100.0, 200.0, 300.0, 400.0])
        rate = round(rng.uniform(0.004, 0.015), 5)
        due_time = rng.randint(20, latest_due + 60)
        arrival_time = max(0, due_time - rng.randint(30, 90))
        cutoff = max(arrival_time + 5, due_time - rng.randint(5, 20))
        _add_filler(
            sc_currencies, spread_cheap, spread_expensive, cutoff_time,
            starting_balances, obligations, sink, amount, rate, cutoff,
            due_time, arrival_time, i,
        )

    horizon = latest_due + 60
    if mid_day_credit:
        credit_currency = HOME
        credits.append(CreditSpec("CR1", credit_currency, home_balance * 0.4, arrival_time=max(1, latest_due // 3)))

    return Scenario(
        currencies=sorted(sc_currencies),
        spread_cheap=spread_cheap,
        spread_expensive=spread_expensive,
        cutoff_time=cutoff_time,
        starting_balances=starting_balances,
        credits=credits,
        obligations=obligations,
        horizon=horizon,
        gadget_count=n_gadgets,
        filler_count=n_filler,
    )


def write_scenario(scenario: Scenario, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump({
            "currencies": scenario.currencies,
            "starting_balances": scenario.starting_balances,
            "horizon": scenario.horizon,
        }, f, indent=2)

    with open(os.path.join(out_dir, "rates.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_currency", "to_currency", "cheap_rate", "expensive_rate", "cutoff_time"])
        for (frm, to), cheap in sorted(scenario.spread_cheap.items()):
            w.writerow([frm, to, cheap, scenario.spread_expensive[(frm, to)], scenario.cutoff_time[(frm, to)]])

    with open(os.path.join(out_dir, "obligations.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["obligation_id", "currency", "amount", "due_time", "arrival_time"])
        for o in sorted(scenario.obligations, key=lambda o: (o.arrival_time, o.obligation_id)):
            w.writerow([o.obligation_id, o.currency, o.amount, o.due_time, o.arrival_time])

    with open(os.path.join(out_dir, "credits.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["credit_id", "currency", "amount", "arrival_time"])
        for c in sorted(scenario.credits, key=lambda c: c.arrival_time):
            w.writerow([c.credit_id, c.currency, c.amount, c.arrival_time])


def load_scenario(data_dir: str) -> Scenario:
    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)
    spread_cheap, spread_expensive, cutoff_time = {}, {}, {}
    with open(os.path.join(data_dir, "rates.csv"), newline="") as f:
        for r in csv.DictReader(f):
            pair = (r["from_currency"], r["to_currency"])
            spread_cheap[pair] = float(r["cheap_rate"])
            spread_expensive[pair] = float(r["expensive_rate"])
            cutoff_time[pair] = int(r["cutoff_time"])
    obligations = []
    with open(os.path.join(data_dir, "obligations.csv"), newline="") as f:
        for r in csv.DictReader(f):
            obligations.append(ObligationSpec(
                r["obligation_id"], r["currency"], float(r["amount"]),
                due_time=int(r["due_time"]), arrival_time=int(r["arrival_time"]),
            ))
    credits = []
    with open(os.path.join(data_dir, "credits.csv"), newline="") as f:
        for r in csv.DictReader(f):
            credits.append(CreditSpec(r["credit_id"], r["currency"], float(r["amount"]), arrival_time=int(r["arrival_time"])))
    return Scenario(
        currencies=cfg["currencies"],
        spread_cheap=spread_cheap,
        spread_expensive=spread_expensive,
        cutoff_time=cutoff_time,
        starting_balances=cfg["starting_balances"],
        credits=credits,
        obligations=obligations,
        horizon=cfg["horizon"],
    )
