Work in `/app`. The file to leave behind is `/app/outputs/policy.py`.

The simulator is already there. Use `/app/sim/README.md` as the main reference for the scheduling rules and scoring. `/app/sim/simulator.py` is useful too, especially the `TechSnapshot` and `JobSnapshot` definitions since those show what arrives in `state`.

The policy needs this function:

`def decide(state) -> list[tuple[str, str]]`

The simulator calls it during the shift and expects `(technician_id, job_id)` pairs for work you want assigned. Returning `[]` is fine when there is nothing to assign. `state` is the current scheduling state at that point in the replay. You can structure the module however you want and use helpers or internal bookkeeping, but `decide` is the only function the grader calls.

One replay detail matters. If an assignment is illegal when it is returned, the simulator ignores it. Duplicate technicians or jobs in the same response are handled the same way: only the first occurrence is honored.

There are three development scenarios:

`/app/data/sample_45/`
`/app/data/sample_87/`
`/app/data/sample_150/`

Run the policy on all three before you call it finished. They are just development cases, so don't tie the policy to their particular technicians, jobs, or other values. The actual grading uses two different shifts. Each shift is checked against its own quality bar, so passing one does not make up for missing the other.

The grader imports `policy.py` and runs it through the real simulator on those two hidden shifts. It replays the assignments and checks the resulting cost against the hidden bars. The bars were set from measured baseline and reference results. You won't have the exact values or the grading shifts.

There is also a 200-second wall-clock budget for the complete simulation, combined across both grading shifts. `decide` may be called many times, so keep the work done on each call reasonably small. Spending a lot of time searching for a better assignment at every decision can make the whole run miss the limit.

Keep the result deterministic. The same state should produce the same list. Wall-clock time, unseeded randomness, or changing external state should not affect the decision.

Before submitting, run the module through the simulator and make sure it imports cleanly and completes without an exception. Leave the simulator unchanged.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
