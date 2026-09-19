This one is hard on purpose. Two hidden 45-job cases will be run separately, each with 180 seconds, and each has its own sealed quality threshold. You need to clear both. The thresholds came from real 180-second calibration runs, and even CP-SAT, or a reasonably strong dispatch heuristic plus local search, missed the required quality on at least some of the cases. Sorting by a single priority value isn't going to get you there.

The problem itself is defined in /app/SCHEDULING_SPEC.md, so read that before you write any scheduler code. It's single-machine scheduling with no preemption. Every job has a family, a processing time, a due date and a weight. Setup time comes from the previous job's family through setup_matrix, and the first job uses initial_setup instead. Watch the same-family case in particular. Going from a family to itself still uses the matrix entry, and that entry isn't necessarily zero.

To score a sequence, simulate it from time zero, adding setup and processing time to get each completion time. The total is the sum over all jobs of weight * max(0, completion_time - due_date). Lower is better, and finishing early doesn't earn a bonus.

How you get there is your call. No particular sequence is hidden in the task for you to reproduce, so constructive scheduling, repeated improvement, search, an exact component, or a mix of them are all fair. Put the effort into schedule quality, not into something that only works for the sample IDs. Make the search aware of the clock, and keep a complete valid sequence on hand at every point, so there's always something to write if improvement stalls or the deadline gets close. Also don't let randomness make the result swing wildly between otherwise identical runs.

For checking your work, /app/data/worked_example/ has four jobs, and its README evaluates two sequences with objectives 308 and 159. Get your objective calculation to agree with both before you trust any of the search code. /app/data/case/ is a 45-job practice case with IDs J000 through J044. It has the same general data shape as the evaluation data, but it's only for practice.

Now the mechanics. Start in /app. What you're handing in is /app/outputs/scheduler.py, and the grader runs it like this:

python3 scheduler.py --instance <instance.json> --output <output.json> --time-budget <seconds>

The time value is a real cutoff. When it expires the process is stopped, with no cleanup time afterward, so the final schedule can't be left waiting in memory. It has to be written to the output path before then.

The output is one JSON object, {"sequence": [job_id, ...]}, and every job in the input has to appear in it once and only once. The checker confirms that first, making sure the sequence is a valid permutation of the jobs it supplied. Then it calculates the objective itself and compares it with that case's threshold.

Don't modify /app/SCHEDULING_SPEC.md or anything under /app/data/. Before you submit, use the worked example and the practice case to check both the permutation handling and the objective calculation. Then test the actual command-line interface with a time budget, so you know the output is written before the cutoff.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
