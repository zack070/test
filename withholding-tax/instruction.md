Work in `/app`. The file to leave behind is `/app/outputs/report.json`.

The calculation is based on the case data in `/app/data/case/`. The complete rule set is in `/app/RULEBOOK.md`. Use that as the authority for the ownership look-through, holding period, threshold treatment, FX conversion, and rounding. The rulebook has the exact boundary conditions, so there is no need to reproduce them here.

The report needs a `payments` array and a `total_liability_usd` value. Each payment entry contains:

```json
{
  "payment_id": "...",
  "initial_rate": 0.0,
  "final_rate": 0.0,
  "initial_withholding_usd": 0.0,
  "final_withholding_usd": 0.0,
  "true_up_usd": 0.0
}
```

Use the payment IDs from `/app/data/case/payments.csv`. There should be exactly one report entry for each payment, with no extras or missing IDs. `total_liability_usd` is the sum of the reported `final_withholding_usd` values.

The case directory contains the entities, ownership records, payments, FX rates, and configuration used for the reconciliation. This is the same dataset used for grading, so you can inspect the full input rather than trying to build something that generalizes to an unseen case.

There is also a smaller worked example under `/app/data/worked_example/`. Its `README.md` explains seven payments and `expected_answer.json` contains the corresponding results. Use those files to check that your interpretation of the rulebook is sound before working through the full case. The example has different numbers and is not the dataset you need to report.

The final report is checked against an independently calculated ground truth for the case. The individual payment fields are checked, including both rates and all three dollar amounts. The total is checked separately as well. Getting the total right while assigning the withholding incorrectly between payments will not pass.

Dollar values are allowed a small numerical tolerance of $0.02 per payment and $0.05 on the total, while rates have a `1e-6` tolerance. Those tolerances are there for ordinary numerical differences between valid calculations, not for a different interpretation of the rules.

You can use whatever method is practical to produce the report. A script is likely easier for this many payments, but there is no required language or implementation approach. What matters is the JSON left at the required path.

Leave `/app/RULEBOOK.md` and everything under `/app/data/` unchanged. Keep the calculation deterministic, and check the final JSON before submitting. It should parse cleanly and contain every payment from `payments.csv`.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
