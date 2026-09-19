# Worked example

Two SKUs. Walk this through by hand against `INVENTORY_SPEC.md` to
confirm you understand the rules before running anything against the
larger case data.

## WIDGET

One lot: `WIDGET-L1`, receipt_date 1, unit_cost 4.00, qty 40.
A single PICK of 15 consumes 15 from that lot (only lot available):
`remaining_qty = 40 - 15 = 25`.

**Expected: `on_hand_qty = 25`, `valuation = 25 * 4.00 = 100.00`.**

## GADGET

Two lots received on the **same day** (receipt_date 5):
`GADGET-L9` (unit_cost 6.00, qty 30) and `GADGET-L2` (unit_cost 9.00,
qty 30) — `L9` was received first in the event stream, but that's not
what decides consumption order.

A single PICK of 30 must consume from whichever lot the tie-break rule
says comes first among same-date lots: **lot_id ascending**. Comparing
the strings `"GADGET-L2"` and `"GADGET-L9"`, `L2` sorts first, so the
pick consumes entirely from `L2` (`30 - 30 = 0` remaining), leaving `L9`
untouched at its full 30 units.

**Expected: `on_hand_qty = 0 + 30 = 30`,
`valuation = (0 * 9.00) + (30 * 6.00) = 180.00`.**

Notice that a wrong tie-break (for example, consuming the *cheaper* lot
first instead of the lower-`lot_id` one) would still land on
`on_hand_qty = 30` here — the same total quantity either way — but the
valuation would come out to `30 * 9.00 = 270.00` instead of the correct
`180.00`. The quantity alone won't tell you if the tie-break is wrong;
check valuation too.

Run `solution/engine.py` (or your own implementation) against
`events.json` in this directory and confirm your output matches both
figures above exactly before moving on to the larger case data.
