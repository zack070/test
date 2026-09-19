"""
Nightly inventory reconciliation engine.

Processes the day's warehouse event stream (receipts, picks, quantity
corrections, cycle-count adjustments) against lot-tracked SKU inventory
and produces a per-SKU on-hand quantity and valuation report.

See /app/INVENTORY_SPEC.md for the full rules this is supposed to
implement.
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
    """Holds all lots, grouped by SKU."""

    def __init__(self):
        self.lots_by_sku: dict[str, list[Lot]] = {}

    def add_lot(self, lot: Lot):
        self.lots_by_sku.setdefault(lot.sku, []).append(lot)

    def fifo_candidates(self, sku: str) -> list[Lot]:
        """Lots for a sku, in the order they should be consumed from."""
        lots = self.lots_by_sku.get(sku, [])
        # FIFO by receipt date; same-day receipts are broken by unit cost,
        # cheapest first, so valuation stays conservative on ties.
        return sorted(lots, key=lambda l: (l.receipt_date, l.unit_cost))

    def find_lot(self, sku: str, lot_id: str) -> Lot | None:
        for lot in self.lots_by_sku.get(sku, []):
            if lot.lot_id == lot_id:
                return lot
        return None


def consume_fifo(state: InventoryState, sku: str, qty: float) -> None:
    """Consume qty units from a sku's lots in FIFO order."""
    remaining = qty
    for lot in state.fifo_candidates(sku):
        if remaining <= 0:
            break
        take = min(lot.remaining_qty, remaining)
        if take > 0:
            lot.remaining_qty -= take
            remaining -= take


def apply_receipt(state: InventoryState, event: dict) -> None:
    lot = Lot(event["lot_id"], event["sku"], event["receipt_date"], event["unit_cost"], event["qty"])
    state.add_lot(lot)


def apply_pick(state: InventoryState, event: dict) -> None:
    consume_fifo(state, event["sku"], event["qty"])


def apply_correction(state: InventoryState, event: dict) -> None:
    """A correction amends a previous pick's quantity. The corrected
    amount is picked fresh against current inventory state."""
    consume_fifo(state, event["sku"], event["corrected_qty"])


def apply_cycle_count(state: InventoryState, event: dict, deferred: list) -> None:
    """Cycle counts are reconciled as a separate end-of-run pass, after
    the transactional event stream has been fully processed, so that a
    single reconciliation pass can be audited independently of the
    day's transaction log."""
    deferred.append(event)


def reconcile_cycle_counts(state: InventoryState, deferred: list) -> None:
    for event in deferred:
        lot = state.find_lot(event["sku"], event["lot_id"])
        if lot is not None:
            lot.remaining_qty = event["true_qty"]


def process_events(events: list[dict]) -> InventoryState:
    state = InventoryState()
    deferred_cycle_counts: list = []

    for event in sorted(events, key=lambda e: e["seq"]):
        etype = event["type"]
        if etype == "RECEIPT":
            apply_receipt(state, event)
        elif etype == "PICK":
            apply_pick(state, event)
        elif etype == "CORRECTION":
            apply_correction(state, event)
        elif etype == "CYCLE_COUNT":
            apply_cycle_count(state, event, deferred_cycle_counts)
        else:
            raise ValueError(f"unknown event type: {etype}")

    reconcile_cycle_counts(state, deferred_cycle_counts)
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
