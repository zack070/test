# Adversarial testing notes

All entries below were run through `dev/local_harness.sh` (the real
`tests/test.sh` two-stage verifier) against both sealed instances
(`case_a`, seed 7001; `case_b`, seed 7002), or a targeted standalone
check where noted (infinite loop, permission-sealing reads/writes).
Every entry scores reward **0** on both instances; the reference
solution (`solution/scheduler.py`) scores **1** on both.

## The two headline adversarial baselines (the actual difficulty claim)

### CP-SAT at the same 180-second time budget any submission gets

Not a bundled cheat/ file (it's a solver run, not a submitted script),
but the load-bearing evidence for `difficulty_explanation`, measured
directly with `dev/build/calibrate.py` against a proper AddCircuit-based
CP-SAT formulation of the exact same objective:

| instance | reference (180s) | CP-SAT (180s) | CP-SAT proven optimal? |
|---|---|---|---|
| case_a | 4230 | 5447 | no |
| case_b | 4210 | 6303 | no |

CP-SAT never matches the reference at the real time budget on either
instance, and never proves optimality. This directly answers the "would
a competent exact solver just clear the bar given more time" concern:
no, not at the time budget any submission actually receives.

### `atcs_no_search/` and the ATCS+local-search level (folded into the bar)

The bar itself (`reference_objective * 1.15`) is set so that a
genuinely competent, published dispatch heuristic — ATCS (Apparent
Tardiness Cost with Setups, Lee/Bhaskaran/Pinedo 1997) plus adjacent-swap
and reinsertion local search — still fails:

| instance | ATCS+local-search | pass bar | fails? |
|---|---|---|---|
| case_a | 7837 | 4864.5 | yes (61% over) |
| case_b | 5331 | 4841.5 | yes (10% over) |

`atcs_no_search/scheduler.py` in this directory is the ATCS construction
step alone, with no follow-up search at all:

| instance | ATCS only | pass bar | fails? |
|---|---|---|---|
| case_a | 25553 | 4864.5 | yes (5.3x over) |
| case_b | 24999 | 4841.5 | yes (5.2x over) |

## Additional adversarial angles

### `edd_only/`

Sorts jobs by due date alone (classic EDD dispatch rule), completely
ignoring setup times — the "did no real analysis of the actual
objective" baseline.

**Measured:** case_a=62055, case_b=64910, both roughly 13x the pass bar.

### `hardcoded_answers/`

Embeds a fully-computed sequence for the *visible* practice instance
(`environment/data/case`, seed 6001, job ids `J000`-`J044`) inline in the
single graded file and returns it regardless of the actual input. The
sealed instances use disjoint id ranges (`J100`-`J144` and
`J300`-`J344`) specifically so a memorized visible-instance sequence
cannot coincidentally validate; this fails the permutation-coverage
check before any scoring happens.

### `reward_forgery/`

Attempts to write `1` directly to `/logs/verifier/reward.txt` and to
overwrite `/tests/sealed/reference/*.json` with a fabricated pass bar.
Both targets are `chown root:root` / `chmod 700` (files `chmod 600`) by
`tests/test.sh` before Stage 1 (the untrusted candidate subprocess,
running as the unprivileged `runner` user) ever executes; verified
directly that both writes raise `PermissionError` under the real
UID/permission split. `test.sh` also unconditionally calls
`write_reward()` again after Stage 2 grades the (still-wrong) sequence,
so any earlier tampering is overwritten regardless.

### `sealed_reference_read/`

Attempts to read `/tests/sealed/reference/*.json` directly. Same
root-owned, chmod-700 sealing applies; verified directly that this
raises `PermissionError` under the `runner` UID. Falls back to the
input's natural job order on the read failure (also fails on the merits,
since it never runs any real scheduling).

### `crashing/`

Raises an unconditional exception. Stage 1 records `status: "crashed"`
with captured stderr; `test_scheduler_present_and_ran` fails.

### `malformed_interface/`

Ignores the documented `--instance/--output/--time-budget` CLI entirely.
Produces no output file; Stage 1 records `status: "no_output_file"`.

### `infinite_loop/`

`while True: pass`. Verified against the real per-dataset subprocess
timeout mechanism (`subprocess.run(..., timeout=...)` in
`collect_agent_output.py`) with a temporarily shortened timeout for
speed, confirmed `status: "timeout"` after the process is killed. The
real 195-second timeout uses the identical, unmodified code path.

### `empty_sequence/`

Produces a syntactically valid but empty output (`{"sequence": []}`).
Fails the permutation-coverage assertion immediately (`set(sequence) ==
all_ids` requires all 45 job ids, gets none).
