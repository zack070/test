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

## Why the "claim more than is true" family doesn't apply here the same way

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
one, never better.
