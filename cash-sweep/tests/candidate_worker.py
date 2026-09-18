"""
Runs ONLY the candidate's decide() function, in its own OS process,
spawned fresh (multiprocessing "spawn" context, never "fork") so it never
inherits any of the trusted simulator process's memory. It communicates
with that process exclusively through two queues carrying plain
JSON-encoded strings -- never pickled objects, so nothing this process
sends back can trigger code execution on the far end by shaping a
malicious pickle payload, and nothing beyond the literal SimState fields
below is ever transmitted to it in the first place.

Built this way from the start (see the companion field-service-dispatch
bundle's cheat/frame_introspection/ for what happens when decide() runs
in-process instead): a genuinely separate OS process's call stack and
heap contain nothing but the JSON payload explicitly sent to it --
current_time, balances, pending obligations, and the public rate/cutoff
schedule, exactly what the documented SimState exposes -- so there is no
live run_simulation frame to walk to for future obligations, regardless
of the introspection technique used.
"""
import importlib.util
import json
import queue
import sys


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
            obligations = tuple(
                sim.ObligationSnapshot(
                    obligation_id=o["obligation_id"], currency=o["currency"], amount=o["amount"],
                    due_time=o["due_time"], arrival_time=o["arrival_time"],
                )
                for o in payload["pending_obligations"]
            )
            state = sim.SimState(
                current_time=payload["current_time"],
                balances=tuple(tuple(b) for b in payload["balances"]),
                pending_obligations=obligations,
                currencies=tuple(payload["currencies"]),
                spread_cheap=tuple(tuple(r) for r in payload["spread_cheap"]),
                spread_expensive=tuple(tuple(r) for r in payload["spread_expensive"]),
                cutoff_time=tuple(tuple(r) for r in payload["cutoff_time"]),
            )
            transfers = decide(state)
            transfers = [(str(f), str(t), float(a)) for f, t, a in transfers]
            out_queue.put(json.dumps({"transfers": transfers}))
        except Exception as e:  # noqa: BLE001
            out_queue.put(json.dumps({"error": str(e)}))
            return


if __name__ == "__main__":
    # Guard required for the "spawn" start method on all platforms.
    pass
