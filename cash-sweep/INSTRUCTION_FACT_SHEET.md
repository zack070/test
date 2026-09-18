# Fact sheet for instruction.md (cash-sweep)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself. Facts only; no narrative framing implied.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/policy.py`.
- The module must define: `def decide(state) -> list[tuple[str, str, float]]`
- The grader (Stage 1) only ever calls `decide`. The module can have any
  other structure, helpers, or module-level state.
- `decide` may be called many times across a scenario; module-level state
  persists across calls WITHIN one scenario, but each of the two grading
  scenarios runs in a fresh process, so nothing carries over between them
  (don't rely on it, and don't worry about accidentally leaking state
  between them either).

## Reference material available to the agent

- `/app/sim/README.md` -- the full simulator contract in prose (time
  model, entities, decide() interface, cost formula). This is the primary
  reference.
- `/app/sim/simulator.py` -- the actual simulator source, byte-identical
  to what grades the submission. Useful for exact field names
  (`SimState`, `ObligationSnapshot`) and to see `run_simulation`'s event
  loop directly.
- Three sample scenario directories for local development:
  - `/app/data/sample_A/`
  - `/app/data/sample_B/`
  - `/app/data/sample_C/`
  Each contains `config.json` (currencies, starting_balances, horizon),
  `rates.csv` (from_currency, to_currency, cheap_rate, expensive_rate,
  cutoff_time), `obligations.csv` (obligation_id, currency, amount,
  due_time, arrival_time), `credits.csv` (credit_id, currency, amount,
  arrival_time). These are development cases only -- don't tie the policy
  to their particular currencies, obligations, or values.

## decide() interface (exact fields, from SimState)

- `current_time: int`
- `balances`: tuple of `(currency, balance)` pairs, every currency
- `pending_obligations`: tuple of snapshots, each with `obligation_id`,
  `currency`, `amount`, `due_time`, `arrival_time` -- only obligations
  that have arrived and are not yet resolved
- `currencies`: tuple of every currency in the scenario
- `spread_cheap`, `spread_expensive`: tuple of `(from_currency,
  to_currency, rate)` triples, every tradeable pair
- `cutoff_time`: tuple of `(from_currency, to_currency, cutoff)`
  triples, every tradeable pair

The rate/cutoff schedule is static for the whole scenario and is resent
in full on every call.

## Return value / legality

- Return a list of `(from_currency, to_currency, amount)` triples.
- `[]` means "do nothing right now."
- Multiple transfers drawing on the same source currency in one call are
  all honored, in order, against a balance that decrements as each is
  applied.
- An illegal transfer (same currency both ends, non-positive amount, a
  currency not in the scenario, a pair with no market, or an amount that
  would exceed the source's remaining balance at that point in the
  batch) is silently dropped -- no exception, and that one transfer's
  balances are left untouched.

## Grading structure

- Grading uses two hidden scenarios. The agent does not get their exact
  values or contents.
- Each scenario is checked against its OWN pass bar independently -- not
  an average. Passing one does not make up for missing the other.
- The grader (Stage 1) drives the real simulator and records the exact
  sequence of transfers `decide()` returns at each call. Stage 2
  independently replays that sequence through the same deterministic
  simulator from scratch and recomputes the cost -- so nothing about the
  policy's own bookkeeping or self-reported reasoning is trusted, only
  the actual sequence of transfers it returned.

## Constraints

- 200-second wall-clock budget for the complete simulation, combined
  across both grading scenarios. `decide` may be called many times, so
  keep per-call work reasonably small.
- Keep the result deterministic: the same state should produce the same
  list. Wall-clock time, unseeded randomness, or other external state
  should not affect the decision.
- Leave the simulator unchanged.
- Before submitting, run the module through the simulator on all three
  sample scenarios and make sure it imports cleanly and completes
  without an exception.
- (Standard boilerplate, matching the companion field-service-dispatch
  task) total time budget and "do not cheat / use hints specific to this
  task" clause.

## Open items only you can fill in (task.toml)

- `author_name` / `author_email`
- `relevant_experience` -- a first-person statement of your own
  professional background relevant to judging whether this task's
  premise (an intraday treasury cash-sweep desk) and grading (a
  held-out simulation replay against a calibrated cost bar) are
  realistic and fair, the same kind of statement used in the companion
  field-service-dispatch bundle's task.toml.
