# Case dataset

165 claims -- the same size and shape as the two sealed portfolios you'll
be graded against, so this is the right dataset to develop and stress-test
your policy on before submitting. Not the graded data itself.

Same model, same disclosed parameters (`config.json`, matching
`MODEL_SPEC.md`), just a fresh, larger claim mix and its own budget. As
with the worked example, some claims share `incident_cluster_id`s in
groups larger than one -- look at the distribution of cluster sizes in
`claims.csv` yourself rather than assuming it matches the worked example's
exact shape.

`reference_metrics.json` gives the same three baseline measurements as
the worked example (settle-nothing, plain ratio-greedy, and the exact
expected-value-optimal knapsack), for validating your simulator at this
larger scale. Notice that the ratio-greedy and the expected-value-optimal
knapsack don't necessarily agree on which one scores better under the
full objective -- expected-value optimality and objective optimality are
not the same thing here.
