# Fact sheet for instruction.md (claims-reserve-allocation)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself. Facts only; no narrative framing implied.

## ACTION NEEDED: one sentence in your current instruction.md is now stale

The model changed since your last draft (linked-claim pairs added, see
below). Your current instruction.md's budget paragraph reads:

> "The settlement budget is a hard constraint. The `settlement_offer_usd`
> for all claims marked `1` must fit within the portfolio's `budget_usd`
> from `config.json`."

This is no longer fully accurate: for a linked-pair claim, what counts
against budget is the discounted cost when its partner is also settled,
not always the raw `settlement_offer_usd`. This needs a correction or a
pointer to MODEL_SPEC.md for the exact rule -- I can't write that sentence
for you, but wanted to flag it precisely rather than leave it silently
wrong.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/policy.py`.
- Required interface: a top-level `run(data_dir) -> dict` function
  returning `{"decisions": {claim_id: 0 or 1, ...}}`, and invokable as a
  script: `python3 policy.py <data_dir> <output_path>` writing that same
  JSON structure to `<output_path>`.
- `decisions` must have exactly one entry per `claim_id` in the dataset
  it's run against (no missing or extra ids), each value `0` (defer) or
  `1` (settle now).
- Budget constraint: the sum of each settled claim's actual settlement
  cost must not exceed that portfolio's `budget_usd` (given in
  `config.json`) -- see "Linked claim pairs" below for when that cost is
  less than `settlement_offer_usd`. A submission that exceeds the cap is
  infeasible and scores 0 regardless of anything else about it.

## The problem

- `/app/MODEL_SPEC.md` is the complete, authoritative statement of the
  model: how a deferred claim's eventual cost is distributed (severity by
  claim type, a shared per-`incident_cluster_id` correlation factor,
  litigation escalation, interest), linked-claim pairs (below), and the
  exact objective being minimized
  (`E[total_cost] + risk_lambda * CVaR_alpha(total_cost)`). Nothing about
  the mechanics is hidden.
- What's NOT disclosed: the exact random draws used at grading time, and
  the numeric pass bar. The agent has to build its own estimate (e.g. its
  own Monte Carlo simulation) to judge candidate decision sets.
- There is no single correct decision set to compute or look up -- this
  is optimization under uncertainty, not a report to compute from a spec.

## Linked claim pairs (new since your last draft)

- A small number of claims are pair-linked: each has a `linked_claim_id`
  column in `claims.csv` pointing to exactly one other claim (empty for
  most claims, which are unaffected).
- If BOTH members of a pair are settled, each one's cost is
  `settlement_offer_usd * (1 - linked_settlement_discount)` (the discount
  is disclosed in `config.json`). If only one or neither is settled, each
  settled member costs its full, undiscounted `settlement_offer_usd`.
- Individually, a linked-pair claim is priced as a bad deal (its own
  `settlement_offer_usd` is above its own expected deferred cost) --
  it's only worthwhile once both members of the pair are settled
  together. This is why a per-claim, one-at-a-time evaluation (rank
  claims and greedily fill the budget, even with 1-1 swaps to polish) can
  never find a pair's value: neither half looks good in isolation.
  Finding them requires evaluating pairs of claims jointly.

## Reference material available to the agent

- `/app/MODEL_SPEC.md` -- full model + objective, as above.
- `/app/data/worked_example/` -- 23 small claims, explained in its own
  `README.md`, plus `reference_metrics.json` giving the measured
  objective of three example policies (settle-nothing, plain
  ratio-greedy, expected-value-optimal knapsack) for validating your own
  simulator against. These are NOT the task's answer.
- `/app/data/case/` -- 165 claims (same scale as the graded data), same
  structure, its own `reference_metrics.json`.

## Grading structure

- Grading runs the agent's own submitted `/app/outputs/policy.py`
  against TWO sealed held-out portfolios the agent never sees, once
  each, as a fresh subprocess per portfolio.
- Each portfolio is checked against its own sealed pass bar
  independently -- not averaged.
- For each portfolio: first, the budget constraint is checked
  mechanically (a deterministic dollar-sum comparison; infeasible = fail,
  no simulation needed). Then a large, fixed-seed Monte Carlo simulation
  (not available to the agent) computes the actual `objective` for the
  submitted decision set, and it must be at or below that portfolio's
  sealed pass bar.
- The pass bar is calibrated to sit strictly below whichever of two
  measured baselines is more permissive: an exact expected-value-optimal
  knapsack (ignores correlation AND linked pairs), and a genuinely
  sophisticated pair-blind heuristic (its own Monte Carlo simulator,
  greedy by simulated marginal objective gain per dollar recomputed each
  round, plus 1-1 swaps -- this exact class of submission passed an
  earlier, less complete version of this bundle's bars, so the bar is now
  calibrated directly against it). See cheat/README.md for the measured
  numbers.

## Constraints

- Leave `/app/MODEL_SPEC.md` and everything under `/app/data/` unchanged.
- Keep the policy deterministic enough to be reasonably reproducible, and
  reasonably fast (grading gives each portfolio a 220-second budget per
  dataset -- the reference solution's own MILP can take up to ~180s of
  that).

## Required closing sentence (platform structural requirement, easy to miss)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800** (unchanged).

## Open items only you can fill in (task.toml)

None outstanding -- author identity and relevant_experience carried over
and adapted from the prior (withholding-tax) submission, same pattern as
before.
