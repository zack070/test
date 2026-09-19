#!/usr/bin/env python3
"""Cheat / adversarial baseline: a fresh implementation written from the
spec's rules rather than by patching the shipped pipeline -- tests
whether bypassing the "debug existing code" framing and just
reimplementing is an easy escape hatch. Uses two natural, non-malicious
shortcuts a reasonably careful but efficient engineer might reach for:
relying on Python's stable sort to preserve receipt/append order instead
of an explicit lot_id tie-break key, and a net-delta correction instead
of fully reversing the original pick before redoing it. Cycle-count
handling is implemented correctly here, to isolate whether these two
particular shortcuts independently cause failures."""
from __future__ import annotations

import json
import sys


class Lot:
    def __init__(self, lot_id, sku, receipt_date, unit_cost, qty):
        self.lot_id, self.sku = lot_id, sku
        self.receipt_date, self.unit_cost, self.remaining_qty = receipt_date, unit_cost, qty


def run(data_dir):
    with open(f"{data_dir}/events.json") as f:
        events = json.load(f)

    lots_by_sku = {}
    last_pick_qty = {}

    def fifo(sku):
        # shortcut: sort by date only, relying on stable sort + the order
        # lots were appended in (receipt order)
        return sorted(lots_by_sku.get(sku, []), key=lambda l: l.receipt_date)

    def consume(sku, qty):
        remaining = qty
        for lot in fifo(sku):
            if remaining <= 0:
                break
            take = min(lot.remaining_qty, remaining)
            if take > 0:
                lot.remaining_qty -= take
                remaining -= take

    def give_back(sku, qty):
        order = fifo(sku)
        if order:
            order[-1].remaining_qty += qty

    def find(sku, lot_id):
        for lot in lots_by_sku.get(sku, []):
            if lot.lot_id == lot_id:
                return lot
        return None

    for e in sorted(events, key=lambda e: e["seq"]):
        t = e["type"]
        if t == "RECEIPT":
            lots_by_sku.setdefault(e["sku"], []).append(
                Lot(e["lot_id"], e["sku"], e["receipt_date"], e["unit_cost"], e["qty"]))
        elif t == "PICK":
            consume(e["sku"], e["qty"])
            last_pick_qty[e["seq"]] = e["qty"]
        elif t == "CORRECTION":
            # shortcut: net-delta adjustment instead of reverse-then-redo
            orig_qty = last_pick_qty[e["corrects_seq"]]
            delta = e["corrected_qty"] - orig_qty
            if delta > 0:
                consume(e["sku"], delta)
            elif delta < 0:
                give_back(e["sku"], -delta)
        elif t == "CYCLE_COUNT":
            lot = find(e["sku"], e["lot_id"])
            if lot:
                lot.remaining_qty = e["true_qty"]

    skus = {}
    for sku, lots in lots_by_sku.items():
        qty = sum(l.remaining_qty for l in lots)
        val = sum(l.remaining_qty * l.unit_cost for l in lots)
        skus[sku] = {"on_hand_qty": qty, "valuation": round(val, 2)}
    return {"skus": skus}


def main():
    data_dir, output_path = sys.argv[1], sys.argv[2]
    with open(output_path, "w") as f:
        json.dump(run(data_dir), f)


if __name__ == "__main__":
    main()
