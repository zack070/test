Start in `/app`. Your submission is `/app/outputs/scheduler.py`.

The grader will invoke it as:

`python3 scheduler.py --instance <instance.json> --output <output.json> --time-budget <seconds>`

The time value passed to the program is a real cutoff. Once it expires, the process is stopped. There is no cleanup time afterward, so don't leave the final schedule waiting in memory.

Your program should write one JSON object:

`{"sequence": [job_id, ...]}`

Every job in the input must appear in that list once, and only once.

Read `/app/SCHEDULING_SPEC.md` before working on the scheduler. That file defines the actual problem. In short, this is a single-machine scheduling problem with no preemption. A job has a family, processing time, due date, and weight. Setup time is part of the schedule too. It comes from the family of the previous job through `setup_matrix`, while the first job uses `initial_setup`.

One easy detail to get wrong: a transition from a family to that same family still uses the matrix entry. Those entries are not necessarily zero.

The score comes from simulating the sequence from time zero. Include setup and processing time when determining each completion time, then add:

`weight * max(0, completion_time - due_date)`

for each job. Lower total weighted tardiness is the target. Being early does not give a bonus.

You have room to choose the algorithm. There isn't a particular sequence hidden in the task that you are expected to reproduce. A good solution could use constructive scheduling, repeated improvement, search, an exact component, or several of these together. Spend the available time on the quality of the schedule rather than building something that only works for the sample IDs.

There is a small worked case at `/app/data/worked_example/`. It has four jobs. The README evaluates two sequences and gives objectives of 308 and 159. Check your objective calculation against those before trusting the search code.

For something larger, `/app/data/case/` contains a 45-job practice case using IDs `J000` through `J044`. It has the same general data shape as the evaluation data, but it is only there for practice.

The actual run uses two separate hidden 45-job cases. Each is given 180 seconds. They have separate quality thresholds, and both have to pass. The checker first makes sure your sequence is a valid permutation of the jobs it supplied, then calculates the objective itself and compares it with that case's sealed threshold.

The target is intentionally demanding. Real 180-second calibration runs showed that even CP-SAT and a reasonably strong dispatch heuristic plus local search missed the required quality on at least some of the cases. A simple sort by one priority value is therefore unlikely to carry the task by itself.

Make the search time-aware. Keep a valid complete sequence available throughout the run so there is something to write if improvement stops or the deadline gets close. Avoid depending on randomness in a way that makes the result swing wildly between otherwise identical runs.

Don't modify `/app/SCHEDULING_SPEC.md` or anything in `/app/data/`.

Use the worked example and practice case before submitting. Check both the permutation handling and the objective calculation, and test the actual command-line interface with a time budget so you know the output is written before the cutoff.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
