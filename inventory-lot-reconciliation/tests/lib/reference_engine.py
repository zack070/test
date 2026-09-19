"""Independently-written reference implementation (trusted, Stage 2 only).
Deliberately structured differently from solution/engine.py -- plain
dicts instead of a Lot class, a single flat processing loop instead of
per-event-type dispatch functions, and reversal computed inline rather
than via a shared consume_fifo() helper -- to catch a shared-bug risk
between the reference solution and the grader."""


def score(events):
    # sku -> list of lot dicts {"lot_id","receipt_date","unit_cost","qty"}
    lots = {}
    pick_history = {}  # seq -> (sku, [(lot_id, amount), ...])

    for ev in sorted(events, key=lambda e: e["seq"]):
        kind = ev["type"]

        if kind == "RECEIPT":
            lots.setdefault(ev["sku"], []).append({
                "lot_id": ev["lot_id"], "receipt_date": ev["receipt_date"],
                "unit_cost": ev["unit_cost"], "qty": ev["qty"],
            })

        elif kind == "PICK":
            sku = ev["sku"]
            ordered = sorted(lots.get(sku, []), key=lambda l: (l["receipt_date"], l["lot_id"]))
            need = ev["qty"]
            taken = []
            for lot in ordered:
                if need <= 0:
                    break
                give = lot["qty"] if lot["qty"] < need else need
                if give > 0:
                    lot["qty"] -= give
                    need -= give
                    taken.append((lot["lot_id"], give))
            pick_history[ev["seq"]] = (sku, taken)

        elif kind == "CORRECTION":
            sku = ev["sku"]
            _, taken = pick_history[ev["corrects_seq"]]
            index = {l["lot_id"]: l for l in lots.get(sku, [])}
            for lot_id, amount in taken:
                index[lot_id]["qty"] += amount
            ordered = sorted(lots.get(sku, []), key=lambda l: (l["receipt_date"], l["lot_id"]))
            need = ev["corrected_qty"]
            redo = []
            for lot in ordered:
                if need <= 0:
                    break
                give = lot["qty"] if lot["qty"] < need else need
                if give > 0:
                    lot["qty"] -= give
                    need -= give
                    redo.append((lot["lot_id"], give))
            pick_history[ev["seq"]] = (sku, redo)

        elif kind == "CYCLE_COUNT":
            for lot in lots.get(ev["sku"], []):
                if lot["lot_id"] == ev["lot_id"]:
                    lot["qty"] = ev["true_qty"]
                    break

        else:
            raise ValueError(f"unknown event type: {kind}")

    result = {}
    for sku, sku_lots in lots.items():
        qty_total = 0
        val_total = 0.0
        for lot in sku_lots:
            qty_total += lot["qty"]
            val_total += lot["qty"] * lot["unit_cost"]
        result[sku] = {"on_hand_qty": qty_total, "valuation": round(val_total, 2)}
    return result
