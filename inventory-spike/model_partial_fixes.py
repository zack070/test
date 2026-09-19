"""Three variants of model_buggy.py, each with exactly two of the three
bugs fixed (one left in), to confirm the sealed grading would actually
catch a partial fix rather than only an all-or-nothing one."""


class Lot:
    def __init__(self, lot_id, sku, receipt_date, unit_cost, qty):
        self.lot_id = lot_id
        self.sku = sku
        self.receipt_date = receipt_date
        self.unit_cost = unit_cost
        self.remaining_qty = qty


def _run(events, tie_break_fixed, correction_fixed, cycle_count_fixed):
    lots_by_sku = {}
    pick_consumption_log = {}
    deferred_cycle_counts = []

    def fifo_order(sku):
        if tie_break_fixed:
            key = lambda l: (l.receipt_date, l.lot_id)
        else:
            key = lambda l: (l.receipt_date, l.unit_cost)
        return sorted(lots_by_sku.get(sku, []), key=key)

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
            if correction_fixed:
                _, orig_consumed = pick_consumption_log[e["corrects_seq"]]
                lots_index = {l.lot_id: l for l in lots_by_sku.get(orig_sku, [])}
                for lot_id, amount in orig_consumed:
                    lots_index[lot_id].remaining_qty += amount
            do_pick(orig_sku, e["corrected_qty"])

        elif etype == "CYCLE_COUNT":
            if cycle_count_fixed:
                for lot in lots_by_sku.get(e["sku"], []):
                    if lot.lot_id == e["lot_id"]:
                        lot.remaining_qty = e["true_qty"]
                        break
            else:
                deferred_cycle_counts.append(e)

    if not cycle_count_fixed:
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


def fix_1_2_only(events):  # tie_break + correction fixed, cycle_count bug remains
    return _run(events, tie_break_fixed=True, correction_fixed=True, cycle_count_fixed=False)


def fix_1_3_only(events):  # tie_break + cycle_count fixed, correction bug remains
    return _run(events, tie_break_fixed=True, correction_fixed=False, cycle_count_fixed=True)


def fix_2_3_only(events):  # correction + cycle_count fixed, tie_break bug remains
    return _run(events, tie_break_fixed=False, correction_fixed=True, cycle_count_fixed=True)
