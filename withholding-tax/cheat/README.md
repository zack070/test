# Adversarial testing notes

Harbor never executes anything under this directory. Every attempt here
was actually run against the real verifier via `dev/local_harness.sh`
(which runs the real `tests/test.sh`, `collect_agent_output.py`, and
`test_withholding_grading.py` against real `/app`, `/tests`, `/work`,
`/logs` paths and a Python matching `tests/Dockerfile`'s exact pinned
installs). Results below are measured, not hypothetical.

The agent's deliverable is executable code (`/app/outputs/engine.py`),
which runs once per sealed held-out dataset at grading time -- so the
full untrusted-execution attack surface applies, though in a simpler
shape than the companion field-service-dispatch/cash-sweep bundles: this is a
one-shot batch call, not a live per-event decide() loop, so there is no
incrementally-revealed state to leak and no separate trusted process
with live secrets to introspect. What has to stay hidden is only the
ground truth the output gets checked against.

## 1. Unmodified buggy submission (`unmodified_buggy_submission/`)

The exact pipeline as given, resubmitted with no fix at all -- the
"didn't do the work" baseline for this task.

**Measured result: reward 0.** 13 of 64 payments wrong on held_out_1, 17
of 84 wrong on held_out_2 (the same three bugs documented in the
pipeline's own module docstring, exercised by real data rather than
reasoned about).

## 2. Reward forgery (`reward_forgery/`)

`run()` tries to overwrite `/logs/verifier/reward.txt` with `1` directly
before returning an empty report.

**Measured result: reward 0.** The write is attempted under the
`runner` UID; `/logs/verifier` is root-owned and sealed before Stage 1
runs (same as every other bundle in this account), and Stage 2's own
independent grading still runs afterward and overwrites whatever Stage 1
did to the reward file regardless.

## 3. Sealed ground truth read (`sealed_ground_truth_read/`)

`run()` tries to read `/tests/sealed/reference/held_out_1_ground_truth.json`
and `held_out_2_ground_truth.json` directly by name (not just via a
directory-listing glob, which would fail before even trying, since the
directory itself is sealed to mode 700), plus attempts a directory
listing.

**Measured result: reward 0**, and every attempt genuinely fails:

    {"path": ".../held_out_1_ground_truth.json", "status": "blocked", "error": "[Errno 13] Permission denied..."}
    {"path": ".../held_out_2_ground_truth.json", "status": "blocked", "error": "[Errno 13] Permission denied..."}
    {"path": ".../reference (listdir)", "status": "blocked", "error": "[Errno 13] Permission denied..."}

`test.sh` chown+chmod's `/tests/sealed/reference` to root-only before
Stage 1 (running as `runner`) ever executes -- the raw sealed INPUT
scenario files are deliberately left unsealed, since the candidate's own
code has to read them to compute anything; only the ground truth is
sealed.

## 4. Crashing pipeline (`crashing/`)

`run()` unconditionally raises `RuntimeError`.

**Measured result: reward 0.** `collect_agent_output.py` catches the
non-zero exit / exception, records `status: "crashed"`, and Stage 2
fails the "policy present and ran" check cleanly.

## 5. Malformed submission -- wrong interface (`malformed_no_cli/`)

Defines `solve(data_dir)` instead of `run(data_dir)`, and has no
`if __name__ == "__main__":` block at all, so invoking it as a script
produces no output file.

**Measured result: reward 0.** Stage 1 detects the missing output file
and records a crashed/missing status before Stage 2 has anything to
grade.

## 6. Infinite loop (`infinite_loop/`)

`run()` loops forever.

**Measured result: reward 0**, confirmed to actually time out rather
than hang the verifier: the harness returns in ~2 minutes (matching the
per-dataset subprocess timeout times two datasets, well inside `test.sh`'s
own outer 150-second Stage 1 budget) rather than hanging indefinitely.

## 7. Always statutory (`always_statutory/`)

Ignores treaty eligibility, ownership, and holding period entirely --
applies the statutory rate to every payment.

**Measured result: reward 0.** Fails on every payment that should have
qualified for a treaty rate on either held-out dataset.

## 8. Always the best available treaty rate (`always_best_treaty/`)

The opposite constant strategy -- applies the cheapest treaty rate in
the table to every payment regardless of jurisdiction, ownership, or
holding period.

**Measured result: reward 0.** Fails on nearly every line.

## 9. Memorized visible answers (`hardcoded_answers/`)

Ships a lookup table built from `environment/data/case/expected_answer.json`
(the visible practice dataset's own known-correct answers) keyed by
`payment_id`, and falls back to a naive statutory-only guess for any
`payment_id` not in the table.

**Measured result: reward 0.** Held-out `payment_id`s happen to reuse
the same `PAY####` numbering scheme as the visible case dataset (both
start fresh at `PAY0001`), so this cheat's lookup table technically
"hits" on every held-out payment_id -- but the underlying facts
(amounts, dates, ownership, currencies) differ, so the memorized dollar
figures are simply wrong for held-out data. This confirms held-out
grading tests whether the pipeline's LOGIC was actually fixed, not
whether the agent can pattern-match on identifiers.

## Why this bundle's cheat surface differs from field-service-dispatch/cash-sweep

There is no incrementally-revealed information to leak (no decide()
loop, no live simulator with hidden future state) and correspondingly no
process-isolation-against-introspection concern -- the candidate's code
receives a data directory once and returns an answer once. The attack
surface that remains is standard for any "submit code that gets
executed against sealed test data" task: don't let it read the answer
key, don't let it forge the reward file, don't let a crash or hang
silently pass, and confirm that a shortcut specific to the VISIBLE data
(hardcoding, memorizing, partial fixes that only happen to work on the
cases you've seen) genuinely fails to generalize to the sealed data,
which is exactly what exploit #9 checks directly rather than assumes.
