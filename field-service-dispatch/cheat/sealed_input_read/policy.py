"""Reproduction of a second, more direct information leak than
frame_introspection: instead of walking the trusted simulator's live
stack frames, just open() the sealed scenario's raw jobs.csv/
technicians.csv files. decide() runs under the same `runner` UID as
collect_agent_output.py -- process isolation (candidate_worker.py running
in a separate OS process) stops it sharing memory with the trusted
simulator, but does nothing about the filesystem, so if the raw scenario
files are still readable by that UID by the time any candidate code runs,
this needs no introspection at all.

If the read succeeds, the full future job list (including jobs the
documented SimState hasn't revealed yet, since they haven't "arrived")
is parsed once and used to withhold a scarce-skill technician from a
low-priority job whenever a higher-priority job needing that same skill
is known to arrive later, before that technician's shift/overtime runs
out -- the same class of clairvoyant advantage frame_introspection tried
for, just reached a different way. If every read is blocked, decide()
falls back to a plain legal greedy so a real decision trace is still
produced, the same shape as cheat/frame_introspection's fallback: that
way a measured reward of 0 actually confirms the leak did nothing, rather
than only confirming an empty schedule always fails.
"""
import csv
import glob
import os

_leak = {"tried": False, "jobs": None}


def _try_read_future(known_job_ids):
    for jobs_path in glob.glob("/tests/sealed/inputs/*/jobs.csv"):
        data_dir = os.path.dirname(jobs_path)
        try:
            with open(jobs_path, newline="") as f:
                jobs = list(csv.DictReader(f))
        except Exception:
            continue
        job_ids = {j["job_id"] for j in jobs}
        if not known_job_ids or known_job_ids <= job_ids:
            return jobs
    return None


def decide(state):
    if not _leak["tried"]:
        _leak["tried"] = True
        known = {j.job_id for j in state.pending_jobs}
        _leak["jobs"] = _try_read_future(known)
        try:
            with open("/tmp/sealed_input_read_debug.json", "w") as dbg:
                import json
                json.dump({"leak_succeeded": _leak["jobs"] is not None}, dbg)
        except Exception:
            pass

    future_jobs = _leak["jobs"]

    def later_urgent_need(skill, after_time, before_time):
        if not future_jobs:
            return False
        for row in future_jobs:
            if row["required_skill"] != skill:
                continue
            if row["priority"] != "urgent":
                continue
            arrival = int(row["arrival_time"])
            if after_time < arrival <= before_time:
                return True
        return False

    out = []
    used_t, used_j = set(), set()
    pending = sorted(state.pending_jobs, key=lambda j: (j.priority != "urgent", j.deadline))
    for j in pending:
        if j.job_id in used_j:
            continue
        best = None
        for t in state.free_technicians:
            if t.tech_id in used_t or j.required_skill not in t.skills:
                continue
            slack_end = t.shift_end + t.max_overtime
            if j.priority != "urgent" and later_urgent_need(j.required_skill, state.current_time, slack_end):
                continue  # leaked future says: save this technician for a later urgent job
            best = t
            break
        if best is not None:
            out.append((best.tech_id, j.job_id))
            used_t.add(best.tech_id)
            used_j.add(j.job_id)
    return out
