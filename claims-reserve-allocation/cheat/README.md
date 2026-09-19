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

An earlier version of this bundle's pass bar sat only between an
expected-value-only knapsack and a correlation-aware MILP. Quality review
found that a ~40-line greedy-by-simulated-marginal-gain-per-dollar +
1-1-swap heuristic -- genuinely sophisticated-looking, not a strawman --
passed both bars anyway, because that kind of simulation-driven greedy
already captures nearly all of the achievable correlation-awareness gain.
The bundle now additionally includes linked-claim pairs (see
`MODEL_SPEC.md`): a handful of claims per large cluster are individually
priced as a bad deal, only worthwhile once settled together with a
specific partner claim. Neither half of a pair shows any standalone
improvement, so no per-claim marginal-value search -- greedy, 1-1 swaps,
or the plain EV-only knapsack -- can find them; only genuine joint
reasoning does (the reference solution's AND-linearized MILP). Both
sealed bars are now calibrated directly against a measured run of that
same reported heuristic (`cheat/greedy_marginal_value_swap/`), not just
against the EV-only baseline, so the exploit that got through the
previous version is included in this bundle's own adversarial suite and
confirmed to fail.

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

An EXACT 0/1 knapsack solution (via MILP) that maximizes expected savings
subject to the budget, completely ignoring cluster correlation, the CVaR
term, and linked-pair complementarity. This is not a strawman -- it is
mathematically optimal for expected cost alone, and would pass a task
that only measured expected cost.

**Measured result: reward 0 on both portfolios.** Held-out 1: objective
25,867,616 against a pass bar of 24,020,473 (expected_cost=4,510,548,
cvar=7,119,022). Held-out 2: objective 22,818,775 against a pass bar of
20,783,693 (expected_cost=4,062,809, cvar=6,251,989). The shortfall
(~7.7%-9.8%) is large and reproducible -- this baseline both concentrates
deferred exposure in correlated clusters and never settles a linked pair
(each pair member looks like a loss in isolation).

## 10. Greedy by simulated marginal value + 1-1 swaps (`greedy_marginal_value_swap/`)

The exploit reported by quality review against an earlier version of
this bundle, kept here as a permanent regression check: builds its own
Monte Carlo simulator from `MODEL_SPEC.md`, greedily settles whichever
remaining budget-feasible claim gives the best simulated full-objective
improvement per dollar (recomputed against the current partial decision
set each round -- not a one-shot ranking), then polishes with 1-1 swaps.
It correctly handles cluster correlation (it's evaluating the true
simulated objective, not a closed-form proxy), but has no notion of
linked-claim pairs, so it never settles either half of one.

**Measured result: reward 0 on both portfolios.** Held-out 1: objective
25,443,629 against a pass bar of 24,020,473. Held-out 2: objective
21,626,194 against a pass bar of 20,783,693. In both cases it settles
zero linked-pair claims -- confirmed directly, not inferred -- and the
shortfall (~3.4%-4.1%) is real: correlation-awareness alone is not
enough once complementary pairs are part of the model.

## 11. Memorized visible answers (`hardcoded_answers/`)

Embeds a lookup table of decisions computed on the visible `case/`
dataset (built with `ev_optimal`), keyed by `claim_id`, falling back to
settle-nothing for anything unrecognized -- embedded directly in
`policy.py` rather than shipped as a side file, since only the one
submitted file is ever graded.

**Measured result: reward 0.** Held-out `claim_id`s happen to reuse the
same `CLM####` numbering scheme as the visible case dataset (both restart
at `CLM0001`), so this cheat's lookup table technically "hits" on every
held-out id -- but the underlying facts differ, and concretely: replaying
the case-dataset decisions verbatim overspends both sealed budgets
(measured: $1,423,186.43 used against a $1,422,917.65 cap on held_out_1;
$1,375,045.26 against $1,312,456.77 on held_out_2) and is rejected on the
mechanical feasibility check before any simulation runs -- a deterministic
dollar-sum check, not subject to simulation noise. Confirms held-out
grading tests whether the policy's logic generalizes to the actual
portfolio it's run against, not whether the agent can pattern-match on
identifiers.

## Reference solution, for contrast

`solution/policy.py` (the scenario-based, CVaR-aware, pair-linearized
MILP) measures reward 1 on both held-out portfolios -- see the numbers
recorded in `tests/sealed/reference/*.json`'s `_calibration_measured`
block for the exact figures, and `dev/build_bundle.py`'s own printed
output for how the pass bar was derived from them (whichever of the
EV-only or greedy+swap baselines gives the stricter bound).
