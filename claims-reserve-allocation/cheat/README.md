# Adversarial testing notes

Harbor never executes anything under this directory. Every attempt here
was actually run against the real verifier via `dev/local_harness.sh`
(which runs the real `tests/test.sh`, `collect_agent_output.py`, and
`test_claims_grading.py` against real `/app`, `/tests`, `/work`, `/logs`
paths and a Python matching `tests/Dockerfile`'s exact pinned installs).
Results below are measured, not hypothetical.

The agent's deliverable is executable code (`/app/outputs/policy.py`),
run once per sealed held-out portfolio at grading time -- a one-shot
batch call, not a live per-event decide() loop, so there's no
incrementally-revealed state to leak and no separate trusted process
running a live simulation to introspect. What has to stay hidden is only
the exact Monte Carlo draws used to grade the submission and the numeric
pass bar itself.

## 1. Reward forgery (`reward_forgery/`)

`run()` tries to overwrite `/logs/verifier/reward.txt` with `1` directly,
then returns an empty decision set.

**Measured result: reward 0.** The write is attempted under the `runner`
UID; `/logs/verifier` is root-owned and sealed before Stage 1 runs, and
Stage 2's own independent grading still runs afterward and overwrites
whatever Stage 1 did to the reward file regardless. (The empty decision
set would also fail Stage 2's coverage check on its own.)

## 2. Sealed reference read (`sealed_ground_truth_read/`)

Tries to read `/tests/sealed/reference/held_out_1_reference.json` and
`held_out_2_reference.json` directly by name, plus a directory listing.

**Measured result: reward 0**, and every attempt genuinely fails --
`test.sh` chown+chmod's `/tests/sealed/reference` to root-only before
Stage 1 (running as `runner`) ever executes. The raw sealed INPUT
portfolio files are deliberately left unsealed, since the candidate's own
code has to read them to compute anything; only the grading seed and bar
are sealed.

## 3. Crashing policy (`crashing/`)

Unconditionally raises `RuntimeError`.

**Measured result: reward 0.** `collect_agent_output.py` catches the
non-zero exit, records `status: "crashed"`, and Stage 2 fails the
"policy present and ran" check cleanly.

## 4. Malformed submission -- wrong interface (`malformed_no_cli/`)

Defines `solve(data_dir)` instead of `run(data_dir)`, with no
`if __name__ == "__main__":` block, so invoking it as a script produces
no output file.

**Measured result: reward 0.** Stage 1 detects the missing output file
before Stage 2 has anything to grade.

## 5. Infinite loop (`infinite_loop/`)

Loops forever.

**Measured result: reward 0**, confirmed to actually time out rather
than hang the verifier.

## 6. Budget violation (`budget_violation/`)

Settles every claim regardless of the budget cap.

**Measured result: reward 0 on both portfolios**, rejected mechanically
on the feasibility check before any simulation runs -- confirms the
budget cap can't be bypassed by an otherwise-plausible-looking decision
set.

## 7. Settle nothing (`settle_nothing/`)

Defers every claim -- trivially feasible, but forfeits every settlement
discount.

**Measured result: reward 0 on both portfolios.**

## 8. Arbitrary-order greedy (`arbitrary_order_greedy/`)

Settles claims in file order until the budget runs out, ignoring value
entirely -- the "did essentially no analysis" baseline.

**Measured result: reward 0 on both portfolios.**

## 9. Expected-value-optimal, risk-blind (`ev_only_risk_blind/`)

The most important negative result in this bundle: an EXACT 0/1 knapsack
solution (via MILP) that maximizes expected savings subject to the
budget, completely ignoring cluster correlation and the CVaR term. This
is not a strawman -- it is mathematically optimal for expected cost alone,
and would pass a task that only measured expected cost.

**Measured result: reward 0 on both portfolios.** Held-out 1: objective
26,254,698 against a pass bar of 25,798,709 (expected_cost=4,554,257,
cvar=7,233,481). Held-out 2: objective 23,296,704 against a pass bar of
22,858,574 (expected_cost=4,094,213, cvar=6,400,830). In both cases the
shortfall (~1.8%-1.9%) is real and reproducible, not a rounding artifact --
this baseline concentrates deferred exposure inside the large correlated
clusters (because doing so is expected-value-neutral or better) and pays
for it in CVaR.

## 10. Memorized visible answers (`hardcoded_answers/`)

Embeds a lookup table of decisions computed on the visible `case/`
dataset (built with `ev_optimal`), keyed by `claim_id`, falling back to
settle-nothing for anything unrecognized -- embedded directly in
`policy.py` rather than shipped as a side file, since only the one
submitted file is ever graded (`cheat/hardcoded_answers/memorized.json`
is kept alongside only for readability, and isn't read by the cheat
itself).

**Measured result: reward 0.** Held-out `claim_id`s happen to reuse the
same `CLM####` numbering scheme as the visible case dataset (both restart
at `CLM0001`), so this cheat's lookup table technically "hits" on every
held-out id -- but the underlying facts differ, and concretely: the
visible case dataset's budget is larger than either sealed portfolio's,
so replaying the case-dataset decisions verbatim overspends the held-out
budget (measured: $1,373,644.92 used against a $1,267,629.60 cap on
held_out_2) and is rejected on the mechanical feasibility check before
any simulation runs. Confirms held-out grading tests whether the
policy's logic generalizes to the actual portfolio it's run against, not
whether the agent can pattern-match on identifiers.

## Reference solution, for contrast

`solution/policy.py` (the scenario-based, CVaR-aware MILP) measures
reward 1 on both held-out portfolios: objective 25,200,854 (bar
25,798,709, margin ~2.3%) on held_out_1, and 21,894,412 (bar 22,858,574,
margin ~4.2%) on held_out_2 -- comfortably under both bars, not just
barely.
