# Cash-sweep simulator contract

`simulator.py` is the complete, authoritative implementation of how a
trading day plays out. This document explains it in prose; where the two
differ, the code is correct (report it as a bug if you find a
difference). Nothing about how the simulator works is hidden from you.

## Time and entities

Time is in integer minutes. A day runs from minute 0 to `horizon` (the
scenario data gives this).

Each **currency** has one account, holding a single non-negative balance.
There is no overdraft: a transfer can never draw more than a currency's
current balance.

A **credit** has: an id, a currency, an amount, and an arrival time. The
instant it arrives, its amount is added directly to that currency's
balance.

An **obligation** has: an id, a currency, an amount, a due time, and an
arrival time. It becomes visible to your policy at its arrival time. By
its due time, that much of that currency's balance must be available, or
the obligation is recorded as missed. There is no partial credit: an
obligation is either fully covered by its due time or it is a miss.

A **currency pair** (ordered: A->B need not exist or cost the same as
B->A) may have a market: a cheap rate, an expensive rate, and a cutoff
time. A transfer on that pair initiated at or before the cutoff pays the
cheap rate; after the cutoff, the expensive rate. Not every ordered pair
of currencies necessarily has a market at all.

## Your policy

You submit a Python module exposing:

```python
def decide(state) -> list[tuple[str, str, float]]:
    ...
```

`state` has:
- `current_time`
- `balances`: every currency's current balance, as `(currency, balance)` pairs
- `pending_obligations`: every obligation that has arrived and is not yet
  resolved (met or missed), each exposing `obligation_id`, `currency`,
  `amount`, `due_time`, `arrival_time`
- `currencies`: every currency that exists in this scenario
- `spread_cheap`, `spread_expensive`: every tradeable pair's two rates, as
  `(from_currency, to_currency, rate)` triples
- `cutoff_time`: every tradeable pair's cutoff, as `(from_currency,
  to_currency, cutoff)` triples

The rate/cutoff schedule is static for the whole day and is resent, in
full, on every call -- it is never something you need to remember across
calls or look up anywhere else.

`decide` returns a list of `(from_currency, to_currency, amount)` triples:
transfer `amount` of `from_currency`'s balance into `to_currency`'s
account. Returning `[]` means "do nothing right now." Multiple transfers
drawing on the same source currency in one call are all honored, in
order, against a balance that decrements as each is applied -- only
actually running out of money blocks a later one in the same batch, not
merely naming the same currency twice. A transfer naming the same
currency as both source and destination, a non-positive amount, a
currency not in this scenario, a pair with no market, or an amount
exceeding the source's balance at that point in the batch is silently
dropped -- it does not raise an error, and the underlying balances are
left exactly as they were for that one dropped transfer.

A transfer moves `amount` into the destination at par (1:1); the spread
rate is charged separately, as a cost, and does not reduce what arrives.

`decide` is called whenever a credit lands, whenever an obligation
becomes known, and whenever any currency pair's cutoff passes -- but only
when at least one obligation is currently pending. There is no other way
to be notified that time has passed.

## Cost (lower is better; this is what you are scored on)

```
total_cost = (number of obligations missed) * 200
           + (sum of amount * applicable_rate over every transfer executed)
```

There is no reward for holding balances idle and no separate reward for
using a particular currency; the only things that cost anything are
missed obligations and the spread paid on transfers actually executed.
