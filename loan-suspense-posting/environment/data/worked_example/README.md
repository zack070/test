# Worked example

Two loans, a 45-day window. Walk this through by hand against
`SERVICING_SPEC.md` to confirm you understand the rules before running
anything against the full case data.

## Loan W001

`annual_rate=0.08`, `monthly_installment=400.00`, `late_fee_amount=25.00`,
`first_due_day=10`, `opening_principal=20000.00`, `opening_escrow=100.00`,
no opening fees, one disbursement of `300.00` on day 20.

Payments: `150.00` posting day 10, `300.00` posting day 18.

- Days 1-9: no payments. Interest accrues daily on 20000.00 at 0.08/365 =
  4.383562/day.
- Day 10: accrued_interest reaches 43.835616 (10 days). A payment of
  150.00 arrives. `pending_cash = 0 + 150 = 150`. `escrow_shortage = 0`
  (escrow is still +100, no disbursement yet). `required = 0 + 0 + 400 =
  400`. `150 < 400` -> held in suspense. `suspense_balance = 150.00`.
- Days 11-17: no payments. Interest keeps accruing on the unchanged
  20000.00 principal (no release has happened yet).
- Day 18: accrued_interest reaches 78.904110 (18 days of accrual). A
  payment of 300.00 arrives. `pending_cash = 150 + 300 = 450`.
  `escrow_shortage = 0` still (disbursement is day 20, hasn't happened
  yet). `required = 400`. `450 >= 400` -> **release**. Waterfall: no fees,
  no escrow shortage, pay accrued_interest in full (78.904110), remainder
  `450 - 78.904110 = 371.095890` to principal. New
  `principal_balance = 20000 - 371.095890 = 19628.904110` ->
  **19628.90**. `accrued_interest -> 0.00`. `suspense_balance -> 0.00`.
  `next_due_date` advances from 10 to **40**.
- Day 20: the scheduled disbursement fires: `escrow_balance = 100 - 300 =
  -200.00`. No payment posts this day, so nothing else happens (this
  shortage sits unresolved for the rest of the window, since no further
  payment for W001 falls in this example).
- Days 19-45 (27 days): interest accrues on the new principal balance of
  19628.904110 at 0.08/365 = 4.302825/day, compounding day by day on the
  unchanged post-release principal (no further curtailment occurs), for a
  total of `116.16`.
- End of window (day 45): `next_due_date = 40`, so
  `days_past_due = max(0, 45-40) = 5` — under the 15-day grace period, so
  no late fee. `escrow_balance = -200.00` (never resolved in this
  example). `fees_owed` all zero.

Expect exactly: `principal_balance = 19628.90`,
`accrued_interest = 116.16`, `escrow_balance = -200.00`,
`suspense_balance = 0.00`, `next_due_date = 40`, `days_past_due = 5`.

## Loan W002

`annual_rate=0.06`, `monthly_installment=250.00`, `first_due_day=10`,
`opening_principal=12000.00`, `opening_escrow=500.00`, no disbursements.
Payments: `250.00` posting day 10 (full), `250.00` posting day 40
(`effective_date=39`, but `posting_date=40` is what governs everything).

Both payments fully cover `required_today` (no fees, no escrow shortage,
exactly the installment amount) the moment they post, so each is an
immediate release with no suspense involved. Each release pays that
cycle's full accrued interest and curtails the rest to principal, and
advances `next_due_date` by 30 days (10 -> 40 -> 70). By day 45,
`next_due_date = 70`, so `days_past_due = 0` (not yet due).

Run `solution/poster.py` (or your own implementation) against
`loans.json` / `payments.json` in this directory with `window_days = 45`
(see `window.json`) and confirm your output matches the figures above to
the cent.
