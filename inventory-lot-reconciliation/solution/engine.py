"""
Nightly inventory reconciliation engine (corrected).

Processes the day's warehouse event stream (receipts, picks, quantity
corrections, cycle-count adjustments) against lot-tracked SKU inventory
and produces a per-SKU on-hand quantity and valuation report, per
/app/INVENTORY_SPEC.md.
"""
from __future__ import annotations

import json
import sys


class Lot:
    __slots__ = ("lot_id", "sku", "receipt_date", "unit_cost", "remaining_qty")

    def __init__(self, lot_id, sku, receipt_date, unit_cost, qty):
        self.lot_id = lot_id
        self.sku = sku
        self.receipt_date = receipt_date
        self.unit_cost = unit_cost
        self.remaining_qty = qty


class InventoryState:
    def __init__(self):
        self.lots_by_sku: dict[str, list[Lot]] = {}

    def add_lot(self, lot: Lot):
        self.lots_by_sku.setdefault(lot.sku, []).append(lot)

    def fifo_candidates(self, sku: str) -> list[Lot]:
        lots = self.lots_by_sku.get(sku, [])
        # FIFO by receipt date; same-day receipts broken by lot_id
        # ascending (the disclosed tie-break rule).
        return sorted(lots, key=lambda l: (l.receipt_date, l.lot_id))

    def find_lot(self, sku: str, lot_id: str) -> Lot | None:
        for lot in self.lots_by_sku.get(sku, []):
            if lot.lot_id == lot_id:
                return lot
        return None


def consume_fifo(state: InventoryState, sku: str, qty: float) -> list[tuple[str, float]]:
    """Consume qty units from a sku's lots in FIFO order. Returns exactly
    which lots were drawn from and how much, for use by corrections."""
    remaining = qty
    consumed = []
    for lot in state.fifo_candidates(sku):
        if remaining <= 0:
            break
        take = min(lot.remaining_qty, remaining)
        if take > 0:
            lot.remaining_qty -= take
            remaining -= take
            consumed.append((lot.lot_id, take))
    return consumed


def apply_receipt(state: InventoryState, event: dict) -> None:
    lot = Lot(event["lot_id"], event["sku"], event["receipt_date"], event["unit_cost"], event["qty"])
    state.add_lot(lot)


def apply_pick(state: InventoryState, event: dict, pick_log: dict) -> None:
    consumed = consume_fifo(state, event["sku"], event["qty"])
    pick_log[event["seq"]] = (event["sku"], consumed)


def apply_correction(state: InventoryState, event: dict, pick_log: dict) -> None:
    """A correction fully reverses the original pick's exact consumption,
    then re-picks the corrected quantity against current inventory state
    (which may differ from the state at the time of the original pick)."""
    orig_sku, orig_consumed = pick_log[event["corrects_seq"]]
    for lot_id, amount in orig_consumed:
        lot = state.find_lot(orig_sku, lot_id)
        lot.remaining_qty += amount
    consumed = consume_fifo(state, orig_sku, event["corrected_qty"])
    pick_log[event["seq"]] = (orig_sku, consumed)


def apply_cycle_count(state: InventoryState, event: dict) -> None:
    """Cycle counts take effect immediately, at their position in the
    event sequence -- not deferred, since later events in the same run
    must see the corrected quantity."""
    lot = state.find_lot(event["sku"], event["lot_id"])
    if lot is not None:
        lot.remaining_qty = event["true_qty"]


def process_events(events: list[dict]) -> InventoryState:
    state = InventoryState()
    pick_log: dict = {}

    for event in sorted(events, key=lambda e: e["seq"]):
        etype = event["type"]
        if etype == "RECEIPT":
            apply_receipt(state, event)
        elif etype == "PICK":
            apply_pick(state, event, pick_log)
        elif etype == "CORRECTION":
            apply_correction(state, event, pick_log)
        elif etype == "CYCLE_COUNT":
            apply_cycle_count(state, event)
        else:
            raise ValueError(f"unknown event type: {etype}")

    return state


def build_report(state: InventoryState) -> dict:
    skus = {}
    for sku, lots in state.lots_by_sku.items():
        qty = sum(l.remaining_qty for l in lots)
        val = sum(l.remaining_qty * l.unit_cost for l in lots)
        skus[sku] = {"on_hand_qty": qty, "valuation": round(val, 2)}
    return {"skus": skus}


def run(data_dir: str) -> dict:
    with open(f"{data_dir}/events.json") as f:
        events = json.load(f)
    state = process_events(events)
    return build_report(state)


def main():
    data_dir = sys.argv[1]
    output_path = sys.argv[2]
    report = run(data_dir)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
