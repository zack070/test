Work in `/app`. The file you need to leave behind is `/app/outputs/policy.py`.

The simulator is already built. `/app/sim/README.md` is the contract for how it behaves, so use that as the reference for the scheduling rules and scoring. The implementation is in `/app/sim/simulator.py` too. The `TechSnapshot` and `JobSnapshot` definitions there show exactly what `state` contains.

Your module needs to provide:

`def decide(state) -> list[tuple[str, str]]`

The simulator asks this function for assignments during the shift. Give back `(technician_id, job_id)` pairs when you want work assigned, or an empty list if you want to leave things alone. The state passed in is the current scheduling state. You can add whatever helpers or internal bookkeeping you find useful, but `decide` is the only interface the grader uses.

There is one small replay detail to keep in mind. An assignment that is not legal at the time it is returned is not applied. The same goes for duplicate names in one response: if a technician or job appears more than once, only its first occurrence is honored.

You have three scenarios to work with:

`/app/data/sample_45/`
`/app/data/sample_87/`
`/app/data/sample_150/`

Run the policy against all three. They are only development cases, though. The grader uses a different shift, with its own technicians and jobs, so don't build something that depends on the particular contents of these samples.

The submitted module is imported and run through the real simulator on that hidden shift. The returned assignments are replayed and the resulting cost is checked against a hidden quality bar. The bar was set using measured baseline and reference results. Its exact value, and the grading scenario itself, are not available here.

There is another practical constraint: the complete shift simulation has a combined wall-clock budget of 120 seconds. Keep the decision function cheap enough to run repeatedly. A clever policy that spends too much time making each decision will not help if the simulation cannot finish.

Keep `decide` deterministic. Given the same state, it should give back the same list. In particular, don't let wall-clock time, unseeded random choices, or changing outside state affect its result.

Before you finish, make sure `policy.py` imports and survives a full run without throwing an exception. Leave the simulator itself alone.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
