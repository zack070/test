"""
A plausible 'reasonably careful but not exhaustive' fresh implementation,
written from natural-language spec understanding rather than by copying
model_correct.py's exact logic. Represents what a competent engineer who
reads the rules once and implements efficiently (not defensively) might
naturally write. Three deliberate natural shortcuts, one per rule:

  1. FIFO tie-break: sorts lots by receipt_date, relying on Python's
     stable sort to preserve whatever order the lots list was built in
     (append-on-receipt order), rather than explicitly sorting by lot_id
     as a secondary key -- a very natural "the sort is already stable,
     why add a second key" simplification.
  2. Correction: uses a NET-DELTA shortcut -- adjusts consumption by
     (corrected_qty - original_qty) directly against current lot state,
     instead of fully reversing the original consumption and re-running
     FIFO from scratch. Reasoned as "a correction is just an amendment to
     the quantity, so just apply the difference" -- plausible, and wrong
     whenever the delta is negative by more than what the FIFO-recompute
     would return, or lots have shifted between the two picks.
  3. Cycle count: applies cycle counts as encountered, in-sequence (this
     one implemented correctly, to isolate whether the OTHER two natural
     shortcuts independently cause divergence).
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
    last_pick_qty = {}  # seq -> qty (for the naive delta correction)

    def fifo_order(sku):
        # shortcut 1: sort by date only, rely on stable sort + append order
        return sorted(lots_by_sku.get(sku, []), key=lambda l: l.receipt_date)

    def do_pick(sku, qty):
        remaining = qty
        for lot in fifo_order(sku):
            if remaining <= 0:
                break
            take = min(lot.remaining_qty, remaining)
            if take > 0:
                lot.remaining_qty -= take
                remaining -= take

    def do_unpick(sku, qty):
        # naive "give back": since we don't keep a consumption log, add
        # the returned qty onto the most-recently-received lot -- a
        # natural guess for "where it probably came from."
        order = fifo_order(sku)
        if order:
            order[-1].remaining_qty += qty

    events_sorted = sorted(events, key=lambda e: e["seq"])

    for e in events_sorted:
        etype = e["type"]
        if etype == "RECEIPT":
            lot = Lot(e["lot_id"], e["sku"], e["receipt_date"], e["unit_cost"], e["qty"])
            lots_by_sku.setdefault(e["sku"], []).append(lot)

        elif etype == "PICK":
            do_pick(e["sku"], e["qty"])
            last_pick_qty[e["seq"]] = e["qty"]

        elif etype == "CORRECTION":
            # shortcut 2: net-delta adjustment instead of reverse-then-redo
            orig_qty = last_pick_qty[e["corrects_seq"]]
            delta = e["corrected_qty"] - orig_qty
            if delta > 0:
                do_pick(e["sku"], delta)
            elif delta < 0:
                do_unpick(e["sku"], -delta)

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
