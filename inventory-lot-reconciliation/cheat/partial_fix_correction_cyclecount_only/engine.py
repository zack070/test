#!/usr/bin/env python3
"""Cheat / adversarial baseline: fixes the correction and cycle-count
bugs but leaves the tie-break bug in place."""
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
    pick_log = {}

    def fifo(sku):
        # NOT FIXED: tie-break by unit_cost instead of lot_id
        return sorted(lots_by_sku.get(sku, []), key=lambda l: (l.receipt_date, l.unit_cost))

    def consume(sku, qty):
        remaining = qty
        consumed = []
        for lot in fifo(sku):
            if remaining <= 0:
                break
            take = min(lot.remaining_qty, remaining)
            if take > 0:
                lot.remaining_qty -= take
                remaining -= take
                consumed.append((lot.lot_id, take))
        return consumed

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
            pick_log[e["seq"]] = (e["sku"], consume(e["sku"], e["qty"]))
        elif t == "CORRECTION":
            sku = e["sku"]
            _, orig = pick_log[e["corrects_seq"]]  # FIXED: reverse original
            for lot_id, amt in orig:
                find(sku, lot_id).remaining_qty += amt
            pick_log[e["seq"]] = (sku, consume(sku, e["corrected_qty"]))
        elif t == "CYCLE_COUNT":
            # FIXED: applied in-sequence, not deferred
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
