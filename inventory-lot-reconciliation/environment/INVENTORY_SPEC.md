# Inventory Reconciliation Rules

This document is the complete, authoritative specification of the
reconciliation rules. Every rule the grader checks is stated here.

## 1. Entities

Inventory is tracked per SKU as a set of **lots**. Each lot was created
by a receipt and has: `lot_id`, `sku`, `receipt_date` (an integer day
number), `unit_cost`, and a `remaining_qty` that decreases as the lot is
consumed.

## 2. Events

The day's event stream is a list of events, each carrying a unique `seq`
integer that defines the total order events must be processed in (sort
by `seq` ascending; the order events appear in the input file is not
meaningful).

- **RECEIPT** `{seq, sku, lot_id, receipt_date, unit_cost, qty}` — creates
  a new lot with `remaining_qty = qty`.
- **PICK** `{seq, sku, qty}` — consumes `qty` units from the sku's lots,
  in FIFO order: earliest `receipt_date` first. When two or more lots
  for the same sku share a `receipt_date`, the tie is broken by `lot_id`
  ascending (ordinary string comparison) — **not** by unit cost, and
  not by which lot was received first in real time. Consumption moves to
  the next lot in FIFO order once the current one is exhausted
  (`remaining_qty` reaches 0).
- **CORRECTION** `{seq, sku, corrects_seq, corrected_qty}` — amends an
  earlier PICK. `corrects_seq` always refers to an earlier PICK event
  for the same sku. Processing a correction means: first, fully reverse
  the original pick's exact consumption (restore `remaining_qty` on
  every lot that pick drew from, by exactly the amount it drew from
  each); then perform a brand-new FIFO pick of `corrected_qty`, using
  the lot state as it stands at the moment the correction is processed
  (which can differ from the state when the original pick ran, since
  other events may have occurred on that sku in between).
- **CYCLE_COUNT** `{seq, sku, lot_id, true_qty}` — a physical count sets
  that lot's `remaining_qty` directly to `true_qty`. This takes effect
  at its exact position in the `seq` order, like any other event — not
  before, and not deferred to the end of the run. Any event with a
  later `seq` that touches this sku must see the corrected quantity, and
  the correction must reflect everything that happened on this sku
  before it.

## 3. Guarantees about the input (do not add handling for anything else)

These are guaranteed true of every event stream you will be graded on.
You do not need to handle, and should not need to guess about, anything
outside these guarantees:

- Every PICK and every CORRECTION's `corrected_qty` is satisfiable by
  the sku's actual available inventory at the moment it is processed,
  under the rules above. Inventory never goes negative and a pick is
  never short.
- Each PICK is the target of at most one CORRECTION. A CORRECTION's
  `corrects_seq` always points to a PICK, never to another CORRECTION.
- Every CYCLE_COUNT's `lot_id` refers to a lot that was actually created
  by an earlier RECEIPT for that sku.
- `unit_cost` and `qty`/`true_qty` values are given as plain numbers
  (no currency symbols, no strings).

## 4. Output

For each sku that appears anywhere in the event stream, report:

- `on_hand_qty` — the sum of `remaining_qty` across all of that sku's
  lots at the end of processing.
- `valuation` — the sum, across all of that sku's lots, of
  `remaining_qty * unit_cost`, computed as one exact sum over all lots
  and rounded to the nearest cent **once**, at the end. Do not round at
  any intermediate step (per-lot or per-event) — only the final total
  per sku is rounded.

Your submission is one Python 3 file, `engine.py`, that must define a
top-level function `run(data_dir) -> dict` reading `events.json` from
`data_dir` and returning:

```json
{
  "skus": {
    "<sku>": {"on_hand_qty": 0, "valuation": 0.00}
  }
}
```

It must also be runnable as a script:

```
python3 engine.py <data_dir> <output_path>
```

writing that same JSON structure to `<output_path>`.
