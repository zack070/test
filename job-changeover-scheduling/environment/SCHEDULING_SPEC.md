# Single-Machine Changeover Scheduling

This document is the complete, authoritative specification of the
scheduling problem and how a submitted sequence is scored. Every rule the
grader checks is stated here.

## 1. The problem

A single machine must process every job in the input, one at a time, in
some order you choose. There is no parallelism and no preemption: once a
job starts, it runs to completion before the next job (and that next
job's setup) begins.

Each job has:

- `job_id`
- `family` — an integer identifying which product/tooling family the job
  belongs to
- `proc_time` — how long the job takes to run, once the machine is set up
  for it
- `due_date` — the time by which the job should be complete
- `weight` — the job's priority; higher weight means lateness on this job
  costs more

## 2. Setup (changeover) time

Before a job can run, the machine may need to be reconfigured for that
job's family. This time is **sequence-dependent**: it depends on which
family ran immediately before it, not on the job itself.

- `setup_matrix` is a full `F x F` table (`F` = number of families).
  `setup_matrix[a][b]` is the time required to change the machine from
  having just finished a job in family `a` to being ready to start a job
  in family `b`. This applies between every consecutive pair of jobs in
  your sequence, based on their families, regardless of how many jobs of
  each family there are or where they fall in the sequence.
- `initial_setup` is a length-`F` array. Before the very first job in
  your sequence, the machine starts from a fixed idle state and requires
  `initial_setup[family]` time to be ready for a job of that family. This
  applies once, before the first job only.
- Setup time is never skipped, including when consecutive jobs share the
  same family — use `setup_matrix[a][a]` in that case, which may be
  nonzero (a same-family setup still represents real reconfiguration
  time, e.g. minor cleaning or calibration).

## 3. Timing and the objective

Simulate your sequence from time 0:

```
t = 0
for each job in your sequence, in order:
    if this is the first job:
        t += initial_setup[job.family]
    else:
        t += setup_matrix[previous_job.family][job.family]
    t += job.proc_time
    completion_time = t
    tardiness = max(0, completion_time - job.due_date)
    cost += job.weight * tardiness
```

The objective is the final `cost`: total weighted tardiness. Lower is
better. There is no reward for finishing early — a job that completes
before its due date contributes 0, not a negative number.

## 4. What you submit

Your submission is one Python 3 file, `scheduler.py`, invoked as:

```
python3 scheduler.py --instance <instance.json> --output <output.json> --time-budget <seconds>
```

`<instance.json>` has this shape:

```json
{
  "jobs": [
    {"job_id": "...", "family": 0, "proc_time": 0, "due_date": 0, "weight": 0}
  ],
  "setup_matrix": [[0, 0], [0, 0]],
  "initial_setup": [0, 0]
}
```

`--time-budget` gives you, in seconds, how long you have before the
process is terminated. Your program must write `<output.json>` before
that time is up — there is no grace period, and a process that is still
running when the budget expires is killed and scores 0 for that dataset,
the same as a crash. Budget your own internal time accordingly (for
example, stop searching a few seconds before the limit to guarantee you
can write the file).

Write a single JSON object to `<output.json>`:

```json
{"sequence": ["job_id_1", "job_id_2", "..."]}
```

`sequence` must be a permutation of every `job_id` in the input: every job
appears exactly once, nothing missing, nothing invented.

## 5. Grading

The grader computes your submitted sequence's objective exactly as
described in section 3, then checks it against a fixed numeric threshold
for that dataset. Your submission scores 1 if your objective is at or
below the threshold, 0 otherwise. There is no partial credit and no
reward for finishing under budget once you've cleared the threshold —
only whether you cleared it.
