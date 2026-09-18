#!/usr/bin/env python3
"""
Structural scenario generator for the field-service-dispatch task.

This is a build-time tool (not shipped to the agent or the verifier). It
exists so every scenario -- visible sample or sealed held-out -- can be
given a genuinely distinct structural *shape* (arrival cadence, technician
pool size, skill-scarcity ratio) instead of all four scenarios sharing one
template, which is what let a policy tuned/benchmarked against a
self-generated "looks like the samples" dataset transfer almost perfectly
to the real held-out grading scenario.

A "profile" fully describes one scenario's shape. Two profiles differ in
structure when their arrival cadence, technician-pool size, or per-skill
supply/demand ratio meaningfully differs -- not just their random seed.
"""
from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SkillSpec:
    name: str
    n_techs: int          # how many technicians carry this skill (supply)
    demand_weight: float  # relative weight when sampling a job's required_skill


@dataclass
class WaveSpec:
    time: int
    n_jobs: int


@dataclass
class ScenarioProfile:
    name: str
    seed: int
    shift_length: int
    n_techs: int
    skills: List[SkillSpec]              # excludes "general", added automatically
    waves: List[WaveSpec]
    duration_range: Tuple[int, int] = (30, 60)
    urgent_prob: float = 0.28
    urgent_slack_range: Tuple[int, int] = (10, 45)       # minutes of slack past duration, urgent jobs
    standard_slack_range: Tuple[int, int] = (40, 130)    # minutes of slack past duration, standard jobs
    shift_end_jitter: Tuple[int, int] = (0, 0)           # (min, max) subtracted from shift_length
    max_overtime_range: Tuple[int, int] = (60, 120)


def _assign_tech_skills(rng: random.Random, n_techs: int, skills: List[SkillSpec]) -> List[frozenset]:
    """Every technician gets 'general' plus a subset of named skills, honoring
    each skill's exact supply count (n_techs field)."""
    tech_skillsets: List[set] = [{"general"} for _ in range(n_techs)]
    for sk in skills:
        assert sk.n_techs <= n_techs, f"skill {sk.name} wants {sk.n_techs} techs but pool is {n_techs}"
        holders = rng.sample(range(n_techs), sk.n_techs)
        for h in holders:
            tech_skillsets[h].add(sk.name)
    return [frozenset(s) for s in tech_skillsets]


def generate_scenario(profile: ScenarioProfile):
    rng = random.Random(profile.seed)

    tech_skills = _assign_tech_skills(rng, profile.n_techs, profile.skills)
    tech_rows = []
    for i, skills in enumerate(tech_skills):
        jitter = rng.randint(*profile.shift_end_jitter) if profile.shift_end_jitter != (0, 0) else 0
        shift_end = profile.shift_length - jitter
        max_ot = rng.randint(*profile.max_overtime_range)
        tech_rows.append({
            "tech_id": f"T{i+1}",
            "skills": ";".join(sorted(skills)),
            "shift_end": shift_end,
            "max_overtime": max_ot,
        })

    skill_names = [sk.name for sk in profile.skills] + ["general"]
    weights = [sk.demand_weight for sk in profile.skills] + [
        max(0.05, 1.0 - sum(sk.demand_weight for sk in profile.skills) / max(1, len(profile.skills)))
    ]

    job_rows = []
    jid = 1
    for wave in profile.waves:
        for _ in range(wave.n_jobs):
            skill = rng.choices(skill_names, weights=weights, k=1)[0]
            duration = rng.randint(*profile.duration_range)
            urgent = rng.random() < profile.urgent_prob
            slack = rng.randint(*profile.urgent_slack_range) if urgent else rng.randint(*profile.standard_slack_range)
            deadline = wave.time + duration + slack
            job_rows.append({
                "job_id": f"J{jid}",
                "required_skill": skill,
                "base_duration": duration,
                "priority": "urgent" if urgent else "standard",
                "deadline": deadline,
                "arrival_time": wave.time,
            })
            jid += 1

    return tech_rows, job_rows, profile.shift_length


def inject_swap_gadget(tech_rows, job_rows, gadget_id, shift_length, params, next_job_num, next_tech_num):
    """Appends one guaranteed 'swap' pair: two technicians whose shift_end
    is split very differently even though their total overtime headroom is
    similar, plus a short and a long job, all sharing one skill that only
    these two technicians have (so nothing else in the scenario can dilute
    or interfere with it). The pairing that minimizes cost is genuinely a
    SWAP (long job to the late-shift_end technician, short job to the
    early-shift_end one) -- reacting to whichever job happens to arrive
    first and greedily picking its pairwise-cheapest technician commits
    the wrong one, because that technician looks locally fine for the
    first job while quietly being the only one who can absorb the second
    job's overtime cheaply. `params` supplies verified (se_a, mo_a, se_b,
    mo_b, d1, d2, urgent1, urgent2) that make this failure large and
    unambiguous (not a near-tie), found by direct search against the real
    cost formula -- see dev/find_swap_gadget.py.
    """
    skill = f"gadget{gadget_id}"
    tA, tB = f"G{next_tech_num}A", f"G{next_tech_num}B"
    tech_rows.append({
        "tech_id": tA, "skills": skill, "shift_end": params["se_a"], "max_overtime": params["mo_a"],
    })
    tech_rows.append({
        "tech_id": tB, "skills": skill, "shift_end": params["se_b"], "max_overtime": params["mo_b"],
    })
    safe_deadline = shift_length + params["mo_a"] + params["mo_b"] + max(params["d1"], params["d2"])
    j1, j2 = f"G{next_job_num}a", f"G{next_job_num}b"
    job_rows.append({
        "job_id": j1, "required_skill": skill, "base_duration": params["d1"],
        "priority": "urgent" if params["urgent1"] else "standard",
        "deadline": safe_deadline, "arrival_time": 0,
    })
    job_rows.append({
        "job_id": j2, "required_skill": skill, "base_duration": params["d2"],
        "priority": "urgent" if params["urgent2"] else "standard",
        "deadline": safe_deadline, "arrival_time": 0,
    })


def write_scenario(out_dir: str, tech_rows, job_rows, shift_length: int):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "technicians.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tech_id", "skills", "shift_end", "max_overtime"])
        w.writeheader()
        w.writerows(tech_rows)
    with open(os.path.join(out_dir, "jobs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["job_id", "required_skill", "base_duration", "priority", "deadline", "arrival_time"])
        w.writeheader()
        w.writerows(job_rows)
    with open(os.path.join(out_dir, "config.json"), "w") as f:
        json.dump({"shift_length": shift_length}, f, indent=2)


if __name__ == "__main__":
    import sys
    print("This module is imported by build_scenarios.py; it has no standalone CLI.", file=sys.stderr)
    sys.exit(1)
