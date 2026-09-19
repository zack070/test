Work in `/app`. Your submission is `/app/outputs/poster.py`.

The grader will call it like this:

`python3 poster.py --loans <loans.json> --payments <payments.json> --window-days <N> --output <output.json>`

The script must produce one JSON object. It needs the two top-level fields `final_ledger` and `payment_allocations`, using the exact formats described in section 5 of `/app/SERVICING_SPEC.md`. Both parts matter.

For `final_ledger`, include every loan from the input exactly once, keyed by its `loan_id`. Do not add loans that were not supplied. The allocation list follows a different rule. There should be one allocation record for each loan and posting day where a payment was actually posted. If a loan has money sitting in suspense, that does not by itself create another allocation record on a later day.

Most of the work is in the servicing rules. `/app/SERVICING_SPEC.md` is the authority for them, so use that file rather than making assumptions about how a loan system normally behaves. It covers the date convention, daily interest using actual/365, escrow disbursements and release checks, suspense handling, the hold-until-full-installment rule, the payment waterfall, and the late-fee cycle rule. The grader follows those details.

There are two payment fields that are deliberately irrelevant. Use `posting_date` for the simulation. Do not use `effective_date` for accrual, release timing, or delinquency calculations. Treat `memo` as ordinary display text. It has no effect on the waterfall or on whether a payment is held in suspense.

This is not a search for a good policy or an optimization exercise. Given the input and the rules, the result is fixed. The implementation needs to simulate the events in the specified order and record the resulting ledger and payment allocations.

Start with `/app/data/worked_example/` while developing. It contains two loans over a 45-day period, and the README works through the figures manually. The numbers there are useful for checking both the ending balances and the payment records. The larger material in `/app/data/case/` is an 80-loan, 75-day practice portfolio. It has the same general data shape as the grading input, but it is not the portfolio used for grading.

The real test uses one sealed portfolio with 80 loans and 75 days. Its loan IDs and generated figures differ from the visible case. The program is launched in a fresh subprocess with a firm timeout.

The final ledger is compared against a frozen reference. Monetary values such as `principal_balance`, `accrued_interest`, `escrow_balance`, `suspense_balance`, and every bucket under `fees_owed` must agree to the cent. `next_due_date` and `days_past_due` must agree exactly as well.

The grader also checks `payment_allocations` on its own. It matches records by loan and posting day, then checks the `event` value and every monetary breakdown field. A correct ending ledger will still fail if the allocation trace has a missing day, an extra record, duplicate entries, or incorrect amounts. Both comparisons must pass. There is no partial score.

Leave `/app/SERVICING_SPEC.md` and all files under `/app/data/` alone. The script should give the same result every time for the same inputs and should not spend excessive time processing the portfolio. Several minutes are available for the sealed run, though the reference implementation is much faster than that.

Use the worked example and practice case to test the script before submitting. Check the JSON structure too, not just the balances. The final ledger must cover every input loan once, and allocation records belong only to days on which that loan received a posted payment.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
