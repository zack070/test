Work in `/app`. The only file you need to leave as the submission is:

`/app/outputs/poster.py`

The command-line interface matters. The grader will invoke the program in this form:

`python3 poster.py --loans <loans.json> --payments <payments.json> --window-days <N> --output <output.json>`

The output file is one JSON object containing `final_ledger` and `payment_allocations`. Section 5 of `/app/SERVICING_SPEC.md` has the exact shape. Use that rather than guessing at field names or nesting.

The main reference for the actual loan servicing behaviour is `/app/SERVICING_SPEC.md`. Read the whole thing before coding. This isn't a case where you need to invent a reasonable posting system. The date rules, actual/365 accrual, escrow processing, suspense handling, installment release test, waterfall and late-fee behaviour are all spelled out there, including the order in which things happen.

One easy trap is the payment data. `posting_date` is the date that counts. `effective_date` is not used for accrual, release timing, or delinquency. `memo` is just text. Don't let either field sneak into the calculations.

I'd use the small example first. `/app/data/worked_example/` has two loans and a 45-day window, plus a README that works through the arithmetic and gives you figures to compare against. It is much easier to find an accrual or posting-order bug there than after running the larger case. There is also `/app/data/case/`, an 80-loan, 75-day practice portfolio. That one is useful for exercising the script at a more realistic size, but it is still only practice data.

The output has two separate jobs.

`final_ledger` needs exactly one record for every `loan_id` in the input. Nothing extra, nothing missing.

`payment_allocations` is based on actual payment posting days. If loan 17 gets a payment on day 12, there should be an allocation entry for that loan/day. If it has suspense sitting on the account on day 13 but no payment posts that day, there is no new allocation entry for day 13. This distinction is checked.

The sealed test uses another 80-loan, 75-day portfolio. You won't see its figures or loan IDs. Your program is run as a fresh subprocess, so it needs to work from the supplied files and arguments rather than relying on anything outside the task.

The final ledger is compared field by field with the frozen result. Monetary fields are required to match to the cent, including principal, accrued interest, escrow, suspense and every `fees_owed` bucket. `next_due_date` and `days_past_due` have to match exactly.

The payment trace gets its own comparison. For each loan/posting-day entry, the grader checks the `event` and all of the monetary breakdown fields. So don't treat the allocation list as something you can reconstruct loosely from the final balances. A correct ledger with a wrong or incomplete trace still gets a zero.

There isn't any optimization here. Don't spend time looking for a "better" posting outcome. Once the servicing rules and input are fixed, the ledger and allocation trace are fixed too.

Leave `/app/SERVICING_SPEC.md` and everything below `/app/data/` untouched. Keep the program deterministic. Runtime shouldn't be an issue for a normal implementation; the reference finishes in well under a second, while the sealed run allows several minutes.

Before calling it done, run the worked example and the practice case yourself. Check the actual JSON as well as the balances. Missing allocation rows are easy to overlook.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
