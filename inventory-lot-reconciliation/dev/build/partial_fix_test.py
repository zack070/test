import sys
import os
import importlib.util

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
from generator import make_scenario


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


solution_engine = load_module(os.path.join(ROOT, "solution", "engine.py"), "solution_engine")


def process_partial(events, fix_tie, fix_correction, fix_cyclecount):
    """Reimplements the pipeline with exactly the given subset of the
    three fixes applied, to see if a partial fix still gets caught."""
    lots_by_sku = {}
    pick_log = {}
    deferred = []

    class Lot:
        def __init__(self, lot_id, sku, receipt_date, unit_cost, qty):
            self.lot_id, self.sku = lot_id, sku
            self.receipt_date, self.unit_cost, self.remaining_qty = receipt_date, unit_cost, qty

    def fifo(sku):
        lots = lots_by_sku.get(sku, [])
        key = (lambda l: (l.receipt_date, l.lot_id)) if fix_tie else (lambda l: (l.receipt_date, l.unit_cost))
        return sorted(lots, key=key)

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
            if fix_correction:
                _, orig = pick_log[e["corrects_seq"]]
                for lot_id, amt in orig:
                    find(sku, lot_id).remaining_qty += amt
            pick_log[e["seq"]] = (sku, consume(sku, e["corrected_qty"]))
        elif t == "CYCLE_COUNT":
            if fix_cyclecount:
                lot = find(e["sku"], e["lot_id"])
                if lot:
                    lot.remaining_qty = e["true_qty"]
            else:
                deferred.append(e)

    if not fix_cyclecount:
        for e in deferred:
            lot = find(e["sku"], e["lot_id"])
            if lot:
                lot.remaining_qty = e["true_qty"]

    report = {}
    for sku, lots in lots_by_sku.items():
        qty = sum(l.remaining_qty for l in lots)
        val = sum(l.remaining_qty * l.unit_cost for l in lots)
        report[sku] = (qty, round(val, 2))
    return report


def normalize(report_dict):
    return {sku: (v["on_hand_qty"], v["valuation"]) for sku, v in report_dict["skus"].items()}


def main():
    for name, seed, offset in [("case_a", 8001, 0), ("case_b", 8002, 200)]:
        events = make_scenario(seed, n_skus=60, id_offset=offset)
        state = solution_engine.process_events(events)
        correct = normalize(solution_engine.build_report(state))

        for label, flags in [
            ("fix tie+correction only (cyclecount bug remains)", (True, True, False)),
            ("fix tie+cyclecount only (correction bug remains)", (True, False, True)),
            ("fix correction+cyclecount only (tie bug remains)", (False, True, True)),
        ]:
            result = process_partial(events, *flags)
            mism = sum(1 for sku in correct if correct[sku] != result.get(sku))
            status = "CAUGHT" if mism > 0 else "!!! SLIPPED THROUGH !!!"
            print(f"[{name}] {label}: {mism}/60 skus mismatched -> {status}")


if __name__ == "__main__":
    main()
