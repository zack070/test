Work in `/app`. The file to leave behind is `/app/outputs/policy.py`.

The simulator is already built. Start with `/app/sim/README.md`, which is the main reference for the time model, entities, `decide()` interface, and cost calculation. `/app/sim/simulator.py` is the actual code used by the grader and is worth checking when you need the exact `SimState` or `ObligationSnapshot` fields and want to see how the event loop calls the policy.

Your module needs to provide:

`def decide(state) -> list[tuple[str, str, float]]`

That is the only interface Stage 1 calls. You can organize the rest of the module however you like. Module-level state is also allowed. It survives between calls during one scenario, but each hidden grading scenario starts in a fresh process, so state from one scenario will not carry into the other.

The `state` passed to `decide` contains the current time, balances, pending obligations, currencies, and the complete current rate and cutoff information. Pending obligations have `obligation_id`, `currency`, `amount`, `due_time`, and `arrival_time`. The exact shapes and types are in the README and simulator source.

Return transfers as `(from_currency, to_currency, amount)` triples. Returning `[]` means there is nothing to do at that point. When several transfers use the same source currency in one response, they are applied in the order returned, with the available balance reduced after each one.

Transfers that are not legal at the time they are returned are simply dropped by the simulator. That includes using the same currency on both ends, a non-positive amount, an unknown currency, a pair for which there is no market, or an amount larger than the source balance remaining at that point in the batch. The simulator does not raise an exception for these cases, and a dropped transfer does not change the balances.

For local testing, use all three scenarios:

`/app/data/sample_A/`
`/app/data/sample_B/`
`/app/data/sample_C/`

They contain the configuration, rates, obligations, and credits needed to run the simulator. They are development cases, not grading data. In particular, don't make assumptions based on their specific currencies, amounts, obligations, or other values.

The grader has two hidden scenarios. Each one has its own pass bar, and they are checked separately rather than averaged together. Stage 1 runs your policy through the real simulator and records the transfers it actually returns. Stage 2 then replays that recorded sequence through the same simulator from scratch and calculates the cost again. The grading therefore comes from the transfers your policy actually produces, not from any bookkeeping or explanation inside the module.

The full simulation has a combined 200-second wall-clock limit across the two grading scenarios. `decide` can be called many times, so don't make every call unnecessarily expensive.

Keep the policy deterministic. The same state should lead to the same returned list. Don't use wall-clock time, unseeded randomness, or other changing external state to influence the result.

Leave `/app/sim` and the simulator unchanged. Before submitting, run the policy through the simulator on all three sample scenarios. Make sure the module imports and the runs complete without exceptions.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
