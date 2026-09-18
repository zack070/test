Work in `/app`. The file to leave behind is `/app/outputs/engine.py`.

There is already a withholding-tax pipeline in `/app/pipeline/engine.py`. It is the starting point for this task, but it is not correct. The job here is to find the problems and fix the pipeline rather than write a new report by hand. `/app/RULEBOOK.md` is the authority for what the finished pipeline is supposed to calculate.

The version you submit needs to keep the existing `run(data_dir) -> dict` interface working. It must also remain runnable as:

`python3 engine.py <data_dir> <output_path>`

The returned or written report has this shape:

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

The payment list needs one entry for every payment in the dataset being processed, with no missing or extra IDs. The total is the sum of the reported `final_withholding_usd` values.

The engine's module docstring gives some context, but it does not tell you where the bugs are.

`/app/data/worked_example/` has nine small payments with explanations and a known `expected_answer.json`. `/app/data/case/` is a larger 109-payment dataset with its own expected answer and exposes more of the same problems. Neither dataset is the grading data, so fixing individual visible outputs or baking their answers into the code is not a substitute for fixing the underlying behavior.

The grader runs the `/app/outputs/engine.py` you submit, rather than checking in a report you generated beforehand. It runs the engine against two sealed datasets that are not available during development, with a fresh subprocess for each one. Each dataset is checked independently against its own ground truth.

The comparison is done per payment as well as on the total. Rates and the three withholding amounts for each payment are checked, along with `total_liability_usd`. The allowed differences are small: $0.02 for each dollar figure, `1e-6` for rates, and $0.05 for the total. Those tolerances cover normal floating-point differences, not a different calculation.

Keep the fixed pipeline deterministic and reasonably fast. The input data and rulebook stay in place, so the work should be confined to the submitted engine.

Leave `/app/RULEBOOK.md` and everything under `/app/data/` unchanged.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
