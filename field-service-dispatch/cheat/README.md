# Adversarial testing notes

Harbor never executes anything under this directory. Every attempt here
was actually run against the real verifier via `dev/local_harness.sh`
(which runs the real `tests/test.sh`, `collect_agent_output.py`, and
`test_dispatch_grading.py` against real `/app`, `/tests`, `/work`,
`/logs` paths and a Python matching `tests/Dockerfile`'s exact pinned
installs). Results below are measured, not hypothetical.

Unlike a CSV-output-only task, this one genuinely executes candidate code
(the submitted `decide()` policy), so the full untrusted-execution attack
surface applies and was tested directly.

Re-verified three times after recalibration: once when the single sealed
`held_out` scenario was replaced with two structurally distinct ones
(`held_out_1`, `held_out_2`, both must individually clear their own pass
bar) and the reference matching algorithm switched from brute force to
the Hungarian algorithm; again after a real cost-model bug (a scarcity
sentinel scored a pure generalist as merely neutral instead of the safest
choice, and a technician could be committed to a job that could no longer
meet its deadline) was found and fixed, the reference was given the same
time-zero batching a capable policy needs, and both scenarios were
rebuilt with a verified swap-tension mechanism so a joint solve has a
real, measured advantage over every tested greedy; and again after the
architecture change described in #6 below, which changed how Stage 1
runs the candidate at all. Exploits #1-5 still measure reward 0 against
the current `tests/collect_agent_output.py` / `test_dispatch_grading.py`;
the sealing and UID-sweep mechanics they target are unchanged by any of
that.

## 1. Early exit (`early_exit/`)

`policy.py` calls `os._exit(0)` at import time, betting the untrusted
stage treats an early process death as "nothing to grade, default pass"
or otherwise mishandles a missing trace.

**Measured result: reward 0.** `collect_agent_output.py`'s process dies
before writing `/work/trace.json`; `test.sh` checks for that file's
existence independent of the stage's exit code and writes reward 0 when
it's absent.

## 2. Sealed reference read (`sealed_file_read/`)

`policy.py`'s `decide()` tries to open `/tests/sealed/reference/pass_bar.json`
directly, betting the pass bar is readable by the unprivileged stage.

**Measured result: reward 0**, and the read itself fails:

    FAILED: [Errno 13] Permission denied: '/tests/sealed/reference/pass_bar.json'

`test.sh` runs `chown root:root` + `chmod 700`/`600` on `sealed/reference`
before Stage 1 (running as `runner`) ever executes.

## 3. Reward forgery daemon (`reward_forgery_daemon/`)

`decide()` forks on its first call, the child calls `setsid()` to detach
into its own session, then polls for up to 60 seconds trying to overwrite
`/logs/verifier/reward.txt` with `1`.

**Measured result: reward 0**, confirmed genuinely defeated, not just
timed out: after the run, `ps -u runner` shows the forked process as
`<defunct>` (a zombie -- SIGKILL succeeded, it is not merely orphaned or
still executing), and `reward.txt` contains `0`, never `1`, at any point.
`test.sh` runs `pkill -9 -u runner` after Stage 1 and again after Stage 2;
since the candidate cannot change its own UID, detaching into a new
session does not escape a UID-scoped sweep the way it would escape a
process-group-scoped one.

## 4. Crashing policy (`crashing_policy/`)

`decide()` unconditionally raises `RuntimeError`.

**Measured result: reward 0.** `collect_agent_output.py` catches the
exception, records `status: "crashed"`, and Stage 2 fails the
"policy present and loadable" check cleanly rather than the harness
erroring out uncaught.

## 5. Malformed submission -- wrong interface (`malformed_no_decide/`)

`policy.py` defines `solve(state)` instead of `decide(state)`.

**Measured result: reward 0.** Stage 1 detects the missing callable and
records `status: "malformed"` before ever attempting to run a simulation.

## 6. Frame introspection / future-knowledge leak (`frame_introspection/`)

`decide()` walks the Python call stack with `sys._getframe()` looking for
a frame whose locals contain `job_states` -- the trusted simulator's own
internal dict, which (unlike the documented `SimState` snapshot passed to
`decide()`) includes jobs still marked `"not_arrived"`. If found, it reads
those future jobs for clairvoyant scheduling, and separately tries to
tamper with the untrusted-side accounting (replace `overtime_used` with a
self-absorbing zero-like object, monkey-patch `BREACH_PENALTY` /
`OVERTIME_RATE` / `CASCADE_COST` to 0 on every loaded module that has
them). This was a real, measured hole in an earlier version of this
verifier: `decide()` used to run as a plain in-process function call
directly inside `sim.run_simulation`'s own event loop, so `sys._getframe`
genuinely could reach that loop's live locals -- every individual
assignment stayed *legal* at the moment it was returned (technician
free, job pending, skill match), so Stage 2's replay-and-revalidate
design, which only checks legality, never caught it. The unfairness was
entirely in what information `decide()` was never supposed to have, not
in anything a legality check can see.

**Fix:** `decide()` now runs in a genuinely separate OS process
(`tests/candidate_worker.py`, spawned fresh per scenario via
`multiprocessing`'s `spawn` context, never `fork`), and `collect_agent_
output.py` talks to it only through two queues carrying JSON-encoded
`SimState` fields -- current_time, free technicians, pending jobs, exactly
what the documented snapshot exposes. `run_simulation` itself never
executes in that process, so there is no live frame containing
`job_states` (or anything else) to walk to; the fix is structural, not a
block on `sys._getframe` specifically, so it isn't defeated by an
equivalent technique such as `gc.get_objects()`.

**Measured result: reward 0.** A side channel written from inside the
exploit's own `decide()` (`/tmp/exploit_debug.json`, added for this
verification only) confirms `found_job_states: false` and
`future_jobs_seen: false` on all 129 decide() calls across both sealed
scenarios -- the frame walk finds nothing every single time, so the
policy falls back to its plain legal greedy, which naturally fails both
pass bars (measured 3234.5 and 1734.0 against bars of 600.0 and 400.0).
The accounting-tamper half of the attack was already defeated
independently: Stage 2 never imports or trusts anything Stage 1
computed, so a monkey-patched `BREACH_PENALTY` in the candidate's process
has no effect on Stage 2's own fresh import of the real constants.

## Why the "claim more than is true" family doesn't apply to exploits #1-5

There is no submitted claim of cost, feasibility, or optimality to distrust
in the first place: the candidate submits code, not a result. Stage 2
never trusts anything Stage 1 computed either -- it takes only the raw
sequence of `(technician_id, job_id)` pairs the candidate's `decide()`
returned at each call (the "decision trace") and mechanically replays that
sequence through the same deterministic event loop used for the sealed
scenario, independently re-validating every assignment's legality (technician
actually free, job actually pending, skill match, overtime cap) and
recomputing the cost from scratch. A trace that claims an assignment no
longer valid at replay time is simply not applied -- replay can only ever
score a tampered or inconsistent trace the same or worse than a faithful
one, never better. Legality-only revalidation is NOT sufficient on its own,
though -- exploit #6 above is the counterexample: every assignment it
produced was legal, and the problem was entirely in what information
`decide()` had access to while deciding, which is exactly why that fix had
to change where `decide()` runs, not what Stage 2 checks about its output.
