The hard part here is that the existing code fails quietly. /app/pipeline/engine.py has three logic errors, and none of them crash anything. The FIFO tie-break is wrong, corrections don't restore the original pick before the replacement pick happens, and cycle-count changes get applied late. Some of the grading data deliberately makes two of those mistakes land on the same SKU, so fixing just one can still leave you with a wrong final report. There's no partial credit either. The check uses two unseen 60-SKU streams, each compared against its own frozen reference report, with exact matches on both on_hand_qty and valuation. Both have to be right.

Work in /app. Start from the existing implementation if it helps, or replace it outright. What matters is how the submitted file behaves, not whether any of the old code survives. The finished file goes at /app/outputs/engine.py.

The reconciliation rules are all in /app/INVENTORY_SPEC.md. Read that instead of trying to work out the intended behavior from the existing code.

Most of the trouble is lot state. Picks consume inventory FIFO, and when two lots share a receipt day, the lower lot_id goes first. Unit cost and receipt order don't break ties. A correction is more than another pick. First the exact lot consumption of the original pick has to be put back, and then the corrected quantity is picked against the inventory as it stands at that point in the event stream. Cycle counts are the other ordering trap. Apply the adjustment the moment you hit the event, not later in a batch.

The input is well behaved, so don't spend time on edge cases. Picks and corrections are always satisfiable, a pick gets corrected at most once, corrections never point at other corrections, and cycle counts always refer to real lots. Nothing outside those guarantees needs handling.

For checking, /app/data/worked_example/ is a small case, and its README has hand-worked quantities and valuations to compare against. One of the examples is good at catching the FIFO tie-break bug, because picking the wrong lot can leave the quantity unchanged while the valuation shifts. /app/data/case/ is a 60-SKU practice stream with the same general structure. It's there to exercise your implementation, not to grade it, so don't base assumptions on its SKU names or particular event values. The graded streams use different SKU ranges from each other and from the practice data.

The file has to work two ways. It needs a top-level run(data_dir) -> dict function that reads events.json from the directory it's given, and it needs to work from the command line:

python3 engine.py <data_dir> <output_path>

The command-line form writes the same result run() returns. That result has one entry for every SKU found anywhere in the event stream:

{"skus": {"<sku>": {"on_hand_qty": 0, "valuation": 0.00}}}

This is a deterministic reconciliation problem, not an optimization one. Once the event rules are right, the same input gives the same report, and the program should finish quickly.

Leave /app/INVENTORY_SPEC.md and everything under /app/data/ as supplied. Before you finish, run both the worked example and the practice data, and test the command-line entry point as well as run(). Check that every SKU is represented and that what gets written is what the reconciliation logic actually produced.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
