# Fact sheet for instruction.md (withholding-tax, v2 -- debugging shape)

This is a fact sheet, not instruction.md prose -- use it as source material
to write instruction.md yourself. Facts only; no narrative framing implied.

**The task shape changed completely since the last version.** The
previous instruction.md (deliverable: a computed report.json) is gone --
it would actively mislead if reused, since the new task is "find and fix
bugs in a given pipeline," not "compute a report from a spec." Write
this one from scratch using the facts below, not by editing the old one.

## Submission

- Work in `/app`. The file to leave behind is `/app/outputs/engine.py`
  -- your fixed version of `/app/pipeline/engine.py`.
- `/app/pipeline/engine.py` is supposed to implement `/app/RULEBOOK.md`
  exactly, but it has real bugs. It's given as a starting point, not a
  reference to leave untouched -- the whole task is fixing it.
- Required interface: a top-level `run(data_dir) -> dict` function
  (returning the report structure below), invokable as a script:
  `python3 engine.py <data_dir> <output_path>`. The given pipeline
  already has both; keep them working after your fix.
- Report structure `run()` must return / the script must write as JSON:
  ```json
  {
    "payments": [
      {
        "payment_id": "...",
        "initial_rate": 0.0,
        "final_rate": 0.0,
        "initial_withholding_usd": 0.0,
        "final_withholding_usd": 0.0,
        "true_up_usd": 0.0
      }
    ],
    "total_liability_usd": 0.0
  }
  ```
  One entry per payment_id in the dataset it's run against, no extras or
  missing IDs. `total_liability_usd` = sum of every payment's
  `final_withholding_usd`.

## Reference material available to the agent

- `/app/RULEBOOK.md` -- the complete, authoritative rule set. Same
  content as before, still fully precise on every boundary condition.
- `/app/pipeline/engine.py` -- the given pipeline, with its own module
  docstring explaining what it's for and that it has bugs (without
  naming them -- that's the agent's job to find).
- `/app/data/worked_example/` -- nine small, fully-explained payments
  (seven rule behaviors) with the correct answer shown
  (`expected_answer.json`, explained in `README.md`). Running the given
  pipeline against this reveals 2 of the 9 payments disagree with the
  shown correct answer -- this is the intended way to discover that
  something's wrong before diving into the full case dataset.
- `/app/data/case/` -- a larger (109-payment) practice dataset, also
  with a shown correct answer (`expected_answer.json`, explained in its
  own `README.md`). Running the unfixed pipeline against this gets 21 of
  109 payments wrong (total off by ~9%). This is NOT the graded dataset.

## Grading structure

- Grading runs the agent's own submitted `/app/outputs/engine.py` (not
  a report file) against TWO sealed held-out datasets the agent never
  sees, once each, as a fresh subprocess per dataset.
- Each dataset is checked against its own ground truth independently --
  not averaged -- so a fix that only happens to work for one dataset's
  particular mix of bug manifestations doesn't pass by coasting on the
  other.
- Comparison is per-payment (both rates, both withholding amounts, the
  true-up) plus the total, with small absolute tolerance (0.02 USD per
  dollar figure, 1e-6 on rates, 0.05 USD on the total) for legitimate
  floating-point differences -- not for a different interpretation of
  the rules. A fix that only works by memorizing the visible datasets'
  answers will not pass; see cheat/README.md's "memorized visible
  answers" case for the measured proof.

## Constraints

- Leave `/app/RULEBOOK.md` and everything under `/app/data/` unchanged.
- Keep the fixed pipeline deterministic and reasonably fast (grading
  gives each dataset its own timeout; don't add expensive work that
  wasn't already there).
- Before submitting, run your fixed engine.py against both the worked
  example and the case dataset and confirm it matches their shown
  answers exactly, not just approximately.

## Required closing sentence (platform structural requirement, easy to miss)

Per the authoring guide: instruction.md must end with a blank line, then
**exactly** this sentence, verbatim, where N is the integer value of
`[agent].timeout_sec` in task.toml, then at most one trailing newline:

    You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This task's `[agent].timeout_sec` is `10800.0`, so N = **10800**.

## What changed since the last version, and why

Quality review rejected the previous version on two blocking criteria:
"typos" (wrong entity IDs in the worked example, a stale repo-relative
path, a stale payment count -- all now fixed in the shipped data/docs)
and, more importantly, "difficult" -- the reviewer's finding was that a
fully-specified rulebook plus a worked example covering every rule
reduces the whole task to "read the spec carefully, implement it,"
which isn't genuine difficulty. Rather than patch that version's rules
(which wouldn't have fixed a genre-level problem), the task is rebuilt
around debugging a given, realistically-buggy pipeline instead of
writing one from a spec -- see task.toml's `difficulty_explanation` for
the full reasoning and measured numbers.

## Open items only you can fill in (task.toml)

None outstanding -- author identity and relevant_experience carried over
and adapted from the prior version, same as before.
