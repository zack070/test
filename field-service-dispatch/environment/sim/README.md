# Dispatch simulator contract

`simulator.py` is the complete, authoritative implementation of how a shift
plays out. This document explains it in prose; where the two differ, the
code is correct (report it as a bug if you find a difference). Nothing
about how the simulator works is hidden from you.

## Time and entities

Time is in integer minutes. A shift runs from minute 0 to `shift_length`
(the scenario data gives this; sample scenarios use 480, an 8-hour shift).
All technicians are on duty from minute 0.

A **technician** has: an id, a set of skills, a `shift_end` minute, and a
`max_overtime` (additional minutes they may work past `shift_end`). A
technician can never be assigned a job whose finish time would exceed
`shift_end + max_overtime`.

A **job** has: an id, a required skill, a base duration in minutes, a
priority (`standard` or `urgent`), a deadline (the minute by which it must
be *completed*), and an arrival time (the minute it becomes visible to your
policy). Jobs with `arrival_time = 0` are known at shift start; others
arrive mid-shift and are invisible to your policy until that moment.

## Your policy

You submit a Python module exposing:

```python
def decide(state) -> list[tuple[str, str]]:
    ...
```

`state` has `current_time`, `free_technicians` (only technicians idle right
now), and `pending_jobs` (only jobs that have arrived and are not yet
assigned). Each technician/job snapshot exposes every field described
above (see `simulator.py`'s `TechSnapshot`/`JobSnapshot` for exact field
names). `decide` returns a list of `(technician_id, job_id)` pairs to
assign immediately; returning `[]` means "assign nothing right now, leave
everyone idle." A technician or job named more than once in one returned
list only has its first occurrence honored. An assignment naming a
technician who isn't actually free, a job that isn't actually pending, a
skill mismatch, or a finish time beyond that technician's overtime cap is
silently dropped -- it does not raise an error, and neither the technician
nor the job is consumed.

`decide` is called once at shift start, once whenever any technician
becomes free, and once whenever any job arrives -- but only when there is
at least one free technician AND at least one pending job at that moment.
There is no other way to be notified that time has passed; if you want a
technician to intentionally sit idle rather than take an available job,
return an assignment list that leaves them out, and they remain a
candidate at the next decision point.

## Fatigue

Each technician tracks `continuous_work`: minutes of job time completed
since their last break, given to you on every snapshot. If a technician is
free (idle) for 15 consecutive minutes or more, `continuous_work` resets to
zero the moment that threshold is reached. It does not reset on shorter
idle gaps, and it does not accumulate during idle time -- only actual job
time adds to it.

If, at the moment a job is assigned, the technician's `continuous_work` is
180 minutes or more, that job's actual duration is inflated to
`round(base_duration * 1.25)`. This multiplier is fixed for that job's
entire duration once assigned (it is not recalculated mid-job even if the
technician's fatigue state would otherwise change). The inflated duration
is what adds to `continuous_work` afterward.

## SLA breach and cascade

A job breaches the instant simulated time exceeds its deadline while it is
still pending or in progress (completing exactly at the deadline is not a
breach). A breached job keeps running to completion if already in
progress; the breach is recorded regardless.

If a breached job's priority is `urgent` and it is not itself a follow-up
job, a follow-up job is created at that instant: required_skill equal to
the original job's, `base_duration = 30`, `priority = standard`,
`deadline = breach_time + 60`, `arrival_time = breach_time` (visible
immediately). Follow-up jobs never spawn further follow-ups even if they
themselves breach. A breached `standard`-priority job never cascades.

## Overtime

A technician accrues overtime minutes equal to however much of an assigned
job's duration falls after their `shift_end`. This is tracked per
technician (`overtime_used`) and is included in every later snapshot of
that technician.

## Cost (lower is better; this is what you are scored on)

```
total_cost = (total overtime minutes across all technicians) * 1.5
           + (number of jobs that breached, including follow-ups) * 200
           + (number of follow-up jobs spawned) * 50
```

There is no reward for finishing early and no separate reward for
utilization; the only things that cost anything are overtime, breaches,
and cascades. A job that is never assigned at all will, once its deadline
passes, count as a breach the same as one that was attempted and ran late.
