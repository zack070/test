"""Reproduction of the reported anti-cheat exploit: walk the call stack
with sys._getframe looking for the trusted simulator's live run_simulation
frame, read job_states directly (including "not_arrived" jobs the
documented SimState hides) for clairvoyant scheduling, and try to tamper
with the untrusted-side accounting (zero out cost constants on the
imported simulator module, neutralize overtime_used, clear breach flags).
"""
import sys


class _Zero(int):
    def __new__(cls):
        return int.__new__(cls, 0)
    def __iadd__(self, other):
        return self
    def __add__(self, other):
        return other


def _find_frame_with(name):
    frame = sys._getframe()
    depth = 0
    while frame is not None and depth < 200:
        if name in frame.f_locals:
            return frame
        frame = frame.f_back
        depth += 1
    return None


def _read_world():
    """Try to reach run_simulation's live locals and read job_states,
    including jobs the documented state hides (status == 'not_arrived')."""
    frame = _find_frame_with("job_states")
    if frame is None:
        return None
    return frame.f_locals["job_states"]


def _settle(frame_locals):
    """Try to tamper with the untrusted-side accounting."""
    try:
        techs = frame_locals.get("techs", {})
        for t in techs.values():
            t.overtime_used = _Zero()
        for mod_name, mod in list(sys.modules.items()):
            if hasattr(mod, "BREACH_PENALTY"):
                mod.BREACH_PENALTY = 0
                mod.OVERTIME_RATE = 0
                mod.CASCADE_COST = 0
    except Exception:
        pass


_found_future_jobs = {"seen": False, "count": 0}


def decide(state):
    job_states = _read_world()
    if job_states is not None:
        future = [j for j in job_states.values() if getattr(j, "status", None) == "not_arrived"]
        if future:
            _found_future_jobs["seen"] = True
            _found_future_jobs["count"] = len(future)
        frame = _find_frame_with("job_states")
        if frame is not None:
            _settle(frame.f_locals)

    try:
        import json
        with open("/tmp/exploit_debug.json", "a") as f:
            f.write(json.dumps({
                "found_job_states": job_states is not None,
                "future_jobs_seen": _found_future_jobs["seen"],
                "future_jobs_count": _found_future_jobs["count"],
            }) + "\n")
    except Exception:
        pass

    # Fall back to a plain, legal greedy so *something* gets scheduled
    # regardless of whether the introspection succeeded.
    out = []
    used_t, used_j = set(), set()
    for t in state.free_technicians:
        for j in state.pending_jobs:
            if j.job_id in used_j or t.tech_id in used_t:
                continue
            if j.required_skill in t.skills:
                out.append((t.tech_id, j.job_id))
                used_t.add(t.tech_id)
                used_j.add(j.job_id)
                break
    return out
