Work in /app. What you're handing in is /app/outputs/poster.py, and it has to run like this:

python3 poster.py --loans <loans.json> --payments <payments.json> --window-days <N> --output <output.json>

Only two things in the output have to be right: final_ledger and payment_allocations. Section 5 of /app/SERVICING_SPEC.md gives the exact JSON structure. Read that file before you write any posting logic, because it's the actual spec for this task. Don't swap in your own interpretation of the date handling, actual/365 interest, escrow processing, suspense behaviour, payment waterfall, or the late-fee cycle rule. The order those operations happen in matters too.

A couple of the payment fields are there to trip up bad assumptions. Use posting_date everywhere in the simulation. effective_date isn't authoritative and shouldn't touch accrual, release timing, or delinquency at all. memo is just a memo, and it can't change how a payment gets posted.

For the ledger, every input loan should appear exactly once, under its loan_id. No missing loans and no made-up ones.

The allocation output follows payment postings, not every day of the simulation. If a payment posts for a loan on a given day, that loan/day needs an entry. A loan can still have suspense the next day without producing another allocation entry, as long as no payment posted that day.

There's a small test case in /app/data/worked_example/: two loans over 45 days, with a README that walks through the calculations. I'd get that matching first, then move on to /app/data/case/, the larger practice portfolio with 80 loans over 75 days. That case is only for development. The portfolio used for grading is a different one.

Grading uses a single sealed 80-loan, 75-day portfolio and starts your program as a fresh subprocess. The final ledger is compared against the reference to the cent on every monetary field: principal, interest, escrow, suspense, and each fee bucket. next_due_date and days_past_due have to match exactly.

The payment trace is checked on its own. Entries are matched by loan and posting day, and the event plus every monetary breakdown field has to agree. So correct ending balances won't rescue a bad allocation trace. Both checks have to pass.

This is a deterministic simulation. There's no optimization step, and you're not choosing a "good" policy. Given the input and the servicing rules, there's exactly one result.

Leave /app/SERVICING_SPEC.md and everything under /app/data/ unchanged. Keep the program deterministic and reasonably quick. The grading run has several minutes, so normal simulation work is fine.

Before you submit, run the worked example and the practice case, then look at the real output structure, especially the number of ledger entries and the number of payment-day allocation entries. Those are separate parts of the answer, and they're graded separately.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
