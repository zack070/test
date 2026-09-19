import random


def make_scenario(seed, n_skus=30):
    """Builds an event stream where every sku hits at least one of the
    three bug conditions, plus plenty of 'boring' skus that exercise the
    ordinary rules correctly (so a naive/lucky implementation can't pass
    by accident)."""
    rng = random.Random(seed)
    events = []
    seq = 0

    def next_seq():
        nonlocal seq
        seq += 1
        return seq

    for i in range(n_skus):
        sku = f"SKU{i:03d}"
        scenario = rng.choice(["tie_break", "correction", "cycle_count_defer", "plain"])

        if scenario == "tie_break":
            # Two lots, SAME receipt_date. lot_id order is deliberately
            # the REVERSE of creation/receipt order, and unit_cost order
            # differs from both -- so three plausible tie-break rules
            # (by lot_id, by creation/processing order via a naive stable
            # sort, by cost) all disagree, and only the disclosed rule
            # (lot_id ascending) is correct.
            date = 100
            lotA = f"{sku}-L9"  # created FIRST, HIGHEST lot_id, LOWER unit cost
            lotB = f"{sku}-L2"  # created SECOND, LOWEST lot_id, HIGHER unit cost
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": lotA, "receipt_date": date, "unit_cost": 7.00, "qty": 50})
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": lotB, "receipt_date": date, "unit_cost": 12.00, "qty": 50})
            # pick enough to fully drain whichever lot is consumed first,
            # but not the other -- so the final valuation depends on which
            # lot the tie-break picked.
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 50})

        elif scenario == "correction":
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 10.00, "qty": 100})
            pick_seq = next_seq()
            events.append({"type": "PICK", "seq": pick_seq, "sku": sku, "qty": 40})
            # a later receipt happens in between, so "redo against current
            # state" can differ from a naive re-pick
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L2", "receipt_date": 101, "unit_cost": 11.00, "qty": 100})
            events.append({"type": "CORRECTION", "seq": next_seq(), "sku": sku,
                            "corrects_seq": pick_seq, "corrected_qty": 25})

        elif scenario == "cycle_count_defer":
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 9.00, "qty": 100})
            cc_seq = next_seq()
            events.append({"type": "CYCLE_COUNT", "seq": cc_seq, "sku": sku,
                            "lot_id": f"{sku}-L1", "true_qty": 60})
            # a pick AFTER the cycle count, in real sequence order, that
            # should consume from the corrected (60) quantity
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 60})

        else:  # plain -- ordinary, unambiguous processing
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 5.00, "qty": 80})
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 30})

    rng.shuffle(events)  # input order need not match seq order
    return events
