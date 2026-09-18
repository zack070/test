Work in `/app`. The file to leave behind is `/app/outputs/policy.py`.

This is a portfolio decision problem. There isn't a single answer file to reproduce. The model is already defined in `/app/MODEL_SPEC.md`, including how deferred claims can develop and how the final objective is calculated. Read that before building the policy.

The module needs a top-level:

`def run(data_dir) -> dict`

It must also be runnable as:

`python3 policy.py <data_dir> <output_path>`

The returned result, and the JSON written by the script, should look like this:

```json
{
  "decisions": {
    "claim_id": 0
  }
}

```

There needs to be exactly one decision for every claim in the input. Use `0` for defer and `1` for settle now. Don't leave out claims or add IDs that aren't in the dataset.

The settlement budget is a hard constraint. The `settlement_offer_usd` for all claims marked `1` must fit within the portfolio's `budget_usd` from `config.json`. A policy that goes over the budget is infeasible and scores zero.

The model mechanics are fully available in `/app/MODEL_SPEC.md`. What you don't get is the exact random draws that will be used during grading or the numeric pass bars. You'll need to make your own estimates of the objective when comparing possible decision sets. Running your own simulations is one reasonable way to do that.

Expected cost alone isn't the whole objective. The model also includes the CVaR term, and claims sharing an `incident_cluster_id` can move together. A set of decisions that looks good on average can therefore behave differently once the tail of the simulated outcomes is considered.

For development, `/app/data/worked_example/` contains 23 claims and an explanation of the setup. Its `reference_metrics.json` gives measured objectives for three example policies: settle-nothing, plain ratio-greedy, and an expected-value-optimal knapsack that ignores the correlation and tail-risk part of the objective. The first two are simple checks, while the knapsack result is useful for seeing the gap between optimizing expected cost alone and dealing with the full objective. These are reference measurements, not an answer to copy.

There is also `/app/data/case/`, with 165 claims and its own reference metrics. Use both datasets to exercise the policy. The hidden portfolios are different, so don't make the decisions depend on their particular claim IDs, values, clusters, or other visible data.

Grading uses two sealed portfolios, each in a fresh subprocess. They are checked independently against their own pass bars. The budget is checked first. Feasible submissions are then evaluated with the grader's fixed-seed Monte Carlo simulation, and the resulting objective has to meet the relevant hidden bar.

Keep the policy reasonably fast and deterministic enough to give reproducible results from the same input. Leave `/app/MODEL_SPEC.md` and everything under `/app/data/` unchanged.

Before submitting, run the policy on the worked example and the case dataset. Check that the output contains exactly the input claim IDs, uses only `0` and `1`, and stays within the budget.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
