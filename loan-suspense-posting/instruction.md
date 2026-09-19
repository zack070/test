Work in `/app`. The file to leave behind is `/app/outputs/poster.py`.

The program needs to run as:

`python3 poster.py --loans <loans.json> --payments <payments.json> --window-days <N> --output <output.json>`

The output is one JSON object with `final_ledger` and `payment_allocations`. The exact structure for both is defined in section 5 of `/app/SERVICING_SPEC.md`. Follow that schema exactly.

There are two things being checked in the output. `final_ledger` needs one entry for every `loan_id` in the supplied loans file, with no extras. `payment_allocations` is different: it should contain one entry for each `(loan, posting day)` on which a payment actually posted. A loan carrying suspense from an earlier day does not create an allocation entry on later days where no payment was posted.

`/app/SERVICING_SPEC.md` is the source of truth for the servicing rules. Read it closely before implementing anything. It defines the calendar convention, actual/365 daily interest, the order of escrow disbursement and release testing, the suspense and hold-until-full-installment behaviour, the payment waterfall, and the once-per-cycle late-fee rule. There is no second hidden convention for these mechanics.

Pay particular attention to the payment fields. `posting_date` is the date that controls accrual, release timing, and delinquency. `effective_date` is explicitly non-authoritative and must not change any calculation. `memo` is also non-authoritative free text. It must not override the waterfall or suspense behaviour.

This is a simulation, not an optimization problem. For a given input there is one correct ledger and one correct payment-allocation trace. The implementation should reproduce the rules in the servicing specification rather than trying to choose among possible outcomes.

There is a small worked example under `/app/data/worked_example/`. It has two loans over 45 days, and its README goes through the calculations by hand. Use that to check the implementation and the allocation trace before moving on to larger data. `/app/data/case/` is an 80-loan, 75-day practice portfolio in the same general format as the graded input. Its README makes clear that it is practice data, not the sealed grading portfolio.

The grader will run the submitted `poster.py` as a fresh subprocess on one sealed portfolio. It has 80 loans over 75 days, with different generated figures and loan IDs from the visible practice case.

The ledger comparison is exact. Every monetary field, including `principal_balance`, `accrued_interest`, `escrow_balance`, `suspense_balance`, and each `fees_owed` bucket, must match the frozen reference to the cent. `next_due_date` and `days_past_due` must also match exactly.

The allocation trace is checked separately. Entries are matched by loan and posting day, then the `event` label and every monetary breakdown field are compared with the reference. Getting the final ledger right is not enough if the allocation entries are missing, duplicated, or otherwise wrong. Both checks have to pass for a score of 1. There is no partial credit.

Keep `/app/SERVICING_SPEC.md` unchanged, along with everything under `/app/data/`. The program should be deterministic and reasonably fast. The sealed run has several minutes available, although a correct reference implementation finishes in well under a second.

Before you finish, exercise the script against the worked example and the visible practice case. Check the output shape as well as the numbers. In particular, make sure every loan appears once in the final ledger and that allocation entries only exist for actual payment posting days.

You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
