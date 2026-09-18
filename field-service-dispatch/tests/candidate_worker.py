"""
Runs ONLY the candidate's decide() function, in its own OS process,
spawned fresh (multiprocessing "spawn" context, never "fork") so it never
inherits any of the trusted simulator process's memory. It communicates
with that process exclusively through two queues carrying plain
JSON-encoded strings -- never pickled objects, so nothing this process
sends back can trigger code execution on the far end by shaping a
malicious pickle payload, and nothing beyond the literal SimState fields
below is ever transmitted to it in the first place.

This exists because decide() used to run as a plain in-process function
call from inside the trusted simulator's own event loop (collect_agent_
output.py called sim.run_simulation(..., decide) directly). That let a
submitted policy use ordinary Python introspection (sys._getframe walking
the call stack up into run_simulation's live locals, or equivalently
gc.get_objects()) to read the simulator's real internal state directly --
including jobs still marked "not_arrived" that the documented SimState
snapshot deliberately withholds -- and use that future knowledge to make
suspiciously well-informed (but individually still "legal") assignments.
Every individual assignment stayed valid at the moment it was returned,
so the trusted replay in Stage 2 (which only re-validates legality) never
caught it; the unfairness was entirely in what information decide() was
never supposed to have, not in anything a legality check can see.

Process isolation closes this structurally rather than by chasing
specific introspection APIs: sys._getframe (or gc, or any other same-
process trick) in a genuinely separate OS process can only ever see that
process's own call stack and heap, which after the fix contains nothing
but the JSON payloads explicitly sent to it -- current_time, the free
technicians, and the pending jobs, exactly what the documented SimState
exposes and nothing else. There is no live run_simulation frame to walk
to, because run_simulation never runs in this process at all.
"""
import importlib.util
import json
import queue
import sys


def _tech_to_dict(t):
    return {
        "tech_id": t.tech_id, "skills": sorted(t.skills), "continuous_work": t.continuous_work,
        "shift_end": t.shift_end, "overtime_used": t.overtime_used, "max_overtime": t.max_overtime,
    }


def _job_to_dict(j):
    return {
        "job_id": j.job_id, "required_skill": j.required_skill, "duration": j.duration,
        "priority": j.priority, "deadline": j.deadline, "arrival_time": j.arrival_time,
        "is_followup": j.is_followup,
    }


def run_worker(artifact_path, sim_path, in_queue, out_queue):
    try:
        # Modules must be registered in sys.modules before exec_module():
        # dataclasses (which simulator.py uses) looks itself up there by
        # module name internally, and an unregistered module makes that
        # lookup return None and crash -- unrelated to anything candidate
        # code does, so it must not be left to surprise a legitimate
        # policy that happens to use dataclasses too.
        spec = importlib.util.spec_from_file_location("candidate_worker_simulator", sim_path)
        sim = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = sim
        spec.loader.exec_module(sim)

        pspec = importlib.util.spec_from_file_location("candidate_policy", artifact_path)
        policy = importlib.util.module_from_spec(pspec)
        sys.modules[pspec.name] = policy
        pspec.loader.exec_module(policy)
        decide = getattr(policy, "decide", None)
        if decide is None or not callable(decide):
            out_queue.put(json.dumps({"error": "policy.py does not define a callable decide(state)"}))
            return
    except Exception as e:  # noqa: BLE001 - untrusted import must never crash uncaught
        out_queue.put(json.dumps({"error": f"failed to load policy.py: {e}"}))
        return

    out_queue.put(json.dumps({"ready": True}))

    while True:
        try:
            msg = in_queue.get(timeout=120)
        except queue.Empty:
            return
        if msg is None:
            return
        payload = json.loads(msg)
        try:
            techs = tuple(
                sim.TechSnapshot(
                    tech_id=t["tech_id"], skills=frozenset(t["skills"]), continuous_work=t["continuous_work"],
                    shift_end=t["shift_end"], overtime_used=t["overtime_used"], max_overtime=t["max_overtime"],
                )
                for t in payload["free_technicians"]
            )
            jobs = tuple(
                sim.JobSnapshot(
                    job_id=j["job_id"], required_skill=j["required_skill"], duration=j["duration"],
                    priority=j["priority"], deadline=j["deadline"], arrival_time=j["arrival_time"],
                    is_followup=j["is_followup"],
                )
                for j in payload["pending_jobs"]
            )
            state = sim.SimState(current_time=payload["current_time"], free_technicians=techs, pending_jobs=jobs)
            assignments = decide(state)
            assignments = [(str(a), str(b)) for a, b in assignments]
            out_queue.put(json.dumps({"assignments": assignments}))
        except Exception as e:  # noqa: BLE001
            out_queue.put(json.dumps({"error": str(e)}))
            return


if __name__ == "__main__":
    # Guard required for the "spawn" start method on all platforms.
    pass
