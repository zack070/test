# Worked example

23 claims, small enough to compute by hand or spot-check quickly. Not the
graded data -- use it to check your understanding of the model and to
validate your own simulator before working through `/app/data/case/`.

Budget: `$172,378.94`. Total settlement offers if you settled every claim:
sum the `settlement_offer_usd` column yourself -- it's comfortably above
budget, so you cannot settle everyone; some claims must be deferred.

A few things worth noticing in this data before you build anything:

- **`CLU0001` and `CLU0002`** are two clusters of AUTO claims (4 and 3
  claims respectively). Every claim within one of these clusters shares
  the *same* `incident_cluster_id` -- meaning, per `MODEL_SPEC.md`, they
  share the same random `cluster_factor` draw if deferred. Whatever
  fraction of a cluster you leave deferred rises and falls together, not
  independently.
- Look at the `linked_claim_id` column for these two clusters. `CLU0001`'s
  four claims are two linked pairs; `CLU0002` has one linked pair plus one
  unlinked claim. Check each linked claim's `settlement_offer_usd` against
  its own expected deferred cost (computable from `MODEL_SPEC.md`'s
  formulas and this data's `config.json`) -- notice what that comparison
  looks like for a linked claim considered by itself, versus for an
  ordinary, unlinked claim.
- The rest of the claims sit in clusters of size 1-3, spread across all
  three claim types, with discounts spanning the full disclosed range --
  ordinary, uncorrelated, unlinked exposure.

`reference_metrics.json` in this directory gives the measured
`expected_cost` / `cvar` / `objective` for three example policies --
settling nothing, a plain per-claim ratio-greedy fill of the budget, and
the exact expected-value-optimal knapsack -- computed with a large number
of simulation paths under `MODEL_SPEC.md`'s exact formulas. These are
here so you can validate your own simulator: build it, run it against
these same three policies on this data, and confirm your numbers land
close to the ones given. They are not the task's answer -- there is no
single correct decision set to match against, only an objective to
minimize.
