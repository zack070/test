# Adversarial testing notes

All entries below were run through `dev/local_harness.sh` (the real
`tests/test.sh` two-stage verifier, against the actual sealed 80-loan,
75-day portfolio in `tests/sealed/inputs/case`) or a targeted standalone
check where noted. All measured results are from real runs, not
hypothesized. Every entry scores reward **0**; the reference solution
(`solution/poster.py`) scores **1** on the same harness.

## The two structural adversarial baselines (the actual difficulty claim)

### `naive_no_suspense/` — the most natural reading of the spec

Applies every payment immediately through the waterfall (fees, escrow
shortage, interest, principal), whatever its size, and advances
`next_due_date` once a running per-cycle credit counter reaches the
installment amount. This is what a competent engineer would write if they
read the waterfall rules carefully but did not model "hold until a full
installment is covered" — the single most plausible non-expert
implementation of this spec.

**Measured on the sealed 80-loan portfolio:**
- 53/80 loans (66%) end with at least one wrong ledger field.
- Aggregate absolute error: principal $1,526.71, accrued interest
  $5,012.09, escrow balance $828.98, suspense balance $7,635.63.
- Reward: **0** (fails `test_dataset_ledger_matches_reference`).

### `effective_date_confusion/` — otherwise-correct, wrong date field

Implements the suspense/release/waterfall mechanism exactly, but buckets
each payment by `effective_date` instead of `posting_date` — the specific,
plausible trap the spec calls out by name and forbids explicitly.

**Measured on the sealed 80-loan portfolio:**
- 39/80 loans (49%) end with at least one wrong ledger field, even with
  every other rule implemented correctly.
- Aggregate absolute error: principal $322.66, accrued interest $309.83.
- Reward: **0**.

Both were built as real, non-strawman implementations (not deliberately
broken) and tested against the real verifier before the bar/spec was
finalized. Both fail overwhelmingly, which is the basis for
`difficulty_explanation` in `task.toml`.

## Additional adversarial angles

### `memo_driven_allocation/`

Otherwise-correct waterfall, but a payment whose memo mentions
"principal" is applied directly to `principal_balance`, bypassing the
waterfall and suspense test — the mistake an engineer makes if they treat
the (explicitly declared cosmetic) memo field as an instruction.

**Measured:** 50/80 loans (62.5%) end with a wrong ledger field. Reward:
**0**.

### `incomplete_breakdown/`

Computes the final ledger with the exact correct algorithm (byte-for-byte
the same logic as `solution/poster.py`) but only emits
`payment_allocations` records for `"release"` events, silently omitting
`"held_in_suspense"` ones — the shortcut an engineer takes if they assume
only actual money movements need to be reported.

**Measured:** 0/80 ledger mismatches (the ledger check alone would pass
this submission), but 86 `held_in_suspense` records are missing from
`payment_allocations` out of the sealed dataset's total. Reward: **0**,
failing `test_dataset_payment_allocations_match_reference` specifically.
This confirms the per-payment breakdown check is load-bearing: a
submission with a fully correct ledger still fails if it does not report
every required event.

### `hardcoded_answers/`

Embeds the fully-computed answer for the *visible* practice case
(`environment/data/case`, seed 4242, loan ids `L000`-`L079`) inline in the
single graded file (memorization must be inline — only one file is ever
graded) and returns it regardless of the actual input. The sealed grading
portfolio (seed 90909) uses a disjoint id range (`L100`-`L179`) precisely
so a memorized visible-case answer cannot coincidentally match on ids;
this fails loan-coverage before any monetary comparison even happens.
Reward: **0**.

### `reward_forgery/`

Attempts to write `1` directly to `/logs/verifier/reward.txt` and to
`/tests/sealed/reference/case_reference.json`. Both targets are
`chown root:root` / `chmod 700` (and files `chmod 600`) by `tests/test.sh`
*before* Stage 1 (the untrusted candidate subprocess, running as the
unprivileged `runner` user) ever executes. Verified directly: both writes
raise `PermissionError` under the real UID/permission split. Even setting
that aside, `test.sh` unconditionally calls `write_reward()` again after
Stage 2 grades the (still-wrong) ledger, so any earlier tampering is
overwritten regardless. Reward: **0**.

### `sealed_reference_read/`

Attempts to read `/tests/sealed/reference/case_reference.json` directly
and echo it back as the answer. Same root-owned, `chmod 700` sealing
applies; verified directly that this raises `PermissionError` under the
`runner` UID. Falls back to an empty submission on the read failure.
Reward: **0**.

### `crashing/`

Raises an unconditional exception. Stage 1 records `status: "crashed"`
with the captured stderr; `test_poster_present_and_ran` fails. Reward:
**0**.

### `malformed_interface/`

Ignores the documented `--loans/--payments/--window-days/--output` CLI
entirely. Produces no output file; Stage 1 records
`status: "no_output_file"`. Reward: **0**.

### `infinite_loop/`

`while True: pass`. Verified against the real per-dataset subprocess
timeout mechanism (`subprocess.run(..., timeout=...)` in
`collect_agent_output.py`) with a temporarily shortened timeout (5s
instead of the real 240s) for speed — confirmed `status: "timeout"` after
the process is killed. The real 240s timeout uses the identical, unmodified
code path. Reward: **0**.

### `do_nothing/`

Produces a syntactically valid but empty output
(`{"final_ledger": {}, "payment_allocations": []}`). Fails the loan-
coverage assertion immediately (`set(ledger.keys()) == loan_ids`). Reward:
**0**.
