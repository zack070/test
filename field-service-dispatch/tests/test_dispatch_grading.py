"""
Stage 2 (TRUSTED). Runs as root. Never imports or executes anything from
the candidate; takes the RAW decision traces Stage 1 recorded while running
the candidate's code, and mechanically replays each through the same
deterministic simulator with no policy code involved at all
(make_replay_policy just plays back recorded (tech,job) pairs). Every
assignment is re-validated from scratch by the real event loop -- a
tampered or nonsensical trace simply replays to a worse (or identical)
score, never a better one, since replay can only apply what the real
event loop still considers valid at that point.

There are two sealed held-out scenarios, deliberately different in
structure (technician-pool size, skill-scarcity ratio, arrival cadence).
The candidate must clear BOTH scenarios' own calibrated pass bar
individually -- not an average -- so a policy tuned to only one shape
cannot coast on the other.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import simulator as sim

SEALED_SCENARIO_DIRS = {
    "held_out_1": "/tests/sealed/inputs/held_out_1",
    "held_out_2": "/tests/sealed/inputs/held_out_2",
}
SEALED_BAR_PATH = "/tests/sealed/reference/pass_bar.json"
COLLECTED_PATH = "/work/trace.json"

SCENARIO_NAMES = sorted(SEALED_SCENARIO_DIRS)


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
def scenarios():
    return {name: load_scenario(path) for name, path in SEALED_SCENARIO_DIRS.items()}


@pytest.fixture(scope="session")
def pass_bars():
    with open(SEALED_BAR_PATH) as f:
        data = json.load(f)["scenarios"]
    return {name: data[name]["pass_bar_cost"] for name in SCENARIO_NAMES}


@pytest.fixture(scope="session")
def collected():
    with open(COLLECTED_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def replayed_results(collected, scenarios):
    if collected["status"] != "ok":
        pytest.fail(f"policy.py could not be run: status={collected['status']} error={collected.get('error')}")
    results = {}
    for name in SCENARIO_NAMES:
        trace_raw = collected["traces"].get(name)
        if trace_raw is None:
            pytest.fail(f"no decision trace recorded for scenario '{name}': status={collected['status']} error={collected.get('error')}")
        # JSON round-trip turns the recorded (tech_id, job_id) tuples into
        # 2-element lists; normalize back to tuples for the replay policy.
        trace = [[tuple(pair) for pair in call] for call in trace_raw]
        replay_fn = sim.make_replay_policy(trace)
        techs, jobs, shift_length = scenarios[name]
        results[name] = sim.run_simulation(techs, jobs, shift_length, replay_fn)
    return results


def test_policy_present_and_loadable(collected):
    assert collected["status"] == "ok", collected


@pytest.mark.parametrize("scenario_name", SCENARIO_NAMES)
def test_cost_within_pass_bar(scenario_name, replayed_results, pass_bars):
    result = replayed_results[scenario_name]
    bar = pass_bars[scenario_name]
    assert result.total_cost <= bar, (
        f"[{scenario_name}] replayed cost {result.total_cost:.1f} exceeds pass bar {bar:.1f} "
        f"(breaches={result.num_breaches}, followups={result.num_followups_spawned}, "
        f"overtime_min={result.overtime_minutes_total})"
    )
