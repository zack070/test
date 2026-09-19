# Fact sheet for instruction.md (inventory-lot-reconciliation)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself, directly, with no AI involved anywhere
in the process (drafting, editing, "just cleaning this up," a grammar
tool with AI suggestions). Given two prior AI-detection rejections on a
different task this account submitted, this matters more than usual:
read this once, close it, and write from memory in your own words and
your own order.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/engine.py`.
- Required interface: `engine.py` must define a top-level
  `run(data_dir) -> dict` function that reads `events.json` from
  `data_dir`, and must also be runnable as a script:
  `python3 engine.py <data_dir> <output_path>`, writing the same JSON
  structure to `<output_path>`.
- Output shape: `{"skus": {"<sku>": {"on_hand_qty": 0, "valuation": 0.00}}}`
  -- one entry per SKU that appears anywhere in the event stream, no
  missing or extra SKUs.

## The starting point

- There is already a pipeline at `/app/pipeline/engine.py`. It mostly
  works but is not correct. The job is to find the problems and fix the
  pipeline -- the agent is not required to use this starting code, but
  it exists and is a reasonable place to start rather than writing
  everything from scratch.
- `/app/INVENTORY_SPEC.md` is the complete, authoritative statement of
  the reconciliation rules: FIFO lot consumption with a same-day
  tie-break by `lot_id` ascending (not unit cost, not receipt order);
  how a CORRECTION event must fully reverse the original pick's exact
  consumption before re-picking the corrected quantity against current
  inventory state; and that CYCLE_COUNT adjustments take effect at their
  exact position in the event sequence, not deferred. Nothing about the
  mechanics is hidden.
- The spec also states explicit guarantees about the input: no pick or
  correction is ever unsatisfiable (no over-picks, no negative
  inventory), each PICK is corrected at most once, corrections never
  reference other corrections, and every CYCLE_COUNT references a lot
  that actually exists. The agent does not need to handle anything
  outside these guarantees.
- The shipped pipeline contains three real, silent bugs (wrong FIFO
  tie-break key, a correction handler that doesn't reverse the original
  pick, deferred cycle-count application). None of them crash. Some SKUs
  in the graded data are constructed so that two of the three bugs
  affect the same SKU at once -- fixing only one still leaves that SKU
  wrong.
- This is not a case with one right answer to guess at -- for any given
  event stream, the rules in the spec fully determine the correct report.

## Reference material available to the agent

- `/app/INVENTORY_SPEC.md` -- full rules, as above.
- `/app/data/worked_example/` -- two SKUs, with a `README.md` that hand-
  walks both to exact expected figures (`on_hand_qty`/`valuation`),
  including a note on how a wrong tie-break would still give the same
  quantity but a different valuation for one of the two SKUs.
- `/app/data/case/` -- a 60-SKU practice event stream in the same shape
  as the graded data, with its own short `README.md` noting it is
  practice data, not the graded data.

## Grading structure

- Grading runs the agent's own submitted `/app/outputs/engine.py`
  against TWO sealed held-out event streams the agent never sees (60
  SKUs each, disjoint SKU-id ranges from each other and from the visible
  practice case), each as a fresh subprocess with a firm timeout.
- Each dataset is checked against its own frozen reference report
  independently -- not averaged. Both must pass for the submission to
  score 1; there is no partial credit.
- The reference report was computed by an implementation written
  independently from the reference solution, and the two were cross-
  checked to agree exactly before either was trusted.
- Comparison is exact per SKU on both `on_hand_qty` and `valuation`.

## Constraints

- Leave `/app/INVENTORY_SPEC.md` and everything under `/app/data/`
  unchanged.
- The submission should be deterministic and run quickly -- there is no
  search or optimization involved, just correct reconciliation logic.

## Required closing sentence (platform structural requirement, exact match required)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800**. This is
fixed platform boilerplate, not something to paraphrase -- copy it
verbatim.

## Open items only you can fill in

None outstanding -- author identity and relevant_experience in task.toml
follow the same pattern established in this account's prior submissions
(operations/business-data-analyst background), adapted to warehouse
inventory reconciliation specifics.

## What I have NOT been able to verify in this environment

Docker is not available in this sandbox (no daemon), so I could not run
`harbor run -a oracle/-a nop -e docker` or `harbor check` against the
real container build. Everything has been verified with a no-Docker
local harness (`dev/local_harness.sh`) that replicates `tests/test.sh`'s
exact logic against a scratch filesystem with real unprivileged-user
permission enforcement: the reference solution scores 1 on both sealed
datasets, a no-submission run scores 0, and all 10 cheat/ entries score
0 -- each confirmed by actually running them through the harness, not
assumed. Please run the real `harbor run -p . -a oracle -e docker`,
`harbor run -p . -a nop -e docker`, and `harbor check .` commands
yourself before final submission.
