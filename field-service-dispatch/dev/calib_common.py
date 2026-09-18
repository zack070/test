"""Shared loading + baseline-policy helpers for calibration scripts.
Build-time only; never shipped to the agent or the verifier."""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "environment", "sim"))
import simulator as sim  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "solution"))
from policy import _pairing_cost  # noqa: E402  (reuse the shipped reference's real cost formula)


def load_scenario(data_dir):
    def read_csv(name):
        with open(os.path.join(data_dir, name), newline="") as f:
            return list(csv.DictReader(f))

    techs = [
        sim.TechnicianSpec(
            tech_id=r["tech_id"], skills=frozenset(r["skills"].split(";")),
            shift_end=int(r["shift_end"]), max_overtime=int(r["max_overtime"]),
        )
        for r in read_csv("technicians.csv")
    ]
    jobs = [
        sim.JobSpec(
            job_id=r["job_id"], required_skill=r["required_skill"], base_duration=int(r["base_duration"]),
            priority=r["priority"], deadline=int(r["deadline"]), arrival_time=int(r["arrival_time"]),
        )
        for r in read_csv("jobs.csv")
    ]
    with open(os.path.join(data_dir, "config.json")) as f:
        cfg = json.load(f)
    return techs, jobs, cfg["shift_length"]


def run(techs, jobs, shift_length, policy_fn):
    return sim.run_simulation(techs, jobs, shift_length, policy_fn)


# ---------------------------------------------------------------------------
# Naive / greedy baseline policies, used only for calibration (never shipped).
# ---------------------------------------------------------------------------

def fifo_policy(state):
    """Assign in arrival order to the first eligible free technician."""
    jobs = sorted(state.pending_jobs, key=lambda j: (j.arrival_time, j.job_id))
    used = set()
    out = []
    for j in jobs:
        for t in state.free_technicians:
            if t.tech_id in used:
                continue
            if j.required_skill in t.skills:
                out.append((t.tech_id, j.job_id))
                used.add(t.tech_id)
                break
    return out


def edf_no_awareness_policy(state):
    """Earliest-deadline-first, first eligible free technician, no fatigue/
    scarcity/overtime awareness at all."""
    jobs = sorted(state.pending_jobs, key=lambda j: (j.deadline, j.job_id))
    used = set()
    out = []
    for j in jobs:
        for t in state.free_technicians:
            if t.tech_id in used:
                continue
            if j.required_skill in t.skills:
                out.append((t.tech_id, j.job_id))
                used.add(t.tech_id)
                break
    return out


JOB_ORDER_RULES = {
    "earliest_deadline": lambda j, now: (j.deadline, j.job_id),
    "urgent_first": lambda j, now: (0 if j.priority == "urgent" else 1, j.deadline, j.job_id),
    "least_slack": lambda j, now: (j.deadline - now, j.job_id),
    "scarcest_skill_first": None,  # needs tech context, handled specially
}

TIE_BREAK_RULES = {
    "first_eligible": None,
    "least_fatigued": lambda t: (t.continuous_work, t.tech_id),
    "fewest_total_skills": lambda t: (len(t.skills), t.tech_id),
    "most_remaining_capacity": lambda t: (-(t.shift_end + t.max_overtime), t.tech_id),
}


def _would_finish(job, tech, now):
    """Finish time for tech taking job right now, accounting for the
    fatigue multiplier -- mirrors the simulator's own rule exactly."""
    dur = job.duration
    if tech.continuous_work >= sim.FATIGUE_THRESHOLD_MIN:
        dur = int(round(dur * sim.FATIGUE_MULTIPLIER))
    return now + dur


def _is_savable(job, tech, now):
    """Would this pairing actually meet the job's deadline (and stay within
    the technician's overtime cap)? A pairing that can't save the job buys
    nothing -- the breach fires at the same wall-clock moment whether or
    not anyone was assigned -- so a policy that assigns it anyway is
    strictly wasting that technician's time."""
    finish = _would_finish(job, tech, now)
    return finish <= job.deadline and finish <= tech.shift_end + tech.max_overtime


def make_fixed_priority_greedy(job_order_name, tie_break_name, feasibility_filtered=False):
    def policy(state):
        now = state.current_time
        techs_all = list(state.free_technicians)
        jobs_all = list(state.pending_jobs)
        if job_order_name == "scarcest_skill_first":
            supply = {}
            for t in techs_all:
                for s in t.skills:
                    supply[s] = supply.get(s, 0) + 1
            jobs = sorted(jobs_all, key=lambda j: (supply.get(j.required_skill, 0), j.deadline, j.job_id))
        else:
            jobs = sorted(jobs_all, key=lambda j: JOB_ORDER_RULES[job_order_name](j, now))

        used = set()
        out = []
        tie_key = TIE_BREAK_RULES[tie_break_name]
        for j in jobs:
            eligible = [t for t in techs_all if t.tech_id not in used and j.required_skill in t.skills]
            if feasibility_filtered:
                eligible = [t for t in eligible if _is_savable(j, t, now)]
            if not eligible:
                continue
            if tie_key is not None:
                eligible.sort(key=tie_key)
            chosen = eligible[0]
            out.append((chosen.tech_id, j.job_id))
            used.add(chosen.tech_id)
        return out
    return policy


def all_fixed_priority_probes():
    probes = {}
    for jo in JOB_ORDER_RULES:
        for tb in TIE_BREAK_RULES:
            probes[f"{jo}__{tb}"] = make_fixed_priority_greedy(jo, tb, feasibility_filtered=False)
            probes[f"{jo}__{tb}__feasible"] = make_fixed_priority_greedy(jo, tb, feasibility_filtered=True)
    return probes


def make_t0_deferring_greedy(job_order_name, tie_break_name, feasibility_filtered=True):
    """Same t=0 'wait until the pending set stops growing' trick as the
    real reference, then applies a plain fixed-priority greedy (not a
    joint solve) to the accumulated batch. Tests whether deferral ALONE
    (without genuinely solving the batch jointly) is enough to match the
    reference -- it must not be, or the difficulty isn't really about
    joint reasoning. State is closure-local (fresh per call to this
    factory) so it never leaks between probes or scenario runs."""
    inner = make_fixed_priority_greedy(job_order_name, tie_break_name, feasibility_filtered)
    state_box = {"last_pending_count": -1, "settled": False}

    def policy(state):
        if state.current_time == 0 and not state_box["settled"]:
            if len(state.pending_jobs) > state_box["last_pending_count"]:
                state_box["last_pending_count"] = len(state.pending_jobs)
                return []
            state_box["settled"] = True
        return inner(state)

    return policy


def greedy_pair_picker_real_cost_policy(state):
    """At each decision point, repeatedly picks the single globally
    cheapest (tech, job) pair by the shipped reference's own per-pairing
    cost formula (already feasibility-aware: infeasible/unsavable pairs
    return None), assigns it, removes both, and repeats -- a proper
    greedy matching using real costs, still one pair at a time rather than
    jointly optimizing the whole batch."""
    all_techs = list(state.free_technicians)
    all_jobs = list(state.pending_jobs)
    used_t, used_j = set(), set()
    out = []
    while True:
        best = None
        best_cost = None
        for t in all_techs:
            if t.tech_id in used_t:
                continue
            for j in all_jobs:
                if j.job_id in used_j:
                    continue
                cost = _pairing_cost(j, t, state.current_time, all_techs)
                if cost is None:
                    continue
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best = (t.tech_id, j.job_id)
        if best is None:
            break
        out.append(best)
        used_t.add(best[0])
        used_j.add(best[1])
    return out


def _mega_greedy(state, feasibility_filtered):
    """Stacks every tie-break trick into one fixed-priority pass: urgent
    first, then earliest deadline, breaking ties by least-fatigued, then
    fewest-total-skills, then most-remaining-capacity."""
    now = state.current_time
    techs_all = list(state.free_technicians)
    jobs_all = sorted(
        state.pending_jobs,
        key=lambda j: (0 if j.priority == "urgent" else 1, j.deadline, j.job_id),
    )
    used = set()
    out = []
    for j in jobs_all:
        eligible = [t for t in techs_all if t.tech_id not in used and j.required_skill in t.skills]
        if feasibility_filtered:
            eligible = [t for t in eligible if _is_savable(j, t, now)]
        if not eligible:
            continue
        eligible.sort(key=lambda t: (t.continuous_work, len(t.skills), -(t.shift_end + t.max_overtime), t.tech_id))
        chosen = eligible[0]
        out.append((chosen.tech_id, j.job_id))
        used.add(chosen.tech_id)
    return out


def mega_greedy_policy(state):
    return _mega_greedy(state, feasibility_filtered=False)


def mega_greedy_feasible_policy(state):
    return _mega_greedy(state, feasibility_filtered=True)
