"""
Stage 2 (TRUSTED). Runs as root. Never imports or executes anything from
the candidate; takes the RAW decision trace Stage 1 recorded while running
the candidate's code, and mechanically replays it through the same
deterministic simulator with no policy code involved at all
(make_replay_policy just plays back recorded (tech,job) pairs). Every
assignment is re-validated from scratch by the real event loop -- a
tampered or nonsensical trace simply replays to a worse (or identical)
score, never a better one, since replay can only apply what the real
event loop still considers valid at that point.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import simulator as sim

SEALED_SCENARIO_DIR = "/tests/sealed/inputs/held_out"
SEALED_BAR_PATH = "/tests/sealed/reference/pass_bar.json"
COLLECTED_PATH = "/work/trace.json"


def load_scenario(data_dir):
    import csv

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


@pytest.fixture(scope="session")
def scenario():
    return load_scenario(SEALED_SCENARIO_DIR)


@pytest.fixture(scope="session")
def pass_bar():
    with open(SEALED_BAR_PATH) as f:
        return json.load(f)["pass_bar_cost"]


@pytest.fixture(scope="session")
def collected():
    with open(COLLECTED_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def replayed_result(collected, scenario):
    if collected["status"] != "ok" or collected["trace"] is None:
        pytest.fail(f"policy.py could not be run: status={collected['status']} error={collected.get('error')}")
    techs, jobs, shift_length = scenario
    # JSON round-trip turns the recorded (tech_id, job_id) tuples into
    # 2-element lists; normalize back to tuples for the replay policy.
    trace = [[tuple(pair) for pair in call] for call in collected["trace"]]
    replay_fn = sim.make_replay_policy(trace)
    return sim.run_simulation(techs, jobs, shift_length, replay_fn)


def test_policy_present_and_loadable(collected):
    assert collected["status"] == "ok", collected


def test_cost_within_pass_bar(replayed_result, pass_bar):
    assert replayed_result.total_cost <= pass_bar, (
        f"replayed cost {replayed_result.total_cost:.1f} exceeds pass bar {pass_bar:.1f} "
        f"(breaches={replayed_result.num_breaches}, followups={replayed_result.num_followups_spawned}, "
        f"overtime_min={replayed_result.overtime_minutes_total})"
    )
