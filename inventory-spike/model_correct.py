"""
Correct reference implementation of the warehouse inventory reconciliation
rules. This IS the disclosed spec once written up in prose.

Entities:
  Lot: {lot_id, sku, receipt_date, unit_cost, remaining_qty}

Events (each has a unique `seq`, the total processing order; no ties):
  RECEIPT(seq, sku, lot_id, receipt_date, unit_cost, qty)
    -> creates a new lot with remaining_qty = qty.
  PICK(seq, sku, qty)
    -> consumes qty from the sku's lots via FIFO: lots are ordered by
       (receipt_date ascending, lot_id ascending as the tie-break when two
       lots share a receipt_date), consuming from the earliest lot first,
       moving to the next lot once one is exhausted. Records exactly which
       lot(s) and how much were consumed (needed if this pick is later
       corrected).
  CORRECTION(seq, sku, corrects_seq, corrected_qty)
    -> corrects_seq must refer to an earlier PICK event. First, reverse
       that PICK's exact recorded consumption (restore each affected lot's
       remaining_qty by the amount that pick took from it). Then perform a
       brand-new FIFO pick of `corrected_qty` against the CURRENT lot
       state (which may differ from the state at the time of the original
       pick, since other events may have occurred in between).
  CYCLE_COUNT(seq, sku, lot_id, true_qty)
    -> sets that lot's remaining_qty to true_qty directly, applied in
       sequence order like any other event (i.e. before any later-seq
       event touches that sku's lots).

Output: for each sku, on-hand quantity (sum of remaining_qty across its
lots) and valuation (sum of remaining_qty * unit_cost across its lots).
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
    pick_consumption_log = {}  # seq -> [(lot_id, amount_taken), ...]

    def fifo_order(sku):
        return sorted(lots_by_sku.get(sku, []), key=lambda l: (l.receipt_date, l.lot_id))

    def do_pick(sku, qty):
        remaining = qty
        consumed = []
        for lot in fifo_order(sku):
            if remaining <= 0:
                break
            take = min(lot.remaining_qty, remaining)
            if take > 0:
                lot.remaining_qty -= take
                remaining -= take
                consumed.append((lot.lot_id, take))
        return consumed

    events_sorted = sorted(events, key=lambda e: e["seq"])

    for e in events_sorted:
        etype = e["type"]
        if etype == "RECEIPT":
            lot = Lot(e["lot_id"], e["sku"], e["receipt_date"], e["unit_cost"], e["qty"])
            lots_by_sku.setdefault(e["sku"], []).append(lot)

        elif etype == "PICK":
            consumed = do_pick(e["sku"], e["qty"])
            pick_consumption_log[e["seq"]] = (e["sku"], consumed)

        elif etype == "CORRECTION":
            orig_sku = e["sku"]
            _, orig_consumed = pick_consumption_log[e["corrects_seq"]]
            lots_index = {l.lot_id: l for l in lots_by_sku.get(orig_sku, [])}
            for lot_id, amount in orig_consumed:
                lots_index[lot_id].remaining_qty += amount
            consumed = do_pick(orig_sku, e["corrected_qty"])
            pick_consumption_log[e["seq"]] = (orig_sku, consumed)

        elif etype == "CYCLE_COUNT":
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
