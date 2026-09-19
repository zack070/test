"""
Buggy implementation: structurally the same as model_correct.py but with
three independently-introduced, silent bugs, each a different mechanism:

  BUG 1 (tie-break): FIFO order uses (receipt_date, unit_cost) instead of
    (receipt_date, lot_id) as the tie-break -- only wrong when two lots
    for the same sku share a receipt_date.
  BUG 2 (correction semantics): a CORRECTION is processed as a brand-new
    pick of corrected_qty WITHOUT first reversing the original pick's
    consumption -- only wrong for skus with a CORRECTION event.
  BUG 3 (deferred cycle counts): CYCLE_COUNT events are collected and
    applied all at once at the very end, instead of in their correct
    sequence position -- only wrong for skus where a pick/receipt with a
    later seq than a cycle count occurs before end-of-processing.
"""


class Lot:
    def __init__(self, lot_id, sku, receipt_date, unit_cost, qty):
        self.lot_id = lot_id
        self.sku = sku
        self.receipt_date = receipt_date
        self.unit_cost = unit_cost
        self.remaining_qty = qty


def run(events):
    lots_by_sku = {}
    deferred_cycle_counts = []  # BUG 3: collected instead of applied in-place

    def fifo_order(sku):
        # BUG 1: tie-break by unit_cost instead of lot_id
        return sorted(lots_by_sku.get(sku, []), key=lambda l: (l.receipt_date, l.unit_cost))

    def do_pick(sku, qty):
        remaining = qty
        for lot in fifo_order(sku):
            if remaining <= 0:
                break
            take = min(lot.remaining_qty, remaining)
            if take > 0:
                lot.remaining_qty -= take
                remaining -= take

    events_sorted = sorted(events, key=lambda e: e["seq"])

    for e in events_sorted:
        etype = e["type"]
        if etype == "RECEIPT":
            lot = Lot(e["lot_id"], e["sku"], e["receipt_date"], e["unit_cost"], e["qty"])
            lots_by_sku.setdefault(e["sku"], []).append(lot)

        elif etype == "PICK":
            do_pick(e["sku"], e["qty"])

        elif etype == "CORRECTION":
            # BUG 2: no reversal of the original pick's consumption --
            # just does a fresh pick of corrected_qty on top.
            orig_sku = e["sku"]
            do_pick(orig_sku, e["corrected_qty"])

        elif etype == "CYCLE_COUNT":
            deferred_cycle_counts.append(e)

    # BUG 3: apply all cycle counts here, after everything else, instead
    # of at their correct position in the sequence.
    for e in deferred_cycle_counts:
        for lot in lots_by_sku.get(e["sku"], []):
            if lot.lot_id == e["lot_id"]:
                lot.remaining_qty = e["true_qty"]
                break

    report = {}
    for sku, lots in lots_by_sku.items():
        qty = sum(l.remaining_qty for l in lots)
        val = sum(l.remaining_qty * l.unit_cost for l in lots)
        report[sku] = {"on_hand_qty": qty, "valuation": round(val, 2)}
    return report
