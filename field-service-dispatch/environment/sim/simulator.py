"""
Deterministic discrete-event field-service dispatch simulator.

This module is the single source of truth for how a shift plays out given
a dispatch policy. It is copied byte-identical into environment/sim/ (agent
visible, full source, nothing hidden) and tests/ (hidden verifier, run
against the sealed held-out scenario). Keep dev/sync_sim.sh in sync after
any edit here.

Constants (all disclosed to the agent -- see environment/sim/README.md):
  BREAK_THRESHOLD_MIN = 15   -- minutes continuously free before a break resets fatigue
  FATIGUE_THRESHOLD_MIN = 180 -- continuous worked minutes before fatigue penalty applies
  FATIGUE_MULTIPLIER = 1.25  -- duration multiplier once fatigued, locked in at assignment time
  OVERTIME_RATE = 1.5        -- cost multiplier per overtime minute (vs base rate of 1.0/minute)
  BREACH_PENALTY = 200.0     -- cost per job that misses its deadline
  CASCADE_COST = 50.0        -- fixed administrative cost per follow-up job spawned
  FOLLOWUP_DURATION_MIN = 30
  FOLLOWUP_SLA_MIN = 60      -- follow-up job's deadline is breach_time + this
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

BREAK_THRESHOLD_MIN = 15
FATIGUE_THRESHOLD_MIN = 180
FATIGUE_MULTIPLIER = 1.25
OVERTIME_RATE = 1.5
BREACH_PENALTY = 200.0
CASCADE_COST = 50.0
FOLLOWUP_DURATION_MIN = 30
FOLLOWUP_SLA_MIN = 60


@dataclass
class TechnicianSpec:
    tech_id: str
    skills: frozenset
    shift_end: int          # minute the technician's paid shift ends
    max_overtime: int       # additional minutes available past shift_end


@dataclass
class JobSpec:
    job_id: str
    required_skill: str
    base_duration: int
    priority: str            # "standard" or "urgent"
    deadline: int             # minute by which the job must be COMPLETED
    arrival_time: int         # minute the job becomes visible to the policy
    is_followup: bool = False
    parent_job_id: Optional[str] = None


@dataclass
class TechState:
    tech_id: str
    skills: frozenset
    shift_end: int
    max_overtime: int
    free_since: int = 0
    continuous_work: int = 0
    overtime_used: int = 0
    busy_until: Optional[int] = None
    current_job: Optional[str] = None


@dataclass
class JobState:
    job_id: str
    required_skill: str
    base_duration: int
    priority: str
    deadline: int
    arrival_time: int
    is_followup: bool
    parent_job_id: Optional[str]
    status: str = "not_arrived"   # not_arrived -> pending -> in_progress -> completed
    breached: bool = False
    assigned_tech: Optional[str] = None
    actual_duration: Optional[int] = None


@dataclass(frozen=True)
class TechSnapshot:
    tech_id: str
    skills: frozenset
    continuous_work: int
    shift_end: int
    overtime_used: int
    max_overtime: int


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    required_skill: str
    duration: int          # base duration; the simulator applies the fatigue multiplier itself
    priority: str
    deadline: int
    arrival_time: int
    is_followup: bool


@dataclass(frozen=True)
class SimState:
    current_time: int
    free_technicians: Tuple[TechSnapshot, ...]
    pending_jobs: Tuple[JobSnapshot, ...]


@dataclass
class SimResult:
    total_cost: float
    num_breaches: int
    num_followups_spawned: int
    overtime_minutes_total: int
    completed_jobs: int
    total_jobs: int
    log: List[str] = field(default_factory=list)
    decision_trace: List[List[Tuple[str, str]]] = field(default_factory=list)


PolicyFn = Callable[[SimState], List[Tuple[str, str]]]


def make_replay_policy(trace: List[List[Tuple[str, str]]]) -> PolicyFn:
    """Build a policy function that mechanically replays a recorded decision
    trace instead of computing anything. Used by the trusted verifier stage
    to re-derive a candidate's result without executing any of its code:
    the same deterministic event loop and validity checks in run_simulation
    re-validate every claimed assignment from scratch. If the trace runs out
    (should not happen for a trace recorded from a real run against the same
    scenario) further calls return no assignment."""
    state = {"i": 0}

    def _policy(_state: SimState) -> List[Tuple[str, str]]:
        i = state["i"]
        state["i"] += 1
        if i >= len(trace):
            return []
        return trace[i]

    return _policy


def _make_tech_snapshot(t: TechState) -> TechSnapshot:
    return TechSnapshot(
        tech_id=t.tech_id, skills=t.skills, continuous_work=t.continuous_work,
        shift_end=t.shift_end, overtime_used=t.overtime_used, max_overtime=t.max_overtime,
    )


def _make_job_snapshot(j: JobState) -> JobSnapshot:
    return JobSnapshot(
        job_id=j.job_id, required_skill=j.required_skill, duration=j.base_duration,
        priority=j.priority, deadline=j.deadline, arrival_time=j.arrival_time,
        is_followup=j.is_followup,
    )


def run_simulation(
    technicians: List[TechnicianSpec],
    jobs: List[JobSpec],
    shift_length: int,
    policy_fn: PolicyFn,
    max_events: int = 100_000,
) -> SimResult:
    techs: Dict[str, TechState] = {
        t.tech_id: TechState(tech_id=t.tech_id, skills=t.skills, shift_end=t.shift_end, max_overtime=t.max_overtime)
        for t in technicians
    }
    job_states: Dict[str, JobState] = {
        j.job_id: JobState(
            job_id=j.job_id, required_skill=j.required_skill, base_duration=j.base_duration,
            priority=j.priority, deadline=j.deadline, arrival_time=j.arrival_time,
            is_followup=j.is_followup, parent_job_id=j.parent_job_id,
        )
        for j in jobs
    }

    # event queue: (time, seq, kind, payload)
    events: List[Tuple[int, int, str, str]] = []
    seq = 0
    for j in job_states.values():
        heapq.heappush(events, (j.arrival_time, seq, "arrival", j.job_id))
        seq += 1
    heapq.heappush(events, (0, seq, "start", ""))
    seq += 1
    # Guarantee at least one event fires after every possible deadline, including a
    # follow-up spawned at the last possible moment, so a job with no eligible
    # technician ever isn't silently missed by the breach check.
    horizon = shift_length + FOLLOWUP_SLA_MIN + 1
    heapq.heappush(events, (horizon, seq, "horizon", ""))
    seq += 1

    log: List[str] = []
    decision_trace: List[List[Tuple[str, str]]] = []
    num_followups_spawned = 0
    events_processed = 0

    def eligible_pending_jobs(now: int) -> List[JobState]:
        return [j for j in job_states.values() if j.status == "pending"]

    def eligible_free_techs(now: int) -> List[TechState]:
        return [t for t in techs.values() if t.busy_until is None]

    def check_breach(j: JobState, now: int):
        if not j.breached and j.status in ("pending", "in_progress") and now > j.deadline:
            j.breached = True
            log.append(f"t={now}: BREACH job={j.job_id} priority={j.priority}")
            if j.priority == "urgent" and not j.is_followup:
                followup = JobState(
                    job_id=f"{j.job_id}-followup",
                    required_skill=j.required_skill,
                    base_duration=FOLLOWUP_DURATION_MIN,
                    priority="standard",
                    deadline=now + FOLLOWUP_SLA_MIN,
                    arrival_time=now,
                    is_followup=True,
                    parent_job_id=j.job_id,
                    status="pending",
                )
                job_states[followup.job_id] = followup
                nonlocal num_followups_spawned
                num_followups_spawned += 1
                log.append(f"t={now}: CASCADE spawned {followup.job_id} from {j.job_id}")

    while events and events_processed < max_events:
        now, _, kind, payload = heapq.heappop(events)
        events_processed += 1

        if kind == "arrival":
            j = job_states[payload]
            if j.status == "not_arrived":
                j.status = "pending"

        elif kind == "job_complete":
            tech_id, job_id = payload.split("|", 1)
            t = techs[tech_id]
            j = job_states[job_id]
            j.status = "completed"
            t.busy_until = None
            t.current_job = None
            t.free_since = now
            check_breach(j, now)  # a job completed exactly at/after its deadline still counts if now > deadline

        elif kind == "horizon":
            pass  # forces a final breach-check pass; see push above

        # break detection: any technician free for >= BREAK_THRESHOLD_MIN resets fatigue
        for t in techs.values():
            if t.busy_until is None and now - t.free_since >= BREAK_THRESHOLD_MIN and t.continuous_work > 0:
                t.continuous_work = 0

        # breach detection for all still-outstanding jobs at this timestamp
        for j in list(job_states.values()):
            check_breach(j, now)

        # decision point: any free tech + any pending job -> ask the policy
        free_techs = eligible_free_techs(now)
        pending = eligible_pending_jobs(now)
        if free_techs and pending:
            state = SimState(
                current_time=now,
                free_technicians=tuple(_make_tech_snapshot(t) for t in free_techs),
                pending_jobs=tuple(_make_job_snapshot(j) for j in pending),
            )
            assignments = policy_fn(state)
            decision_trace.append(list(assignments))
            seen_techs = set()
            seen_jobs = set()
            for tech_id, job_id in assignments:
                if tech_id in seen_techs or job_id in seen_jobs:
                    continue  # a tech or job used twice in one decision is silently ignored beyond the first
                t = techs.get(tech_id)
                j = job_states.get(job_id)
                if t is None or j is None or t.busy_until is not None or j.status != "pending":
                    continue
                if j.required_skill not in t.skills:
                    continue
                duration = j.base_duration
                if t.continuous_work >= FATIGUE_THRESHOLD_MIN:
                    duration = int(round(j.base_duration * FATIGUE_MULTIPLIER))
                finish_time = now + duration
                shift_limit = t.shift_end + t.max_overtime
                if finish_time > shift_limit:
                    continue  # cannot start a job that would run past the technician's overtime cap
                overtime_for_this_job = max(0, finish_time - max(now, t.shift_end))
                t.overtime_used += overtime_for_this_job
                t.busy_until = finish_time
                t.current_job = job_id
                t.continuous_work += duration
                j.status = "in_progress"
                j.assigned_tech = tech_id
                j.actual_duration = duration
                seen_techs.add(tech_id)
                seen_jobs.add(job_id)
                heapq.heappush(events, (finish_time, seq, "job_complete", f"{tech_id}|{job_id}"))
                seq += 1
                log.append(f"t={now}: ASSIGN {tech_id} -> {job_id} (duration={duration}, finish={finish_time})")

    # final accounting
    num_breaches = sum(1 for j in job_states.values() if j.breached)
    completed_jobs = sum(1 for j in job_states.values() if j.status == "completed")
    total_jobs = len(job_states)
    overtime_minutes_total = sum(t.overtime_used for t in techs.values())
    total_cost = (
        overtime_minutes_total * OVERTIME_RATE
        + num_breaches * BREACH_PENALTY
        + num_followups_spawned * CASCADE_COST
    )

    return SimResult(
        total_cost=total_cost,
        num_breaches=num_breaches,
        num_followups_spawned=num_followups_spawned,
        overtime_minutes_total=overtime_minutes_total,
        completed_jobs=completed_jobs,
        total_jobs=total_jobs,
        log=log,
        decision_trace=decision_trace,
    )
