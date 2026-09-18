"""Shared loading + baseline-policy helpers for calibration scripts.
Build-time only; never shipped to the agent or the verifier."""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "environment", "sim"))
import simulator as sim  # noqa: E402


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
    "earliest_deadline": lambda j: (j.deadline, j.job_id),
    "urgent_first": lambda j: (0 if j.priority == "urgent" else 1, j.deadline, j.job_id),
    "scarcest_skill_first": None,  # needs tech context, handled specially
}

TIE_BREAK_RULES = {
    "first_eligible": None,
    "least_fatigued": lambda t: (t.continuous_work, t.tech_id),
    "fewest_total_skills": lambda t: (len(t.skills), t.tech_id),
    "most_remaining_capacity": lambda t: (-(t.shift_end + t.max_overtime), t.tech_id),
}


def make_fixed_priority_greedy(job_order_name, tie_break_name):
    def policy(state):
        techs_all = list(state.free_technicians)
        jobs_all = list(state.pending_jobs)
        if job_order_name == "scarcest_skill_first":
            supply = {}
            for t in techs_all:
                for s in t.skills:
                    supply[s] = supply.get(s, 0) + 1
            jobs = sorted(jobs_all, key=lambda j: (supply.get(j.required_skill, 0), j.deadline, j.job_id))
        else:
            jobs = sorted(jobs_all, key=JOB_ORDER_RULES[job_order_name])

        used = set()
        out = []
        tie_key = TIE_BREAK_RULES[tie_break_name]
        for j in jobs:
            eligible = [t for t in techs_all if t.tech_id not in used and j.required_skill in t.skills]
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
            probes[f"{jo}__{tb}"] = make_fixed_priority_greedy(jo, tb)
    return probes


def mega_greedy_policy(state):
    """Stacks every tie-break trick into one fixed-priority pass: urgent
    first, then earliest deadline, breaking ties by least-fatigued, then
    fewest-total-skills, then most-remaining-capacity."""
    techs_all = list(state.free_technicians)
    jobs_all = sorted(
        state.pending_jobs,
        key=lambda j: (0 if j.priority == "urgent" else 1, j.deadline, j.job_id),
    )
    used = set()
    out = []
    for j in jobs_all:
        eligible = [t for t in techs_all if t.tech_id not in used and j.required_skill in t.skills]
        if not eligible:
            continue
        eligible.sort(key=lambda t: (t.continuous_work, len(t.skills), -(t.shift_end + t.max_overtime), t.tech_id))
        chosen = eligible[0]
        out.append((chosen.tech_id, j.job_id))
        used.add(chosen.tech_id)
    return out
