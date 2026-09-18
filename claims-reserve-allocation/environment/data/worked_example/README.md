# Worked example

23 claims, small enough to compute by hand or spot-check quickly. Not the
graded data -- use it to check your understanding of the model and to
validate your own simulator before working through `/app/data/case/`.

Budget: `$172,378.94`. Total settlement offers if you settled every claim:
sum the `settlement_offer_usd` column yourself -- it's comfortably above
budget, so you cannot settle everyone; some claims must be deferred.

Two things worth noticing in this data before you build anything:

- **`CLU0001` and `CLU0002`** are two clusters of AUTO claims (4 and 3
  claims respectively) all priced at a similar, fairly ungenerous
  discount. Priced on its own, any single one of these claims looks like
  an unremarkable, middling deal -- nothing about a single claim's numbers
  flags it as special. What a per-claim view can't show you is that every
  claim within one of these clusters shares the *same* `incident_cluster_id`
  -- meaning, per `MODEL_SPEC.md`, they share the same random
  `cluster_factor` draw if deferred. Whatever fraction of this cluster you
  leave deferred rises and falls together, not independently.
- The rest of the claims sit in clusters of size 1-3, spread across all
  three claim types, with discounts spanning the full disclosed range --
  ordinary, uncorrelated exposure.

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
