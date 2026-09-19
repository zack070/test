# Adversarial testing notes

All entries below were run through `dev/local_harness.sh` (the real
`tests/test.sh` two-stage verifier) against both sealed datasets
(`case_a`, seed 8001, SKUs 000-059; `case_b`, seed 8002, SKUs 200-259).
Every entry scores reward **0** on both datasets; the reference solution
(`solution/engine.py`) scores **1** on both.

## The headline evidence (the actual difficulty claim)

### `unmodified_buggy_submission/` — the pipeline as shipped, untouched

**Measured:** 51/60 SKUs wrong on both `case_a` and `case_b`. Confirms
the seeded bugs are real and pervasive, not edge-case noise.

### Partial fixes — each leaves exactly one of the three bugs in place

| entry | bug left in | case_a | case_b |
|---|---|---|---|
| `partial_fix_tie_correction_only/` | deferred cycle-count | 22/60 | 25/60 |
| `partial_fix_tie_cyclecount_only/` | broken correction reversal | 20/60 | 21/60 |
| `partial_fix_correction_cyclecount_only/` | wrong FIFO tie-break | 24/60 | 22/60 |

All three bugs are independently necessary to fix. This includes SKUs
deliberately constructed so two bugs are entangled on the same SKU
(tie-break + correction, tie-break + cycle-count, correction +
cycle-count) — fixing only one of the two still leaves that SKU wrong,
which is what these numbers are catching in addition to the
single-bug SKUs.

### `naive_reimplementation/` — bypasses the buggy pipeline entirely

Written fresh from the spec's rules, never derived from
`environment/pipeline/engine.py`. Uses two natural, non-malicious
shortcuts: relies on Python's stable sort to preserve lot append order
instead of an explicit `lot_id` tie-break key, and applies corrections
as a net-delta adjustment instead of fully reversing the original pick
before redoing it. Cycle-count handling is implemented correctly here,
to isolate whether these two shortcuts alone cause failures.

**Measured:** 36/60 (case_a), 33/60 (case_b) SKUs wrong. This is the
load-bearing check against "just ignore the buggy code and reimplement
from the spec" being an easy escape from the intended difficulty — it
isn't; a careful fresh implementation falls into the same class of
mistakes independently.

## Additional adversarial angles

### `hardcoded_answers/`

Embeds the fully-computed answer for the *visible* practice case
(`environment/data/case`, seed 9001, SKU ids `SKU500`-`SKU559`) inline in
the single graded file and returns it regardless of the actual input.
The sealed datasets use disjoint SKU ranges (`SKU000`-`059` and
`SKU200`-`259`) specifically so a memorized visible-case answer cannot
coincidentally validate; this fails SKU-coverage before any value
comparison happens.

### `reward_forgery/`

Attempts to write `1` directly to `/logs/verifier/reward.txt` and to
overwrite `/tests/sealed/reference/*.json`. Both targets are
`chown root:root` / `chmod 700` (files `chmod 600`) by `tests/test.sh`
before Stage 1 (the untrusted candidate subprocess, running as the
unprivileged `runner` user) ever executes; verified directly that both
writes raise `PermissionError` under the real UID/permission split.
`test.sh` also unconditionally calls `write_reward()` again after Stage
2 grades the (still-wrong) output, so any earlier tampering is
overwritten regardless.

### `sealed_reference_read/`

Attempts to read `/tests/sealed/reference/*.json` directly and echo it
back. Same root-owned, chmod-700 sealing applies; verified directly that
this raises `PermissionError` under the `runner` UID. Falls back to an
all-zero submission on the read failure.

### `crashing/`

Raises an unconditional exception. Stage 1 records `status: "crashed"`
with captured stderr; `test_engine_present_and_ran` fails.

### `malformed_interface/`

No `run(data_dir)` function, ignores the documented interface entirely.
Produces no output file; Stage 1 records `status: "no_output_file"`.
