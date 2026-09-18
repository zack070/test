# Adversarial testing notes

Harbor never executes anything under this directory. Every attempt here
was actually run against the real verifier via `dev/local_harness.sh`
(which runs the real `tests/test.sh`, `collect_agent_output.py`, and
`test_cashsweep_grading.py` against real `/app`, `/tests`, `/work`,
`/logs` paths and a Python matching `tests/Dockerfile`'s exact pinned
installs). Results below are measured, not hypothetical.

This bundle reuses the verifier ARCHITECTURE proven on the companion
field-service-dispatch bundle (two-stage sealed verifier, candidate code
isolated in its own OS process, raw scenario files chown'd to the
unprivileged user and chmod 000'd immediately after their one trusted
read) but was built with every lesson from that bundle's own adversarial
testing already folded in from day one, rather than discovered by a
failing probe after the fact. In particular the exploit below labeled #1
was found the hard way on field-service-dispatch (its own cheat/sealed_
input_read/ has the full story, including a first "fix" that silently
failed because the sealed files were root-owned and the unprivileged
user cannot chmod a file it does not own) and is tested here as the
FIRST thing checked, not a late addition.

## 1. Direct raw-scenario-file read (`sealed_input_read/`)

`decide()` tries to `open()` the sealed scenario's `obligations.csv`
directly -- the file lists every obligation's arrival_time and due_time
for the whole day, including ones that haven't "arrived" in the
documented SimState yet. decide() runs in its own OS process (candidate_
worker.py, spawned via `multiprocessing`'s `spawn` context) under the
same `runner` UID as collect_agent_output.py; process isolation stops it
sharing that process's memory, not its filesystem access.

**Measured result: reward 0**, confirmed via a side channel
(`/tmp/sealed_input_read_debug.json`, added for this verification only)
showing `leak_succeeded: false` -- the read genuinely fails with
`Permission denied`. `test.sh` `chown`s `/tests/sealed/inputs` to
`runner` before Stage 1 runs (so `collect_agent_output.py`'s own
post-read `chmod 000` -- which only succeeds for a file's owner or root
-- actually takes effect), and `collect_agent_output.py` reads every
scenario into memory and seals every scenario file/directory for BOTH
held-out scenarios before spawning even the first worker process. Because
the read fails, `decide()` falls back to its plain legal greedy (see the
file's own fallback logic), so the measured reward of 0 confirms the leak
contributed nothing rather than merely confirming an empty schedule
fails: the fallback still produces a full decision trace that funds every
obligation, just not optimally.

## 2. Frame introspection / future-knowledge leak (`frame_introspection/`)

`decide()` walks the Python call stack with `sys._getframe()` looking for
a frame whose locals contain `obligation_states` -- the trusted
simulator's own internal dict, which (unlike the documented `SimState`
snapshot) includes obligations still marked `"not_arrived"`.

**Measured result: reward 0.** A side channel
(`/tmp/frame_introspection_debug.json`) confirms `found_obligation_states:
false` on every decide() call across both sealed scenarios: decide() runs
in a genuinely separate OS process from the start (tests/candidate_
worker.py), so there is no `run_simulation` frame in this process's call
stack to walk to in the first place -- the fix is structural, not a block
on `sys._getframe` specifically, so it is not defeated by an equivalent
technique such as `gc.get_objects()`.

## 3. Sealed reference read (`sealed_reference_read/`)

`decide()`'s tries to open `/tests/sealed/reference/pass_bar.json`
directly, betting the pass bar is readable by the unprivileged stage.

**Measured result: reward 0**, and the read itself fails:

    FAILED: [Errno 13] Permission denied: '/tests/sealed/reference/pass_bar.json'

`test.sh` runs `chown root:root` + `chmod 700`/`600` on `sealed/reference`
before Stage 1 (running as `runner`) ever executes.

## 4. Reward forgery daemon (`reward_forgery_daemon/`)

`decide()` forks on its first call, the child calls `setsid()` to detach
into its own session, then polls for up to 60 seconds trying to overwrite
`/logs/verifier/reward.txt` with `1`.

**Measured result: reward 0.** `test.sh` runs `pkill -9 -u runner` after
Stage 1 and again after Stage 2; since the candidate cannot change its
own UID, detaching into a new session does not escape a UID-scoped sweep
the way it would escape a process-group-scoped one.

## 5. Crashing policy (`crashing_policy/`)

`decide()` unconditionally raises `RuntimeError`.

**Measured result: reward 0.** `collect_agent_output.py` catches the
exception, records `status: "crashed"`, and Stage 2 fails the
"policy present and loadable" check cleanly rather than the harness
erroring out uncaught.

## 6. Malformed submission -- wrong interface (`malformed_no_decide/`)

`policy.py` defines `solve(state)` instead of `decide(state)`.

**Measured result: reward 0.** Stage 1 detects the missing callable and
records `status: "malformed"` before ever attempting to run a simulation.

## 7. Early exit (`early_exit/`)

`policy.py` calls `os._exit(0)` at import time, betting the untrusted
stage treats an early process death as "nothing to grade, default pass"
or otherwise mishandles a missing trace.

**Measured result: reward 0.** `collect_agent_output.py`'s process dies
before writing `/work/trace.json`; `test.sh` checks for that file's
existence independent of the stage's exit code and writes reward 0 when
it's absent.

## Why the "claim more than is true" family doesn't apply to exploits #3-7

There is no submitted claim of cost, feasibility, or optimality to
distrust in the first place: the candidate submits code, not a result.
Stage 2 never trusts anything Stage 1 computed either -- it takes only
the raw sequence of `(from_currency, to_currency, amount)` triples the
candidate's `decide()` returned at each call (the "decision trace") and
mechanically replays that sequence through the same deterministic event
loop used for the sealed scenario, independently re-validating every
transfer's legality (sufficient balance at that point in the batch, a
real market for the pair, no double-counting a currency beyond what it
actually has left) and recomputing the cost from scratch. A trace that
claims a transfer no longer valid at replay time is simply not applied --
replay can only ever score a tampered or inconsistent trace the same or
worse than a faithful one, never better. Legality-only revalidation is
NOT sufficient on its own, though -- exploits #1 and #2 are the
counterexample: every transfer either of them could have produced would
have been individually legal, and the problem was entirely in what
information `decide()` had access to while deciding, which is exactly
why closing them had to change where `decide()` runs and what it can
reach on disk, not what Stage 2 checks about its output.
