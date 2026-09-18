# Fact sheet for instruction.md (withholding-tax)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself. Facts only; no narrative framing implied.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/report.json`.
- No specific programming language or approach is required -- the agent
  can write a script, use a spreadsheet tool, or compute by hand, as
  long as the final JSON file is correct. In practice, correctly
  handling 109 payments makes writing a program the only realistic path,
  but that's not a stated requirement, just a fact worth knowing.
- Required JSON schema:
  ```json
  {
    "payments": [
      {
        "payment_id": "...",
        "initial_rate": 0.0,
        "final_rate": 0.0,
        "initial_withholding_usd": 0.0,
        "final_withholding_usd": 0.0,
        "true_up_usd": 0.0
      }
    ],
    "total_liability_usd": 0.0
  }
  ```
  One entry per payment_id in `environment/data/case/payments.csv`, no
  extras, no omissions. `total_liability_usd` = sum of every payment's
  `final_withholding_usd`.

## Reference material available to the agent

- `/app/RULEBOOK.md` -- the complete, authoritative rule set (data file
  formats, the ownership look-through algorithm, holding-period test,
  cumulative threshold retroactive re-rating, currency conversion,
  rounding). This is the primary reference; nothing needed to compute
  the correct answer is left out of it.
- `/app/data/case/` -- the dataset to reconcile: `entities.csv`,
  `ownership.csv`, `payments.csv`, `fx_rates.csv`, `config.json`
  (statutory_rate, treaty_partners, threshold_usd,
  holding_period_days). This is the SAME dataset that gets graded --
  there is no separate hidden dataset, since the agent has to see what
  it's computing over.
- `/app/data/worked_example/` -- seven small, fully-explained payments
  (six illustrating one rule behavior each, plus a second payment for
  the threshold-breach case, which needs two) with the correct answer
  already computed and shown (`expected_answer.json`, explained
  line-by-line in `README.md`). Meant for the agent to validate its own
  understanding before tackling the real dataset. Not graded.

## Rules (already precisely defined in RULEBOOK.md -- the instruction
should point to it, not restate every boundary condition itself, per
the fact that the rulebook already states them exactly)

- Statutory default rate; treaty rate conditional on: (a) the payee's
  "relevant parent" jurisdiction (see ownership look-through) being a
  treaty partner, AND (b) a holding-period test.
- Ownership look-through: resolved per payment, using the payee's own
  date-specific ownership record. Continues past any >50% owner, stops
  at the first owner holding <=50% (or at the payee itself if it has no
  owner on record for that date).
- Holding period test: `(payment_date - acquisition_date).days >=
  holding_period_days` (365 in this dataset), inclusive.
- Cumulative annual per-payee threshold: sum of USD-converted payments
  per (payee, calendar year); if strictly greater than
  `threshold_usd`, every payment in that group is retroactively
  re-rated to the statutory rate, including ones already computed at a
  lower rate, with the difference reported as `true_up_usd`.
- Currency conversion: the rate for the calendar month containing each
  payment's own date; used both for the threshold sum and the reported
  USD figures.
- Rounding: only the four reported figures (three per-payment, one
  total), 2 decimal places, standard round-half-up, as the very last
  step -- never round an intermediate value and use it further.

## Grading structure

- The submitted report is compared against a ground truth computed from
  the same dataset the agent worked from, independently cross-checked
  with a second, separately-coded implementation (both agree exactly,
  to the cent, on all 109 payments).
- Comparison is per-payment -- `initial_rate`, `final_rate`,
  `initial_withholding_usd`, `final_withholding_usd`, and `true_up_usd`
  are all checked individually -- not just the aggregate total; a
  correct grand total computed the wrong way (or reverse-engineered)
  will not pass; see cheat/README.md's "correct total, wrong
  distribution" case.
- Small absolute tolerance ($0.02 per line on dollar figures, 1e-6 on
  rates, $0.05 on the total) to accommodate legitimate floating-point
  implementation differences, not to forgive a wrong rule application --
  every tested naive/wrong strategy misses by orders of magnitude more
  than this tolerance.

## Constraints

- Leave `/app/RULEBOOK.md` and the files under `/app/data/` unchanged.
- Keep the computation deterministic: the same input data should
  produce the same output every time.
- Before submitting, spot-check the output against
  `/app/data/worked_example/expected_answer.json`'s reasoning pattern
  (not the numbers themselves, which belong to a different, smaller
  dataset) and make sure the JSON is well-formed and covers every
  payment_id in `payments.csv`.

## Required closing sentence (platform structural requirement, easy to miss)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800**. This
is a structural/pipeline check, not stylistic -- get the exact wording
and number right. (The companion field-service-dispatch and cash-sweep
bundles both end with this same sentence, verbatim except for N, which
matched their own task.toml value each time.)

## Open items only you can fill in (task.toml)

Already filled in this time (author identity and relevant_experience
reused/adapted from the companion field-service-dispatch bundle, same
as was done for cash-sweep) -- nothing outstanding here unless you want
to change either.
