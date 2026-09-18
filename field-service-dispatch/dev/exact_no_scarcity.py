"""Calibration-only variant of the primary reference: exact joint batch
matching (Hungarian, no truncation) WITHOUT any scarce-skill reservation
term. Used to measure how much of the reference's advantage over greedy
comes from recognizing the joint-assignment structure alone, versus from
scarcity awareness on top of it."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solution"))
from policy import _hungarian_min_cost  # reuse the verified Hungarian solver

FATIGUE_THRESHOLD_MIN = 180
FATIGUE_MULTIPLIER = 1.25
BREACH_PENALTY = 200.0
_SAFETY_JOB_CAP = 120


def _duration_for(job, tech):
    if tech.continuous_work >= FATIGUE_THRESHOLD_MIN:
        return int(round(job.duration * FATIGUE_MULTIPLIER))
    return job.duration


def _pairing_cost(job, tech, now):
    if job.required_skill not in tech.skills:
        return None
    dur = _duration_for(job, tech)
    finish = now + dur
    shift_limit = tech.shift_end + tech.max_overtime
    if finish > shift_limit:
        return None
    if finish > job.deadline:
        # doesn't actually save the job -- infeasible, not neutral (see
        # solution/policy.py for the full reasoning)
        return None
    overtime = max(0, finish - max(now, tech.shift_end))
    fatigue_waste = dur - job.duration
    avoided_breach_credit = -(BREACH_PENALTY * 0.9) - (30.0 if job.priority == "urgent" else 0.0)
    return overtime * 1.5 + fatigue_waste + avoided_breach_credit


def _best_matching(jobs, techs, now):
    R, C = len(techs), len(jobs)
    if R == 0 or C == 0:
        return []
    BONUS = 1_000_000.0
    BIG = 1_000_000_000.0
    n = R + C
    cost = [[0.0] * n for _ in range(n)]
    raw = {}
    for i, t in enumerate(techs):
        for j, jb in enumerate(jobs):
            c = _pairing_cost(jb, t, now)
            if c is None:
                cost[i][j] = BIG
            else:
                raw[(i, j)] = c
                cost[i][j] = c - BONUS
    for i in range(R):
        cost[i][C + i] = 0.0
    for j in range(C):
        cost[R + j][j] = 0.0
    assign = _hungarian_min_cost(cost)
    result = []
    for i in range(R):
        j = assign[i]
        if j < C and (i, j) in raw:
            result.append((jobs[j], techs[i]))
    return result


def decide(state):
    all_jobs = list(state.pending_jobs)
    all_techs = list(state.free_technicians)
    if not all_jobs or not all_techs:
        return []

    def job_priority(j):
        return (0 if j.priority == "urgent" else 1, j.deadline)

    jobs_to_serve = sorted(all_jobs, key=job_priority)[:_SAFETY_JOB_CAP]
    techs_batch = all_techs[:_SAFETY_JOB_CAP]

    result = _best_matching(jobs_to_serve, techs_batch, state.current_time)

    assignments = []
    used_techs = set()
    used_jobs = set()
    for j, t in result:
        if t.tech_id in used_techs or j.job_id in used_jobs:
            continue
        assignments.append((t.tech_id, j.job_id))
        used_techs.add(t.tech_id)
        used_jobs.add(j.job_id)
    return assignments
