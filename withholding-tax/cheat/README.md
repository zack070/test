# Adversarial testing notes

Harbor never executes anything under this directory. Every attempt here
was actually run against the real verifier via `dev/local_harness.sh`
(which runs the real `tests/test.sh` and `test_withholding_grading.py`
against the real `environment/data/case` dataset and a Python matching
`tests/Dockerfile`'s exact pinned installs). Results below are measured,
not hypothetical.

Unlike the companion field-service-dispatch and cash-sweep bundles, the
agent's deliverable here is a data file (`/app/outputs/report.json`),
not executable code -- Stage 1/candidate-code-execution concerns
(process isolation, frame introspection, sealed-file reads) simply don't
apply, because nothing the candidate writes ever runs at verify time.
The attack surface that remains is: can a plausible-but-wrong report, or
a malformed one, pass anyway?

## 1. Empty object (`empty_object/`)

`report.json` is `{}`.

**Measured result: reward 0.** `test_artifact_present_and_well_formed`
fails on the missing `payments` key before any comparison happens.

## 2. Total only, no line items (`total_only_no_lines/`)

`report.json` supplies a plausible-looking `total_liability_usd` (the
actual correct value, copied) but no `payments` list at all.

**Measured result: reward 0.** Same schema check as #1 -- a bare total
is not a valid submission regardless of its value.

## 3. All-zero report (`all_zero/`)

Every payment present, correct schema, every dollar figure zero.

**Measured result: reward 0.** Fails `test_every_payment_final_
withholding_correct` on all 109 lines.

## 4. Naive: relevant parent resolved once per payee (`naive_once_per_payee_parent/`)

Resolves each payee's ownership look-through once (as of January 1)
instead of separately for each payment's own date -- the exact shortcut
validated in dev/spike2_ownership.py and dev/probes.py to diverge from
the correct answer even when the look-through rule itself is understood
correctly.

**Measured result: reward 0.** Total off by +5.6% (dev/probes.py); fails
line-level checks on every payment whose payee's ownership stake crossed
the 50% boundary during the year.

## 5. Naive: no retroactive threshold re-rating (`naive_no_retroactive_threshold/`)

Computes each payment's base rate correctly (including the per-date
look-through) but never checks the cumulative annual threshold, so nothing
is ever retroactively re-rated.

**Measured result: reward 0.** Total off by -51.2%; fails line-level
checks on every payment belonging to a payee whose annual total crossed
the threshold, and every `true_up_usd` is wrong (always 0 instead of the
correct make-up amount).

## 6. Naive: always statutory (`naive_always_statutory/`)

Ignores treaty eligibility entirely -- a "when in doubt, be conservative"
constant strategy.

**Measured result: reward 0.** Total off by +14.4%; fails on every
payment that should have qualified for a treaty rate.

## 7. Naive: always the best available treaty rate (`naive_always_best_treaty/`)

The opposite constant strategy -- applies the cheapest treaty rate in
the table to every payment regardless of jurisdiction, ownership, or
holding period.

**Measured result: reward 0.** Total off by -80.9%; fails on nearly
every line.

## 8. Missing one payment (`missing_one_payment/`)

Every other line correct (copied from the real answer), but one
`payment_id` dropped from the submission entirely, with the grand total
left unchanged from the correct value.

**Measured result: reward 0.** `test_every_payment_present` fails on the
missing `payment_id` before dollar amounts are even compared -- a
correct-looking total cannot paper over an incomplete submission.

## 9. Correct total, wrong per-line distribution (`correct_total_wrong_lines/`)

The grand total is exactly correct (copied from the real answer), but
every individual payment is reported as an equal share of that total,
ignoring each payment's actual facts entirely.

**Measured result: reward 0.** `test_grand_total_correct` passes, but
`test_every_payment_final_withholding_correct` fails on effectively
every line -- confirms the verifier grades line items, not just the
aggregate, so a correct total computed the wrong way (or reverse-
engineered from a leaked total) cannot pass.

## Why this bundle's cheat surface is different in kind

There is no code-execution attack surface to test here (no process to
isolate, no live simulator state to leak, no filesystem to seal) because
grading never runs anything the candidate wrote -- it only ever reads
the JSON file left behind and diffs it against a sealed ground truth
computed ahead of time from `environment/data/case` (the same dataset
the agent works from; nothing about the graded instance is hidden from
the agent, since a computed-file deliverable requires seeing the data it
computes over). The bar this bundle has to clear instead is: can a
plausible-but-wrong computation, or a malformed/incomplete submission,
survive tolerance-based comparison? Sections 1-3 and 8 test the schema
and completeness checks; sections 4-7 and 9 test that per-line accuracy
(not just a matching or reverse-engineered total) is actually required,
using the same naive computations independently validated in
dev/probes.py against the real dataset.
