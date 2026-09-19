# Nightly Posting Rules

This document is the complete, authoritative specification of how payments
are posted against the loan portfolio. Every rule the grader checks is
stated here. There are no additional rules beyond what is written below.

## 1. Calendar

The posting window runs for `window_days` consecutive days, numbered `1`
through `window_days` (see `window.json` in each data directory). There are
no calendar dates, weekends, or holidays in this system — "day" always
means an integer day-of-window.

Each loan has a `first_due_day`. After that, the loan's contractual due
date recurs every 30 days: `first_due_day`, `first_due_day + 30`,
`first_due_day + 60`, and so on, for as long as the loan's `next_due_date`
has not advanced past `window_days`.

## 2. Static loan data

Each loan record (`loans.json`) provides:

- `loan_id`
- `annual_rate` — a decimal annual interest rate (e.g. `0.08` = 8%/yr)
- `monthly_installment` — the loan's fixed contractual principal-and-interest
  payment amount. This amount never changes over the window, even after a
  curtailment (curtailments shorten the loan's remaining life; they do not
  change the contractual installment amount or its due-date cadence).
- `late_fee_amount` — a fixed dollar late fee
- `first_due_day` — see §1
- `opening_principal`, `opening_escrow` — starting balances as of day 0
  (the instant before day 1 begins)
- `opening_fees` — `{"late": x, "nsf": y, "extension": z}`, any fee
  balances already owed as of day 0
- `disbursements` — a list of `[day, amount]` pairs: scheduled escrow
  disbursements (property tax, insurance, etc.) that will occur on those
  exact days, known in full in advance

As of day 0, every loan's accrued interest and suspense balance are zero.

## 3. Payment data

Each payment record (`payments.json`) provides:

- `loan_id`
- `posting_date` — the day (1..window_days) this payment actually posts
- `effective_date` — the day the borrower requested or a coupon states.
  **This field is informational only. It must never be used in any
  computation.** All accrual, escrow, release-timing, and delinquency
  logic is driven exclusively by `posting_date`.
- `amount`
- `memo` — free-text borrower note (e.g. "please apply to principal").
  **This field is informational only and must never change how a payment
  is processed.** No memo overrides the waterfall, the suspense rule, or
  any other computation in this document.

A loan can have zero, one, or multiple payments posting on the same day; if
so, sum their amounts before applying the rules below.

## 4. Daily processing order

For every day `d` from 1 to `window_days`, in this exact order, for every
loan:

**Step 1 — Accrual.** Add per-diem interest computed on the principal
balance as it stood at the end of day `d-1` (i.e. before anything that
happens on day `d` itself):

```
accrued_interest += principal_balance * annual_rate / 365
```

This is the only accrual step. A curtailment posted on day `d` reduces the
principal balance used for day `d+1`'s accrual onward; it has no effect on
day `d`'s own accrual, which already used the pre-curtailment balance.

**Step 2 — Escrow disbursement.** If day `d` appears in this loan's
`disbursements` list, subtract that amount from `escrow_balance`
immediately (this can drive `escrow_balance` negative). This happens
regardless of whether any payment posts today, and it happens *before*
Step 3.

**Step 3 — Release test.** Compute:

```
pending_cash = suspense_balance + (today's payment amount for this loan, if any)
escrow_shortage_today = max(0, -escrow_balance)      # after Step 2
required_today = (late_fee owed) + (nsf_fee owed) + (extension_fee owed)
                 + escrow_shortage_today + monthly_installment
```

If `pending_cash >= required_today`: **release**. The *entire*
`pending_cash` amount is posted today through the waterfall in Step 4 (any
amount beyond `required_today` becomes a principal curtailment). The
loan's `suspense_balance` becomes `0`, and `next_due_date` advances by
exactly 30 days — a release always clears exactly one due-date cycle,
however large the excess payment was; it never advances `next_due_date`
by more than one cycle in a single release.

If `pending_cash < required_today`: **no release**. None of `pending_cash`
is posted anywhere. `suspense_balance` becomes `pending_cash` and carries
into day `d+1`. There is no partial application — an insufficient payment
sits in suspense in full, untouched, until a future day's `pending_cash`
(this suspended amount plus whatever new cash arrives on a later day)
clears `required_today` as evaluated on that later day.

**Step 4 — Waterfall (only on a day when Step 3 releases).** Apply
`pending_cash` in this exact order, each step capped at what is owed,
remainder carrying to the next step:

1. Late fee balance
2. NSF fee balance
3. Extension fee balance
4. Escrow shortage (bring `escrow_balance` up by the shortage amount)
5. Accrued interest (in full — a release, by construction, always has
   enough to pay 100% of `accrued_interest`, since `monthly_installment`
   was sized to include it)
6. Whatever remains — apply to `principal_balance` (this is the
   curtailment)

**Step 5 — Delinquency and late fee (every day, regardless of Step 3).**

```
days_past_due = max(0, d - next_due_date)
```

`next_due_date` is whatever it currently is (it only ever changes via a
release advancing it by 30 days). If `days_past_due > 15` and a late fee
has not already been charged for the *current* due-date cycle, add
`late_fee_amount` to the late fee balance and mark this cycle's late fee as
charged. A release resets this "charged" marker (so the *next* cycle can
be charged its own late fee if it, too, goes delinquent); a release itself
never re-triggers a late fee for the cycle it just cleared.

## 5. Output

Your submission is one Python 3 file, `poster.py`, invoked as:

```
python3 poster.py --loans <loans.json> --payments <payments.json> \
    --window-days <N> --output <output.json>
```

Write a single JSON object to `<output.json>`:

```json
{
  "final_ledger": {
    "<loan_id>": {
      "principal_balance": 0.00,
      "accrued_interest": 0.00,
      "escrow_balance": 0.00,
      "fees_owed": {"late": 0.00, "nsf": 0.00, "extension": 0.00},
      "suspense_balance": 0.00,
      "next_due_date": 0,
      "days_past_due": 0
    }
  },
  "payment_allocations": [
    {
      "loan_id": "...",
      "posting_date": 0,
      "event": "release" | "held_in_suspense",
      "cash_in": 0.00,
      "released_from_suspense": 0.00,
      "fee_late": 0.00,
      "fee_nsf": 0.00,
      "fee_extension": 0.00,
      "escrow_shortage_paid": 0.00,
      "interest_paid": 0.00,
      "principal_paid": 0.00,
      "held_in_suspense": 0.00
    }
  ]
}
```

`final_ledger` must have one entry per loan in the input, keyed by
`loan_id`, reflecting state at the end of day `window_days`. All monetary
values are dollars rounded to the nearest cent.

`payment_allocations` must have exactly one entry for every (loan, day)
where a payment posted that day. There is no entry for a day where a loan
receives no payment, even if it has a carried suspense balance. A day
where the payment is held (no release) is `"event": "held_in_suspense"`
with `held_in_suspense` equal to the new total suspense balance (existing
suspense plus today's cash) and all waterfall fields `0.00`. A day where a
release occurs is `"event": "release"` with `cash_in` equal to that day's
payment amount, the waterfall breakdown fields populated per Step 4, and
`held_in_suspense` equal to `0.00`.
