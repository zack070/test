# Claims reserve allocation -- model specification

This is the complete, authoritative statement of the model your policy is
graded against. Nothing about the mechanics is hidden; only the exact
random draws used at grading time (and the pass bar itself) are sealed,
the same way a real reserving team knows the model it's optimizing under
but not the future it hasn't observed yet.

## Setup

A portfolio is a batch of open claims. Each claim belongs to exactly one
`claim_type` and exactly one `incident_cluster_id`. For every claim you
must decide, once, whether to **settle now** or **defer**:

- **Settle now**: costs exactly `settlement_offer_usd` (given in the data,
  fixed, known today).
- **Defer**: costs a random amount realized later (see "Deferred cost"
  below) -- you don't know this number today, only its distribution.

Your decision for a portfolio is a 0/1 value per `claim_id` (1 = settle,
0 = defer), subject to one hard constraint:

> The sum of `settlement_offer_usd` over every claim you settle must not
> exceed that portfolio's `budget_usd`.

A decision set that violates the budget is infeasible and is not scored
further, regardless of what it would otherwise achieve.

## Deferred cost

If a claim is deferred, its eventual realized cost is:

```
base_severity   ~ LogNormal(type mean_severity_usd, type severity_cv)
cluster_factor  ~ LogNormal(mean 1)   -- ONE draw per incident_cluster_id,
                                          shared by every claim in that
                                          cluster (this is what makes
                                          claims in the same cluster
                                          correlated -- they rise and fall
                                          together)
litigated       ~ Bernoulli(type litigation_prob)
escalation      = type escalation_factor if litigated else 1

realized        = base_severity * cluster_factor * escalation
deferred_cost   = realized * (1 + interest_rate_annual * deferral_years)
```

`base_severity`'s LogNormal parameters are derived from the disclosed
`mean_severity_usd` and `severity_cv` (coefficient of variation) the
standard way: `sigma = sqrt(ln(1 + cv^2))`, `mu = ln(mean) - sigma^2/2`.
The `cluster_factor` LogNormal has `sigma = cluster_sigma` (disclosed) and
`mu = -0.5 * cluster_sigma^2`, chosen so its mean is exactly 1 -- it's a
pure amplifier, not a bias.

Every random draw above is independent of every other, except that all
claims sharing an `incident_cluster_id` use the *same* `cluster_factor`
draw. `interest_rate_annual` and `deferral_years` are portfolio-level
constants (given in `config.json`), applied identically to every deferred
claim in that portfolio.

## Objective

Let `total_cost` be the sum, across all claims, of `settlement_offer_usd`
(if settled) or `deferred_cost` (if deferred) -- a random variable induced
by the draws above, given your fixed decision set. You are scored on:

```
objective = E[total_cost] + risk_lambda * CVaR_alpha(total_cost)
```

`CVaR_alpha` (`alpha` disclosed, e.g. 0.95) is the mean of the worst
`(1 - alpha)` tail of the `total_cost` distribution -- i.e. if you ran this
decision set many times, it's the average cost on the worst 5% of runs.
`risk_lambda` (disclosed) is how heavily that tail is weighted against the
plain average. Lower `objective` is better; you are trying to minimize it.

This is not the same as minimizing expected cost alone. A decision set
that concentrates deferred exposure inside one or two large, correlated
clusters can have excellent expected cost (because on average nothing goes
wrong) while still scoring worse on `objective`, because on the unlucky
draws where that cluster's shared factor lands high, every claim in it
gets hit at once -- there's no diversification benefit within a cluster,
because they aren't independent.

## Data given to you, per portfolio

- `claims.csv`: `claim_id, claim_type, incident_cluster_id, settlement_offer_usd`
- `config.json`: the full disclosed parameters above --
  `claim_types` (per type: `mean_severity_usd`, `severity_cv`,
  `litigation_prob`, `escalation_factor`), `cluster_sigma`,
  `interest_rate_annual`, `deferral_years`, `risk_alpha`, `risk_lambda`,
  `budget_usd`.

`claim_types`' parameters and `cluster_sigma` / `interest_rate_annual` /
`deferral_years` / `risk_alpha` are the same across every portfolio you'll
ever see (visible or graded); only the claim mix, cluster structure, and
`budget_usd` vary by portfolio. They're still repeated in every
`config.json` so your code never has to hardcode them.

## What is NOT disclosed

The exact random draws used to grade your submission, and the numeric
pass bar itself, are not available to you. You cannot reproduce grading
exactly -- you're expected to build your own estimate of `objective` (e.g.
via your own Monte Carlo simulation using the model above) and use it to
compare candidate decision sets, the same way you'd validate a reserving
policy against a simulated distribution of outcomes before committing to
it in practice.
