# Fact sheet for instruction.md (loan-suspense-posting)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself. Facts only; no narrative framing implied.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/poster.py`.
- Required interface: invokable as a script,
  `python3 poster.py --loans <loans.json> --payments <payments.json> --window-days <N> --output <output.json>`.
- `<output.json>` must be a single JSON object with two top-level keys,
  `final_ledger` and `payment_allocations` -- exact schema is in
  `/app/SERVICING_SPEC.md` section 5. Both are graded.
- `final_ledger` must have exactly one entry per `loan_id` present in the
  input `loans.json` (no missing or extra ids).
- `payment_allocations` must have exactly one entry per (loan, day) where
  a payment posted that day -- no entry for a day with no payment, even if
  that loan is carrying a suspense balance from an earlier day.

## The problem

- `/app/SERVICING_SPEC.md` is the complete, authoritative statement of
  every rule the grader checks: the calendar convention, actual/365
  per-diem accrual, the escrow-disbursement-then-release-test order, the
  suspense/hold-until-full-installment mechanism, the exact waterfall
  order, and the once-per-cycle late fee rule. Nothing about the mechanics
  is hidden -- there is no separate undisclosed convention.
- Two fields in the payment data are explicitly declared non-authoritative
  and must never affect any computation: `effective_date` (only
  `posting_date` governs accrual, release timing, and delinquency) and
  `memo` (free text, cosmetic only, never overrides the waterfall or the
  suspense rule).
- This is a direct simulation, not an optimization or a search -- there is
  exactly one correct ledger and one correct payment-allocation trace for
  any given input, fully determined by SERVICING_SPEC.md.

## Reference material available to the agent

- `/app/SERVICING_SPEC.md` -- full rules, as above.
- `/app/data/worked_example/` -- 2 loans over a 45-day window, with a
  `README.md` that walks the arithmetic by hand for both loans (including
  the exact figures your implementation should reproduce). Use it to
  sanity-check your implementation before running it on anything larger.
- `/app/data/case/` -- an 80-loan, 75-day practice portfolio in the same
  shape as the graded data, with its own short `README.md` noting it is
  practice data, not the graded portfolio.

## Grading structure

- Grading runs the agent's own submitted `/app/outputs/poster.py` against
  ONE sealed held-out portfolio the agent never sees (80 loans, 75 days,
  same shape as the practice case but different generated figures and
  loan ids), as a fresh subprocess with a firm timeout.
- The submission's `final_ledger` is compared to a frozen reference: every
  monetary field (`principal_balance`, `accrued_interest`,
  `escrow_balance`, `suspense_balance`, each `fees_owed` bucket) to the
  cent; `next_due_date` and `days_past_due` exactly.
- Separately, `payment_allocations` is compared entry-by-entry (matched by
  loan + posting day) against the same frozen reference: the `event`
  label and every monetary breakdown field. A submission with a fully
  correct `final_ledger` still fails if it omits or miscounts allocation
  entries -- this is checked independently of the ledger, not folded into
  it.
- Both checks must pass for the submission to score 1. There is no
  partial credit.

## Constraints

- Leave `/app/SERVICING_SPEC.md` and everything under `/app/data/`
  unchanged.
- Keep the program deterministic (same input always produces the same
  output) and reasonably fast -- grading budgets several minutes for the
  single sealed run, and the reference solution completes in well under a
  second, so runtime is not the bottleneck for a correct implementation.

## Required closing sentence (platform structural requirement, easy to miss)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800**.

## Open items only you can fill in

None outstanding -- author identity and relevant_experience in task.toml
follow the same pattern established in this account's prior submissions
(operations/business-data-analyst background), adapted to loan-servicing
specifics.

## What I have NOT been able to verify in this environment

- Docker is not available in this sandbox (no daemon), so I could not run
  `harbor run -a oracle -e docker`, `harbor run -a nop -e docker`, or
  `harbor check` against the real container build. Everything has been
  verified with a no-Docker local harness (`dev/local_harness.sh`) that
  replicates `tests/test.sh`'s exact logic against a scratch filesystem
  with real unprivileged-user permission enforcement: the reference
  solution scores 1, a no-submission run scores 0, and all 11 cheat/
  entries score 0. Before final submission, please run the real
  `harbor run -p . -a oracle -e docker`, `harbor run -p . -a nop -e
  docker`, and `harbor check .` commands yourself to confirm the actual
  Docker builds succeed and the LLM quality-rubric review has no
  surprises -- I cannot do this from here.
