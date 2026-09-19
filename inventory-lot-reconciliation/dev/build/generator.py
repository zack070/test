"""
Generates warehouse event streams for the inventory reconciliation task.

Guarantees enforced by construction (and disclosed in the spec):
  - every PICK and CORRECTION's redo is satisfiable by available
    inventory at the moment it is processed under the CORRECT rules
    (no over-picks, no negative inventory)
  - each PICK is referenced by at most one CORRECTION; a CORRECTION
    never references another CORRECTION
  - every CYCLE_COUNT references a lot_id that was actually received
    earlier in the sequence for that sku

Scenario mix: single-bug scenarios (each exercises exactly one of the
three bugs) and entangled scenarios (exercise two of the three bugs on
the same sku, so fixing only one still leaves that sku wrong), plus a
"plain" scenario with no bug exposure at all.
"""
import random

SCENARIOS_SINGLE = ["tie_break", "correction", "cycle_count_defer"]
SCENARIOS_ENTANGLED = ["tie_and_correction", "tie_and_cyclecount", "correction_and_cyclecount"]


def _tie_lots(sku, rng, date=100):
    """Two same-day lots where lot_id order, creation order, and unit-cost
    order all disagree, so no accidental tie-break coincidentally works."""
    lotA = f"{sku}-L9"  # created first, HIGHEST lot_id, LOWER unit cost
    lotB = f"{sku}-L2"  # created second, LOWEST lot_id, HIGHER unit cost
    events = [
        {"type": "RECEIPT", "sku": sku, "lot_id": lotA, "receipt_date": date, "unit_cost": 7.00, "qty": 50},
        {"type": "RECEIPT", "sku": sku, "lot_id": lotB, "receipt_date": date, "unit_cost": 12.00, "qty": 50},
    ]
    return events, lotA, lotB


def make_scenario(seed, n_skus=60, id_offset=0):
    rng = random.Random(seed)
    events = []
    seq = 0

    def next_seq():
        nonlocal seq
        seq += 1
        return seq

    scenarios = (["plain"] * (n_skus // 4)
                 + SCENARIOS_SINGLE * (n_skus // 4 // len(SCENARIOS_SINGLE) + 1) * 3
                 + SCENARIOS_ENTANGLED * (n_skus // 4 // len(SCENARIOS_ENTANGLED) + 1) * 3)
    rng.shuffle(scenarios)
    scenarios = scenarios[:n_skus]
    while len(scenarios) < n_skus:
        scenarios.append("plain")

    for i, scenario in enumerate(scenarios):
        sku = f"SKU{i + id_offset:03d}"

        if scenario == "plain":
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 5.00, "qty": 80})
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 30})

        elif scenario == "tie_break":
            tie_events, lotA, lotB = _tie_lots(sku, rng)
            for e in tie_events:
                e["seq"] = next_seq()
                events.append(e)
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 50})

        elif scenario == "correction":
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 10.00, "qty": 100})
            pick_seq = next_seq()
            events.append({"type": "PICK", "seq": pick_seq, "sku": sku, "qty": 40})
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L2", "receipt_date": 101, "unit_cost": 11.00, "qty": 100})
            events.append({"type": "CORRECTION", "seq": next_seq(), "sku": sku,
                            "corrects_seq": pick_seq, "corrected_qty": 25})

        elif scenario == "cycle_count_defer":
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 9.00, "qty": 100})
            events.append({"type": "CYCLE_COUNT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "true_qty": 60})
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 60})

        elif scenario == "tie_and_correction":
            # tie between two lots, pick fully drains the correct-first
            # lot, then a correction touches the SAME tied lots
            tie_events, lotA, lotB = _tie_lots(sku, rng)
            for e in tie_events:
                e["seq"] = next_seq()
                events.append(e)
            pick_seq = next_seq()
            events.append({"type": "PICK", "seq": pick_seq, "sku": sku, "qty": 30})
            events.append({"type": "CORRECTION", "seq": next_seq(), "sku": sku,
                            "corrects_seq": pick_seq, "corrected_qty": 15})

        elif scenario == "tie_and_cyclecount":
            tie_events, lotA, lotB = _tie_lots(sku, rng)
            for e in tie_events:
                e["seq"] = next_seq()
                events.append(e)
            # cycle count on the lot that SHOULD be picked first (lotB,
            # lowest lot_id); if the tie-break is wrong, the wrong lot
            # gets consumed before the count corrects it
            events.append({"type": "CYCLE_COUNT", "seq": next_seq(), "sku": sku,
                            "lot_id": lotB, "true_qty": 40})
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 40})

        elif scenario == "correction_and_cyclecount":
            events.append({"type": "RECEIPT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "receipt_date": 100, "unit_cost": 8.00, "qty": 100})
            pick_seq = next_seq()
            events.append({"type": "PICK", "seq": pick_seq, "sku": sku, "qty": 30})
            events.append({"type": "CORRECTION", "seq": next_seq(), "sku": sku,
                            "corrects_seq": pick_seq, "corrected_qty": 20})
            events.append({"type": "CYCLE_COUNT", "seq": next_seq(), "sku": sku,
                            "lot_id": f"{sku}-L1", "true_qty": 50})
            events.append({"type": "PICK", "seq": next_seq(), "sku": sku, "qty": 50})

    rng.shuffle(events)
    return events


def make_worked_example():
    """Tiny, fully hand-checkable scenario: 2 skus, one plain, one with a
    tie-break case."""
    events = [
        {"type": "RECEIPT", "seq": 1, "sku": "WIDGET", "lot_id": "WIDGET-L1",
         "receipt_date": 1, "unit_cost": 4.00, "qty": 40},
        {"type": "PICK", "seq": 2, "sku": "WIDGET", "qty": 15},
        {"type": "RECEIPT", "seq": 3, "sku": "GADGET", "lot_id": "GADGET-L9",
         "receipt_date": 5, "unit_cost": 6.00, "qty": 30},
        {"type": "RECEIPT", "seq": 4, "sku": "GADGET", "lot_id": "GADGET-L2",
         "receipt_date": 5, "unit_cost": 9.00, "qty": 30},
        {"type": "PICK", "seq": 5, "sku": "GADGET", "qty": 30},
    ]
    return events
