# Handoff: building afterquery/* Harbor task bundles

Read this fully before touching any files. It distills what actually got
tasks rejected across four builds (field-service-dispatch [passed],
cash-sweep [rejected, similarity], withholding-tax [rejected 3x on
difficulty/typos before passing], claims-reserve-allocation [rejected on
difficulty/concision/extraneous-files, then fixed]), plus two structural
bugs that got a passing-quality bundle bounced at the submission gate. The
goal is to not re-spend resources relearning any of this.

Account scope: `afterquery/*` namespace, category = Operations, seen
subdomains so far: Finance, Logistics, Supply chain, Claims, Compliance,
Marketing.

---

## 0. Workflow order — do not skip steps

1. **Idea-check first.** Write a 1-paragraph idea description and run it
   through the idea-checker before writing a single line of task code.
   Iterate the paragraph (not the code) until it comes back **Accept**.
   Building first and idea-checking later has never once been the
   cheaper path in this account's history.
2. **Design the difficulty mechanism and empirically stress-test it
   BEFORE building the full bundle.** See §2. A cheap standalone spike
   script that measures whether your intended baselines actually separate
   is worth an hour; discovering they don't after building 60 files is
   not.
3. **Build the bundle**: environment/, solution/, tests/, cheat/,
   dev/ (scratch, excluded from final zip), task.toml.
4. **Verify everything locally** via a no-Docker harness script before
   ever creating the submission zip (see §5). Oracle must pass, every
   cheat must fail, with real measured numbers, not assumed ones.
5. **Get a fact sheet from me, write instruction.md yourself** (see §4 —
   this is a hard rule, not a suggestion).
6. **I fact-check your instruction.md draft against the actual code and
   data.** Any mismatch gets fixed in the code/data if I caused it, or
   flagged back to you if it's your prose (I do not rewrite your prose).
7. **Build the final zip, deliver it.** Re-verify after ANY edit to
   anything the verifier depends on (bar, model, generator) — don't ship
   on stale confidence.

---

## 1. Bundle structure (what goes in the zip, what doesn't)

```
task.toml
instruction.md            (user-authored, see §4)
environment/
  Dockerfile               <-- MUST have COPY . /app + mkdir -p /app/outputs (see §6.1)
  <SPEC>.md                 the fully-disclosed rulebook/model
  data/
    worked_example/         small, hand-checkable dataset + README.md
    case/                   larger practice dataset, same shape as sealed data
solution/
  <entry_file>.py            the reference solution
  solve.sh                  <-- MUST exist, copies entry_file to /app/outputs/ (see §6.2)
tests/
  Dockerfile
  test.sh                    two-stage: seal ground truth, run Stage 1 untrusted, Stage 2 trusted grade
  collect_agent_output.py    Stage 1: runs candidate as subprocess(es), collects output
  test_<task>_grading.py     Stage 2: re-simulates/re-checks against sealed reference, no candidate code runs here
  sealed/
    inputs/<name>/            sealed INPUT data -- left readable, candidate legitimately needs it
    reference/<name>_reference.json   sealed ANSWER/bar -- chown+chmod root-only before Stage 1
cheat/
  README.md                  adversarial testing notes, measured results, not hypothetical
  <exploit_name>/<entry_file>.py   one dir per adversarial attempt
dev/                        <-- EXCLUDED from final zip. Scratch: generators, calibration
                                 scripts, spike tests, local harness. Keep everything here
                                 that isn't part of the graded submission.
```

**Two structural bugs that will bounce a otherwise-good bundle at
submission — check these explicitly before first submission, not after:**

### 6.1 `environment/Dockerfile` needs `COPY . /app`

```dockerfile
FROM python:3.13-slim-bookworm
RUN pip install --no-cache-dir <whatever the solution needs>
WORKDIR /app
COPY . /app
RUN mkdir -p /app/outputs
```
Without `COPY . /app` and the `mkdir -p /app/outputs`, none of your
`environment/` files (spec doc, data/) actually land in the agent's
container, and the outputs dir doesn't pre-exist. This is silent —
nothing errors at build time, the agent just can't see anything, or the
harbor upload step fails looking for `/app`. Confirmed this exact bug
in a bundle that otherwise had passing-quality content.

### 6.2 `solution/solve.sh` must exist

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /app/outputs
cp "$SCRIPT_DIR/<entry_file>.py" /app/outputs/<entry_file>.py
```
Every bundle needs this — the platform's oracle run executes it to
populate `/app/outputs/` and must score 1. A bundle with a working
`solution/<entry_file>.py` but no `solve.sh` fails bundle-structure
validation before quality review even runs. Make it executable
(`chmod +x`). Verify it actually works by running it once against the
real `/app` path (or check it's byte-identical after running).

---

## 2. Difficulty — the actual hard part, read this twice

Every rejection this account has gotten has been about difficulty (or a
symptom of it — similarity is a difficulty-genre problem in disguise).
The failure mode is always the same shape: **the task LOOKS hard when you
design it, but a plausible non-expert approach turns out to clear the
bar anyway**, because you calibrated against an abstract idea of
"sophisticated" rather than against a concretely-implemented alternative
approach.

### 2.1 Anti-patterns, confirmed by actual rejections

- **"Difficulty from careful reading."** A fully-spelled-out spec plus a
  worked example that walks through every rule collapses the task to
  "read carefully, implement it" — not difficult, no matter how long or
  detailed the spec is. (withholding-tax v1.)
- **"Difficulty from hidden information."** Don't make the task hard by
  withholding facts the agent legitimately needs; that's an unfair-spec
  problem, not genuine difficulty, and reviewers catch it.
- **Answer leakage in your OWN supporting materials.** A code comment
  that explains a bug's mechanism, a worked-example README sentence that
  explains WHY a decision is correct (not just what it is), an
  instruction sentence disclosing an exact count/detail of the answer —
  all defeat an otherwise-sound difficulty design. Audit every comment
  and every README sentence you write for "does this hand over the
  mechanism, not just the mechanics." (withholding-tax v2.)
- **Genre reuse.** Same underlying scaffold/architecture as a prior
  submission in the account, even with a different surface domain, reads
  as similarity and gets rejected regardless of content differences.
  (cash-sweep vs field-service-dispatch: both were "live decide()-loop
  against a simulator.")
- **Calibrating the bar against an abstract "weak vs. strong" pair
  instead of a concrete alternative implementation.** This is the
  expensive one. See §2.2.

### 2.2 The load-bearing lesson: prove the bar survives a real adversarial implementation

If your task is "submit code that gets scored against a bar," your
instinct will be to build:
- a **weak baseline** (naive/greedy/no-real-effort), and
- a **strong reference** (your actual intended solution),

and set the bar at some midpoint. **This is not enough.** A quality
reviewer will write their own genuinely-competent-but-not-maximally-
sophisticated implementation and test it against your bar. If that
implementation was never in your calibration set, you don't know if it
clears your bar until someone else finds out for you — which is
expensive and slow.

What actually happened: a task's difficulty rested on "correlation-aware
optimization is hard." The reviewer wrote a ~40-line heuristic (Monte
Carlo simulator from the disclosed spec + greedy-by-simulated-marginal-
value + 1-1 swaps) — not sophisticated, well within an undergrad's reach
in a day — and it matched or beat the "sophisticated" reference solution.
The bar had no real headroom because the reference wasn't meaningfully
better than a strong simple heuristic for that problem's actual
structure.

**The fix that worked, and the process to replicate:**

1. Before finalizing any bar, explicitly ask: *"What is the most
   plausible 40-line-or-less heuristic a competent-but-not-expert
   engineer would write against my fully-disclosed spec, and how well
   does it do?"* Then **actually implement that heuristic** (not a
   strawman weaker one) and measure it against your real sealed data.
2. If it clears the bar (or comes close), your difficulty mechanism
   doesn't have enough depth — tuning the bar number will not fix this,
   because it means your "sophisticated" reference isn't actually much
   better than the simple approach for this problem's structure. You
   need a structural fix, not a calibration fix.
3. The structural fix that worked: inject genuine **complementarity** —
   a decision that requires TWO OR MORE simultaneous choices where
   NEITHER individual choice shows any local improvement, only the
   combination does. This defeats any one-at-a-time greedy or local
   (1-swap) search by construction, because such methods only ever take
   a step that improves the current state; they can't discover a
   "valley then cliff" reward shape. It does NOT require making the
   problem unfair or opaque — the mechanism can and should be fully
   disclosed. Concretely (claims-reserve-allocation): a few items were
   individually priced as a bad deal, only becoming a good deal once
   settled/chosen together with one specific paired partner. A solver
   needs real joint/combinatorial reasoning (e.g., an AND-linearization
   in a MILP: auxiliary binary `w = x_i AND x_j` linked via
   `w <= x_i, w <= x_j, w >= x_i + x_j - 1`) to find these; greedy and
   swap-based local search structurally cannot.
   This generalizes: look for real-world "package deal" / "bundle" /
   "consolidated settlement" / "joint decision" economics in your domain
   — they are both realistic and provably greedy-defeating.
4. **Calibrate the bar directly against the measured adversarial
   heuristic, not just against your abstract weak/strong pair.** e.g.
   `bar = min(bar_vs_naive_baseline, risk_aware_obj + 0.35 * (adversarial_heuristic_obj - risk_aware_obj))`
   — whichever gives the stricter (lower, for a minimization objective)
   bound wins, so neither baseline can slip through. Ship the
   adversarial heuristic itself as a permanent regression-test entry
   in `cheat/`.
5. **Re-verify with a FRESH random seed**, not just the one used during
   calibration — solver/heuristic quality can vary run to run
   (confirmed: a MILP reference found anywhere from ~15% to 100% of the
   available complementary pairs depending on internal scenario-sampling
   luck at one parameter setting; the fix was widening the margin, not
   just re-running).
6. Check margins against measured Monte Carlo noise, not assumption:
   run your oracle's own objective estimator N times with a fixed
   decision set and different eval seeds, take the relative std. Bar
   margins should be comfortably (~8-10x+) above that noise floor on
   both sides (reference passes with margin, adversarial heuristic fails
   with margin). A margin of 1-2% next to ~0.1-0.25% noise is fine; a
   margin smaller than ~5x noise is flaky and will eventually produce a
   borderline pass/fail that looks like a bug.

### 2.3 What "genuinely difficult" has looked like across this account

- **Online decision-making against a live, partially-observed
  simulator** (field-service-dispatch) — passed. Difficulty from
  sequential decisions under revealed-over-time information, not from
  spec complexity.
- **Budget-constrained combinatorial optimization with a nonlinear risk
  term AND genuine complementarity** (claims-reserve-allocation, after
  the fix) — the risk term alone wasn't enough (see §2.2); adding
  complementarity was.
- Do **not** reuse the exact "live decide()-loop against a simulator"
  architecture a second time in the same account — that's what got
  cash-sweep rejected on similarity even though the surface domain
  (cash sweep vs. field dispatch) was completely different. If your idea
  is naturally an online/sequential-decision task, that's fine as an
  idea, but check what genre the account's other recent submissions used
  and pick a structurally different one if there's overlap.

---

## 3. Verification / anti-cheat discipline

- **Seal the ground truth, not the input data.** The candidate's code
  legitimately needs to read the sealed INPUT data to compute anything.
  Only the reference answer / eval seed / pass bar needs to be
  root-owned and `chmod 700`'d, and that sealing must happen in
  `test.sh` BEFORE Stage 1 (untrusted candidate code) ever runs.
  Ownership must transfer to the executing UID for a self-chmod to
  succeed if you rely on that pattern.
- **Process isolation matches the task's shape**: a one-shot batch task
  (submit code, run once per sealed dataset, get a score) just needs a
  subprocess per dataset with a firm timeout under an unprivileged user
  — no shared-memory or live-simulator leak surface exists. A live
  decide()-per-event task needs actual process isolation (e.g.
  multiprocessing, not just subprocess) between the candidate's policy
  and the simulator holding ground truth, because naive threading lets
  the candidate frame-introspect the trusted process. If you're building
  a live-loop task, look at how a passed bundle solved this before
  reinventing it.
- **Only ONE file is ever graded** (whatever `artifacts` in task.toml
  names, e.g. `/app/outputs/<entry>.py`). Any cheat/exploit design that
  assumes it can ship a companion data file alongside the main script is
  invalid and needs to embed that data inline in the single file instead
  — this is also what a real exploit attempt would have to do, so it's
  not just a build convenience, it's the honest adversarial model.
- **Mechanical checks (budget caps, schema/coverage checks, feasibility)
  should run BEFORE any simulation**, and should be exact/deterministic
  (a dollar-sum comparison, an exact set-equality check) — never subject
  to Monte Carlo noise. This also means a "looks good but slightly over
  budget" cheat attempt fails reliably, not probabilistically.
- **Build cheat/ entries for every angle you can think of**, run each
  through the real local harness, and record MEASURED results (not
  hypothesized ones) in `cheat/README.md`. Minimum standard set, adapt
  per task:
  1. Reward forgery (write directly to the reward file)
  2. Sealed-reference/ground-truth read attempt
  3. Crash
  4. Malformed interface (wrong function name / missing CLI entry)
  5. Infinite loop / timeout
  6. Constraint violation (budget, schema) that looks otherwise plausible
  7. Do-nothing / trivial baseline
  8. A "did no real analysis" naive baseline
  9. The best plausible naive-but-principled baseline (this is the one
     most likely to be your actual difficulty ceiling — see §2.2)
  10. Memorized/hardcoded answers from visible data (confirm it fails to
      generalize to sealed data for a REAL reason, e.g. numbers differ,
      not just "we didn't test it")
  11. Whatever concrete adversarial heuristic you identified per §2.2

---

## 4. instruction.md — hard authorship rule

**instruction.md prose is 100% user-authored. I only ever:**
- produce a fact sheet (facts, interface, grading structure, required
  closing sentence — never narrative prose you're meant to copy) for you
  to write instruction.md FROM,
- fact-check your actual draft against the real code/data and report
  mismatches,
- perform narrowly-scoped MECHANICAL DELETIONS of exact phrases a
  reviewer quoted verbatim (never composition, never rewording, never
  addition) — and only when you've told me to move fast without passing
  it back through you each time.

If a reviewer flags instruction.md concision/hand-holding/leakage, I'll
name the exact sentences and either delete them (if you've authorized
autonomous fixing) or hand them back to you to cut yourself. I will not
rewrite your sentences to fix a factual or style problem — even a tiny
one — without this being flagged explicitly as an exception.

Required closing sentence (easy to miss, exact match required):
```
You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
```
where N = the integer value of `[agent].timeout_sec` in task.toml, preceded
by a blank line, at most one trailing newline after.

---

## 5. Local verification harness pattern

Build `dev/local_harness.sh` (no Docker required) that:
1. Copies a candidate file into a scratch `/app/outputs/`.
2. Copies `tests/` into the scratch dir and `sed`-rewrites any hardcoded
   `/app`, `/tests`, `/work`, `/logs` absolute paths to the scratch
   equivalents.
3. Runs the real `tests/test.sh` against the scratch tree as the real
   `runner` unprivileged user.
4. Prints the reward, both stage logs, and any orphaned `runner`
   processes.

Run this against `solution/<entry>.py` (must pass) and every `cheat/*/`
entry (must fail) before ever building the submission zip, and AGAIN
after any change to the model, generator, or bar calibration — stale
verification is how a passing bundle regresses silently.

For long-running verification (MILP solves, large Monte Carlo runs), use
background execution rather than blocking — these can take minutes, and
there is no value in the harness sitting idle waiting on a foreground
call when other file/doc work can happen in parallel.

---

## 6. task.toml content discipline

- `difficulty_explanation`: open with WHO does this work in the real
  world and WHY it's a genuine part of their job (not "the agent must").
  Explicitly disclose that data is synthetic. State the concrete
  adversarial-baseline numbers from §2.2 (the measured shortfall of the
  best plausible non-expert approach), not just abstract claims.
  Never include resubmission-history narrative ("this was rejected
  before because...") — reviewers see this as a wording problem being
  patched instead of a description of the task's own difficulty.
- `solution_explanation`: describe the reference algorithm precisely
  enough that its difficulty is self-evident (name the technique: MILP
  with a specific linearization, scenario-based sampling, etc.), and
  state how its advantage over baselines was verified (fresh seeds,
  multiple independent instances) — don't just assert stability.
- `verification_explanation`: name the isolation pattern used and why
  it fits the task's shape (batch vs. live-loop), what's sealed vs. not
  and why, and summarize every cheat/ result with real numbers.
- Verifier/agent timeouts: **measure your reference solution's actual
  wall-clock time** (including any MILP/optimization step) and set
  `[verifier].timeout_sec` and any per-dataset subprocess timeout with
  real margin above that — don't guess. If your reference needs ~3
  minutes per dataset for two datasets, don't ship a 300-second total
  verifier budget.

---

## 7. Git / delivery mechanics specific to this account

- Work on the assigned branch (`claude/...`), commit and push regularly
  — a stop-hook enforces "no uncommitted changes" between turns, so
  commit WIP freely and often; there's no penalty for many small commits
  during a build.
- Clean `__pycache__` before every commit (`find <bundle> -name
  __pycache__ -exec rm -rf {} +`), it's noise, not useful history.
- The final submission zip **excludes** `dev/` and any standalone fact
  sheet file:
  ```bash
  cd <bundle-dir> && zip -r ../<bundle>-final.zip . \
    -x "dev/*" "INSTRUCTION_FACT_SHEET.md" -x "*.pytest_cache*" -x "*__pycache__*"
  ```
  A delivered zip is a build artifact, not repo content — after sending
  it via file delivery, delete it from the working tree so the repo
  stays clean (`rm <bundle>-final.zip`).
- Deliver the fact sheet and the final zip as files (not pasted inline)
  once verification is complete.

---

## 8. If a "Validation failed" or unfamiliar pipeline error shows up

If a submission error names something that has no precedent in any
bundle you've built (no matching file/structure requirement you've ever
seen asked for before) and especially if it follows an explicit
"the evaluation service errored" message, treat it as a possible
platform/pipeline-side failure, not necessarily a bundle content problem.
Don't guess-build a speculative fix for an unspecified requirement —
that risks wasted effort on the wrong artifact. Say plainly what's known
vs. unknown, and recommend escalating to project support for anything
that has no structural precedent, while still fixing anything you CAN
verify against real prior bundles or explicit reviewer text.

---

## 9. Bring to a fresh session, in order

1. This document.
2. Your idea, as a single paragraph, ready to run through the
   idea-checker as-is.
3. Any files/data you already have for it (if none, that's fine — this
   doc's workflow starts from an idea, not from files).

Then let the session idea-check first, and don't let it start writing
task code until that comes back Accept.
