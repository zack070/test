# Withholding tax rulebook

This is the complete, authoritative rule set for computing withholding
tax liability. Nothing needed to compute the correct answer is left out
of this document or the data files. `pipeline/engine.py` is supposed to
implement every rule below exactly, but it doesn't yet -- see
`pipeline/engine.py`'s own module docstring and `data/case/`'s
`README.md` for what that means for you.

## Data files

Each dataset directory (`data/case/`, `data/worked_example/`) contains:

- `entities.csv`: `entity_id, jurisdiction` -- every entity that appears
  anywhere as a payee or an owner.
- `ownership.csv`: `owner, owned, stake_pct, effective_from, effective_to`
  -- one row per ownership stake, valid for the half-open date interval
  `[effective_from, effective_to)` (the end date itself is NOT covered by
  that row). For any given entity, its rows never gap or overlap: at any
  date, at most one row covers that entity as the `owned` party.
- `payments.csv`: `payment_id, payee, amount, currency, payment_date,
  acquisition_date`.
- `fx_rates.csv`: `currency, year, month, rate_to_usd` -- exactly one
  rate per currency per calendar month.
- `config.json`: `statutory_rate`, `treaty_partners` (a map of
  jurisdiction -> treaty rate; a jurisdiction absent from this map has no
  treaty), `threshold_usd`, `holding_period_days`.

## Payer

All payments are made by the same payer, a single fixed home
jurisdiction. The payer's own jurisdiction never appears in the data and
is never itself a payee or an owner.

## Relevant parent (ownership look-through)

To determine which jurisdiction governs a payment's treaty eligibility,
resolve the payee's **relevant parent as of that payment's own date**
(not once for the payee as a whole -- ownership stakes can change during
the year, and a payment must be evaluated using the ownership structure
in effect on its own date):

1. Look up the payee's ownership row covering that date (the row where
   `effective_from <= payment_date < effective_to`).
2. If no such row exists, the payee itself is the relevant parent. Stop.
3. If the row's `stake_pct` is **greater than 50**, the look-through
   continues: repeat this process treating the owner as the new payee.
4. If the row's `stake_pct` is **50 or less**, the look-through stops
   here: the owner in that row is the relevant parent (not the entity
   being evaluated, and not anyone further up the chain). Stop.

The relevant parent's jurisdiction is looked up in `treaty_partners`. If
it is absent, the statutory rate applies to this payment regardless of
holding period, and the holding-period test (below) is never reached.

## Holding period test

`holding_days = (payment_date - acquisition_date)`, in whole calendar
days. The test is satisfied if and only if `holding_days >=
holding_period_days` (exactly `holding_period_days` days qualifies).

## Base rate

If the relevant parent's jurisdiction is a treaty partner AND the
holding period test is satisfied: the base rate is that jurisdiction's
treaty rate. Otherwise: the base rate is `statutory_rate`.

## Cumulative annual threshold (retroactive re-rating)

Group payments by `(payee, calendar year of payment_date)` -- years
never combine across payees or across each other. For each group, sum
every payment's USD-converted amount (see Currency conversion below). If
that sum is **strictly greater than** `threshold_usd` (a sum exactly
equal to the threshold does not trigger this), every payment in that
group -- including the one that pushed the sum over the threshold, and
including any already computed at a treaty rate -- has its **final
rate** set to `statutory_rate`, overriding its base rate. If the sum
does not exceed the threshold, each payment's final rate equals its base
rate.

## Currency conversion

Convert `amount` to USD using the rate for the calendar month (year and
month) containing `payment_date`. This is the rate used both for the
cumulative threshold sum above and for the reported USD figures below.

## Reported figures

For each payment:
- `initial_withholding_usd` = USD amount x base rate
- `final_withholding_usd` = USD amount x final rate
- `true_up_usd` = `final_withholding_usd` - `initial_withholding_usd`

And one grand total: `total_liability_usd` = sum of every payment's
`final_withholding_usd`.

Carry full floating-point precision through every intermediate step.
Round only the four reported figures above (the three per-payment
figures and the grand total), to 2 decimal places, standard round-half-up,
as the very last step -- never round an intermediate value and use the
rounded value in a further computation.

## Worked example

See `data/worked_example/README.md` for seven rule behaviors across nine
fully-explained payments covering every rule above, with the correct
answer shown in `data/worked_example/expected_answer.json`.
