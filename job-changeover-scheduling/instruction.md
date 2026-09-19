Work in /app. What you're handing in is /app/outputs/scheduler.py, and it has to run like this:

python3 scheduler.py --instance <instance.json> --output <output.json> --time-budget <seconds>

The --time-budget value is real, so treat it as a hard deadline. There's no grace period once it runs out, which means an answer has to be written to the output path before the process gets killed.

The output itself is simple: {"sequence": [job_id, ...]}. The list has to contain every job from the instance exactly once. No missing IDs, no duplicates, no made-up jobs.

The actual scheduling rules are in /app/SCHEDULING_SPEC.md, so read that before you build anything. It's a single-machine, non-preemptive schedule. Each job has a family, a processing time, a due date and a weight. Setup time depends on the family of the job that ran immediately before, using the supplied setup_matrix. The first job uses initial_setup instead. Don't assume that switching to the same family means no setup. The matrix covers same-family transitions too, and those entries can be nonzero.

For a given sequence, start the clock at zero, apply the required setup, run each job, and work out its weighted tardiness from its completion time. The objective is the sum of weight * max(0, completion_time - due_date), and lower is better. Finishing before a due date earns nothing extra.

There's no reference sequence to reproduce here. This is an optimization task, so pick whatever approach you think will get a strong result in the time available: heuristics, local improvement, an exact method, or some mix. What matters is the schedule that actually gets written.

There's a small sanity check in /app/data/worked_example/, with four jobs and two families. Its README gives two sequences evaluated by hand, with objectives 308 and 159. Make sure the scorer in your own code agrees with both before you start tuning.

/app/data/case/ is a larger practice instance with 45 jobs, IDs J000 through J044. It isn't the grading instance, so don't build a solution that leans on those particular IDs or figures.

The real evaluation uses two different hidden 45-job instances. They're run separately, each with a 180-second budget. Each has its own quality threshold, and you need to clear both to score 1.

The grader starts by checking the sequence itself. It has to be an exact permutation of the hidden instance's job IDs. If that's wrong, there's no useful objective score to recover. After that, the grader calculates the objective on its own and compares it with the sealed threshold for that instance.

Those thresholds are deliberately not trivial. They were calibrated from real runs at the same 180-second limit, and in those measurements even CP-SAT and a competent dispatch heuristic with local search didn't reliably hit the required result on both hidden cases. A basic one-pass priority rule is unlikely to be enough.

Keep an eye on the clock while you search for improvements. A schedule that's still sitting in memory when time runs out scores the same as a failed run. The program should also behave reasonably consistently from one run to the next.

Leave /app/SCHEDULING_SPEC.md and everything under /app/data/ unchanged.

Before you submit, run the worked example and the practice instance to confirm the sequence format and the objective calculation behave as expected, and make sure the output file is written before the supplied --time-budget expires.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
