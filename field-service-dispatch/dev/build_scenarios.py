#!/usr/bin/env python3
"""Builds all five scenarios (3 visible samples, 2 sealed held-out) from
distinct structural profiles and writes them to environment/data/ and
tests/sealed/inputs/. Re-run this any time a profile changes; it is
deterministic (fixed seeds) so re-running without changes reproduces
byte-identical output.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from scenario_gen import ScenarioProfile, SkillSpec, WaveSpec, generate_scenario, write_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROFILES = {
    # -------- visible development samples --------
    # sample_45: tight, irregular bursts; moderate single-skill scarcity.
    "environment/data/sample_45": ScenarioProfile(
        name="sample_45", seed=4501, shift_length=420, n_techs=5,
        skills=[
            SkillSpec("A", n_techs=1, demand_weight=0.32),
            SkillSpec("B", n_techs=2, demand_weight=0.28),
            SkillSpec("C", n_techs=3, demand_weight=0.18),
        ],
        waves=[WaveSpec(0, 6), WaveSpec(50, 5), WaveSpec(130, 6), WaveSpec(260, 5), WaveSpec(340, 5)],
        duration_range=(30, 65), urgent_prob=0.33,
        urgent_slack_range=(15, 45), standard_slack_range=(40, 120),
    ),
    # sample_87: smooth trickle, large technician pool, mild scarcity.
    "environment/data/sample_87": ScenarioProfile(
        name="sample_87", seed=8701, shift_length=480, n_techs=8,
        skills=[
            SkillSpec("A", n_techs=2, demand_weight=0.22),
            SkillSpec("B", n_techs=3, demand_weight=0.24),
            SkillSpec("C", n_techs=2, demand_weight=0.18),
        ],
        waves=[WaveSpec(t, n) for t, n in [
            (0, 4), (40, 4), (80, 3), (120, 4), (170, 3), (220, 4), (280, 3), (330, 4), (390, 3),
        ]],
        duration_range=(25, 55), urgent_prob=0.26,
        urgent_slack_range=(15, 45), standard_slack_range=(40, 120),
    ),
    # sample_150: front-loaded, then a long quiet gap, then a final push;
    # severe single-skill scarcity with high demand for it.
    "environment/data/sample_150": ScenarioProfile(
        name="sample_150", seed=15001, shift_length=450, n_techs=6,
        skills=[
            SkillSpec("A", n_techs=1, demand_weight=0.38),
            SkillSpec("B", n_techs=4, demand_weight=0.22),
        ],
        waves=[WaveSpec(0, 9), WaveSpec(60, 6), WaveSpec(90, 5), WaveSpec(300, 8)],
        duration_range=(30, 70), urgent_prob=0.30,
        urgent_slack_range=(15, 45), standard_slack_range=(40, 120),
    ),
    # -------- sealed held-out grading scenarios --------
    # held_out_1: irregular 7-wave cadence not matching any visible sample's
    # wave count or spacing; moderate, two-skill scarcity.
    "tests/sealed/inputs/held_out_1": ScenarioProfile(
        name="held_out_1", seed=911007, shift_length=460, n_techs=6,
        skills=[
            SkillSpec("A", n_techs=1, demand_weight=0.30),
            SkillSpec("B", n_techs=2, demand_weight=0.22),
            SkillSpec("C", n_techs=1, demand_weight=0.20),
        ],
        waves=[WaveSpec(t, n) for t, n in [
            (0, 4), (30, 3), (70, 4), (120, 3), (180, 4), (230, 3), (290, 4), (350, 3),
        ]],
        duration_range=(30, 60), urgent_prob=0.34,
        urgent_slack_range=(15, 45), standard_slack_range=(40, 120),
    ),
    # held_out_2: small technician pool, severe single-skill scarcity with
    # very high relative demand, higher urgency mix -- a different
    # supply/demand regime than every visible sample.
    "tests/sealed/inputs/held_out_2": ScenarioProfile(
        name="held_out_2", seed=922002, shift_length=420, n_techs=4,
        skills=[
            SkillSpec("A", n_techs=1, demand_weight=0.46),
            SkillSpec("B", n_techs=2, demand_weight=0.24),
        ],
        waves=[WaveSpec(t, n) for t, n in [
            (0, 6), (80, 5), (160, 6), (300, 5), (380, 4),
        ]],
        duration_range=(30, 65), urgent_prob=0.40,
        urgent_slack_range=(15, 45), standard_slack_range=(40, 120),
    ),
}


def main():
    for rel_path, profile in PROFILES.items():
        tech_rows, job_rows, shift_length = generate_scenario(profile)
        out_dir = os.path.join(ROOT, rel_path)
        write_scenario(out_dir, tech_rows, job_rows, shift_length)
        print(f"wrote {rel_path}: {len(tech_rows)} techs, {len(job_rows)} jobs, shift_length={shift_length}")


if __name__ == "__main__":
    main()
