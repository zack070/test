# Fact sheet for instruction.md (claims-reserve-allocation)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself. Facts only; no narrative framing implied.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/policy.py`.
- Required interface: a top-level `run(data_dir) -> dict` function
  returning `{"decisions": {claim_id: 0 or 1, ...}}`, and invokable as a
  script: `python3 policy.py <data_dir> <output_path>` writing that same
  JSON structure to `<output_path>`.
- `decisions` must have exactly one entry per `claim_id` in the dataset
  it's run against (no missing or extra ids), each value `0` (defer) or
  `1` (settle now).
- Budget constraint: the sum of `settlement_offer_usd` over every claim
  decided `1` must not exceed that portfolio's `budget_usd` (given in
  `config.json`). A submission that exceeds the cap is infeasible and
  scores 0 regardless of anything else about it.

## The problem

- `/app/MODEL_SPEC.md` is the complete, authoritative statement of the
  model: how a deferred claim's eventual cost is distributed (severity by
  claim type, a shared per-`incident_cluster_id` correlation factor,
  litigation escalation, interest), and the exact objective being
  minimized (`E[total_cost] + risk_lambda * CVaR_alpha(total_cost)`).
  Nothing about the mechanics is hidden.
- What's NOT disclosed: the exact random draws used at grading time, and
  the numeric pass bar. The agent has to build its own estimate (e.g. its
  own Monte Carlo simulation) to judge candidate decision sets, the same
  way a reserving team would validate a policy against a simulated
  outcome distribution before committing to it.
- There is no single correct decision set to compute or look up -- this
  is optimization under uncertainty, not a report to compute from a
  spec. A decision set that's optimal for expected cost alone is not
  necessarily optimal for the full objective, because concentrating
  deferred exposure inside a few large, correlated clusters can look fine
  on average while being risk-worse in the tail.

## Reference material available to the agent

- `/app/MODEL_SPEC.md` -- full model + objective, as above.
- `/app/data/worked_example/` -- 23 small claims, explained in its own
  `README.md`, plus `reference_metrics.json` giving the measured
  objective of two clearly-suboptimal example policies (settle-nothing,
  plain ratio-greedy) for validating your own simulator against. These
  are NOT the task's answer -- there's no answer to match.
- `/app/data/case/` -- 165 claims (same scale as the graded data), same
  structure, its own `reference_metrics.json`.

## Grading structure

- Grading runs the agent's own submitted `/app/outputs/policy.py`
  against TWO sealed held-out portfolios the agent never sees, once
  each, as a fresh subprocess per portfolio.
- Each portfolio is checked against its own sealed pass bar
  independently -- not averaged.
- For each portfolio: first, the budget constraint is checked
  mechanically (infeasible = fail, no simulation needed). Then a large,
  fixed-seed Monte Carlo simulation (not available to the agent) computes
  the actual `objective` for the submitted decision set, and it must be
  at or below that portfolio's sealed pass bar.
- The pass bar sits partway between a measured "expected-value-optimal
  but risk-blind" baseline (a plain 0/1 knapsack maximizing expected
  savings, ignoring correlation) and a measured near-optimal
  risk-aware baseline (a scenario-based optimization that accounts for
  cluster correlation and tail risk) -- see cheat/README.md for the
  measured numbers proving the risk-blind baseline genuinely fails and
  the risk-aware one genuinely passes.

## Constraints

- Leave `/app/MODEL_SPEC.md` and everything under `/app/data/` unchanged.
- Keep the policy deterministic enough to be reasonably reproducible, and
  reasonably fast (grading gives each portfolio its own timeout).

## Required closing sentence (platform structural requirement, easy to miss)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800**.

## Open items only you can fill in (task.toml)

None outstanding -- author identity and relevant_experience carried over
and adapted from the prior (withholding-tax) submission, same pattern as
before.
