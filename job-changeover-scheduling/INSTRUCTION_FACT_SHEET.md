# Fact sheet for instruction.md (job-changeover-scheduling)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself, in your own words. Facts only; no
narrative framing implied. Given the recent AI-detection rejection on the
loan-suspense-posting task, write this one directly yourself from these
bullets rather than asking any AI (including me) to draft or reword it.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/scheduler.py`.
- Required interface: invokable as a script,
  `python3 scheduler.py --instance <instance.json> --output <output.json> --time-budget <seconds>`.
- `--time-budget` tells you, in seconds, how long you have before the
  process is killed. There is no grace period -- write `<output.json>`
  before that time is up, or you get 0 for that dataset, same as a crash.
- `<output.json>` must be a single JSON object: `{"sequence": [job_id, ...]}`.
  `sequence` must be a permutation of every `job_id` in the input instance
  -- every job exactly once, nothing missing, nothing invented, no
  duplicates.

## The problem

- `/app/SCHEDULING_SPEC.md` is the complete, authoritative statement of
  the problem: a single machine, one job at a time, no preemption. Each
  job has `family`, `proc_time`, `due_date`, `weight`. Before a job runs,
  the machine needs a sequence-dependent setup time based on which
  family ran immediately before it (`setup_matrix[a][b]`, a full F x F
  table, disclosed in the input), or `initial_setup[family]` before the
  very first job. Same-family setups can be nonzero too -- always apply
  the table, never skip it.
- The objective is total weighted tardiness: simulate the sequence from
  time 0, accumulate `weight * max(0, completion_time - due_date)` for
  every job. Lower is better; no credit for finishing early.
- This is optimization, not a report to compute from a spec -- there is
  no single "correct" sequence to transcribe. The agent has full latitude
  on method (heuristic, metaheuristic, exact solver, anything).

## Reference material available to the agent

- `/app/SCHEDULING_SPEC.md` -- full rules, as above.
- `/app/data/worked_example/` -- 4 jobs, 2 families, with a `README.md`
  that hand-walks two example sequences (objective 308 and 159
  respectively) so the agent can check its own scoring logic before
  trusting it on larger data. Also has `instance.json` in the same
  schema as the real data.
- `/app/data/case/` -- a 45-job practice instance in the same shape as
  the graded data, with its own short `README.md` noting it is practice
  data, not the graded instance. Job ids are `J000`-`J044`.

## Grading structure

- Grading runs the agent's own submitted `/app/outputs/scheduler.py`
  against TWO sealed held-out instances the agent never sees (45 jobs
  each, disjoint job-id ranges from the practice case and from each
  other), each as a fresh subprocess with the disclosed 180-second time
  budget.
- Each instance is checked against its own sealed pass bar
  independently -- not averaged. Both must pass for the submission to
  score 1; there is no partial credit.
- For each instance: a structural check runs first (the submitted
  sequence must be an exact permutation of that instance's job ids,
  checked mechanically, no scoring needed if it fails). Then the
  objective is computed by an independently-written scorer and compared
  to that instance's sealed pass bar.
- The pass bar was set at 1.15x the reference solution's measured
  objective on each instance, and was calibrated directly against real
  measured baselines run at the SAME 180-second budget any submission
  gets: a state-of-the-art exact solver (Google OR-Tools CP-SAT) failed
  to match the reference on both instances (28.8% and 49.7% worse
  respectively, never proving optimality), and a genuinely competent
  published dispatch heuristic (Apparent Tardiness Cost with Setups,
  plus local search) also fell short on both (61% and 10% over the bar
  respectively). See cheat/README.md for the complete measured numbers
  across nine adversarial submissions.

## Constraints

- Leave `/app/SCHEDULING_SPEC.md` and everything under `/app/data/`
  unchanged.
- The program should be reasonably deterministic and must respect its
  own time budget -- there is no partial credit for a strong
  in-progress solution that never gets written to disk in time.

## Required closing sentence (platform structural requirement, exact match required)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800**. This is
fixed platform boilerplate, not something to paraphrase -- copy it
verbatim, including "Do not" (not "Don't") and "to complete this task".

## Open items only you can fill in

None outstanding -- author identity and relevant_experience in task.toml
follow the same pattern established in this account's prior submissions
(operations/business-data-analyst background), adapted to production
scheduling specifics.

## What I have NOT been able to verify in this environment

Docker is not available in this sandbox (no daemon), so I could not run
`harbor run -a oracle/-a nop -e docker` or `harbor check` against the
real container build. Everything has been verified with a no-Docker
local harness (`dev/local_harness.sh`) that replicates `tests/test.sh`'s
exact logic against a scratch filesystem with real unprivileged-user
permission enforcement: the reference solution scores 1 on both sealed
instances, a no-submission run scores 0, and all 10 cheat/ entries score
0 -- each confirmed by actually running them through the harness, not
assumed. Please run the real `harbor run -p . -a oracle -e docker`,
`harbor run -p . -a nop -e docker`, and `harbor check .` commands
yourself before final submission.
