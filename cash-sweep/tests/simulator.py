"""
Deterministic discrete-event intraday cash-sweep simulator.

This module is the single source of truth for how a business day plays
out given a submitted transfer policy. It is copied byte-identical into
environment/sim/ (agent visible, full source, nothing hidden) and tests/
(hidden verifier, run against the sealed held-out scenario).

Model, deliberately lean:
  - One account per currency; credits land directly in their currency's
    account, obligations draw directly from their currency's account at
    due_time. No partial funding: an obligation is either fully covered
    by its due_time or it is a miss, at a fixed penalty. No settlement
    latency, no overdraft interest.
  - A transfer converts `amount` of one currency's balance into another
    currency's account at par (1:1), plus a separate spread FEE charged
    in total_cost -- the fee does not reduce what arrives at the
    destination, it is booked purely as a cost. Every ordered currency
    pair has its own spread, asymmetric (A->B need not cost the same as
    B->A), and its own cutoff time: a transfer initiated at or before the
    pair's cutoff pays the cheap rate, after it pays the expensive rate.
  - decide() is called whenever a credit lands, whenever an obligation
    becomes known, and whenever any currency pair's same-day cutoff
    passes -- the last one because the achievable cost structure itself
    changes at that instant, the direct analog of a technician becoming
    free changing what's assignable. It is never called on a scheduled
    reminder with no real-world referent. It is only called when at
    least one obligation is currently pending (arrived, not yet
    resolved) -- with nothing to fund, there is nothing to decide.
  - decide() may return several transfers in one call, including more
    than one drawn on the same source currency (a balance can legitimately
    fund several simultaneous wires) -- they are applied in the order
    returned against a balance that decrements as each is applied, so only
    actually running out of money blocks a later one.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

MISS_PENALTY = 200.0


@dataclass
class CreditSpec:
    credit_id: str
    currency: str
    amount: float
    arrival_time: int


@dataclass
class ObligationSpec:
    obligation_id: str
    currency: str
    amount: float
    due_time: int
    arrival_time: int


@dataclass
class ObligationState:
    obligation_id: str
    currency: str
    amount: float
    due_time: int
    arrival_time: int
    status: str = "not_arrived"  # not_arrived -> pending -> met | missed


@dataclass(frozen=True)
class ObligationSnapshot:
    obligation_id: str
    currency: str
    amount: float
    due_time: int
    arrival_time: int


@dataclass(frozen=True)
class SimState:
    current_time: int
    balances: Tuple[Tuple[str, float], ...]           # (currency, balance) pairs, every currency
    pending_obligations: Tuple[ObligationSnapshot, ...]
    # Market data is public and static for the whole day -- baked into
    # every call's own state rather than left for the policy to read from
    # a separate file. A held-out grading run's decide() executes in a
    # separate, unprivileged process (see the two-stage verifier); if the
    # rate/cutoff schedule instead lived only in a file on disk, that
    # process would share the same UID as whatever trusted code read it
    # and could simply open() it directly. Repeating a few dozen floats on
    # every call is cheap; a filesystem channel a same-UID process can
    # reach is not something to reopen once it's been closed elsewhere.
    currencies: Tuple[str, ...]
    spread_cheap: Tuple[Tuple[str, str, float], ...]      # (from, to, rate) before cutoff
    spread_expensive: Tuple[Tuple[str, str, float], ...]  # (from, to, rate) after cutoff
    cutoff_time: Tuple[Tuple[str, str, int], ...]          # (from, to, cutoff)


@dataclass
class SimResult:
    total_cost: float
    num_missed: int
    num_obligations: int
    total_spread_cost: float
    log: List[str] = field(default_factory=list)
    decision_trace: List[List[Tuple[str, str, float]]] = field(default_factory=list)


TransferAction = Tuple[str, str, float]  # (from_currency, to_currency, amount)
PolicyFn = Callable[[SimState], List[TransferAction]]


def make_replay_policy(trace: List[List[TransferAction]]) -> PolicyFn:
    """Mechanically replays a recorded decision trace instead of computing
    anything -- used by the trusted verifier stage to re-derive a
    candidate's result without executing any of its code."""
    state = {"i": 0}

    def _policy(_state: SimState) -> List[TransferAction]:
        i = state["i"]
        state["i"] += 1
        if i >= len(trace):
            return []
        return trace[i]

    return _policy


def run_simulation(
    currencies: List[str],
    spread_cheap: Dict[Tuple[str, str], float],
    spread_expensive: Dict[Tuple[str, str], float],
    cutoff_time: Dict[Tuple[str, str], int],
    starting_balances: Dict[str, float],
    credits: List[CreditSpec],
    obligations: List[ObligationSpec],
    horizon: int,
    policy_fn: PolicyFn,
    max_events: int = 100_000,
) -> SimResult:
    currencies_t = tuple(currencies)
    spread_cheap_t = tuple(sorted((frm, to, rate) for (frm, to), rate in spread_cheap.items()))
    spread_expensive_t = tuple(sorted((frm, to, rate) for (frm, to), rate in spread_expensive.items()))
    cutoff_time_t = tuple(sorted((frm, to, t) for (frm, to), t in cutoff_time.items()))

    balances: Dict[str, float] = {c: starting_balances.get(c, 0.0) for c in currencies}
    obligation_states: Dict[str, ObligationState] = {
        o.obligation_id: ObligationState(
            obligation_id=o.obligation_id, currency=o.currency, amount=o.amount,
            due_time=o.due_time, arrival_time=o.arrival_time,
        )
        for o in obligations
    }
    credit_map = {c.credit_id: c for c in credits}

    events: List[Tuple[int, int, str, str]] = []
    seq = 0
    for c in credits:
        heapq.heappush(events, (c.arrival_time, seq, "credit", c.credit_id)); seq += 1
    for o in obligations:
        heapq.heappush(events, (o.arrival_time, seq, "obligation_arrival", o.obligation_id)); seq += 1
        heapq.heappush(events, (o.due_time, seq, "obligation_due", o.obligation_id)); seq += 1
    seen_cutoffs = set()
    for pair, t in cutoff_time.items():
        if t not in seen_cutoffs:
            heapq.heappush(events, (t, seq, "cutoff", "")); seq += 1
            seen_cutoffs.add(t)
    heapq.heappush(events, (horizon, seq, "horizon", "")); seq += 1

    log: List[str] = []
    decision_trace: List[List[TransferAction]] = []
    total_spread_cost = 0.0
    num_missed = 0
    events_processed = 0

    def pending_snapshot() -> Tuple[ObligationSnapshot, ...]:
        return tuple(
            ObligationSnapshot(s.obligation_id, s.currency, s.amount, s.due_time, s.arrival_time)
            for s in obligation_states.values()
            if s.status == "pending"
        )

    while events and events_processed < max_events:
        now, _, kind, payload = heapq.heappop(events)
        events_processed += 1

        if kind == "credit":
            c = credit_map[payload]
            balances[c.currency] = balances.get(c.currency, 0.0) + c.amount
            log.append(f"t={now}: CREDIT {c.credit_id} +{c.amount:.1f} {c.currency}")

        elif kind == "obligation_arrival":
            s = obligation_states[payload]
            if s.status == "not_arrived":
                s.status = "pending"

        elif kind == "obligation_due":
            s = obligation_states[payload]
            if s.status == "pending":
                if balances.get(s.currency, 0.0) >= s.amount - 1e-9:
                    balances[s.currency] -= s.amount
                    s.status = "met"
                    log.append(f"t={now}: PAID {s.obligation_id} {s.amount:.1f} {s.currency}")
                else:
                    s.status = "missed"
                    num_missed += 1
                    log.append(
                        f"t={now}: MISS {s.obligation_id} needed {s.amount:.1f} {s.currency} "
                        f"had {balances.get(s.currency, 0.0):.1f}"
                    )

        elif kind == "cutoff":
            pass  # pure decision checkpoint; the cost structure just shifted

        elif kind == "horizon":
            pass

        pending = pending_snapshot()
        if pending:
            state = SimState(
                current_time=now,
                balances=tuple(sorted(balances.items())),
                pending_obligations=pending,
                currencies=currencies_t,
                spread_cheap=spread_cheap_t,
                spread_expensive=spread_expensive_t,
                cutoff_time=cutoff_time_t,
            )
            transfers = policy_fn(state)
            decision_trace.append(list(transfers))
            # Multiple transfers drawing on the same source currency in one
            # response are all honored, in order, against a balance that
            # decrements as each is applied -- a real balance can legitimately
            # fund several simultaneous wires; only actually running out of
            # money should block a later one, not merely having named the
            # same currency twice.
            for from_cur, to_cur, amount in transfers:
                if from_cur == to_cur or amount <= 0:
                    continue
                if from_cur not in currencies or to_cur not in currencies:
                    continue
                if balances.get(from_cur, 0.0) < amount - 1e-9:
                    continue  # illegal (insufficient funds at this point in the batch) -- silently dropped
                pair = (from_cur, to_cur)
                if pair not in cutoff_time:
                    continue  # no market for this pair -- silently dropped
                cutoff = cutoff_time[pair]
                rate = spread_cheap[pair] if now <= cutoff else spread_expensive[pair]
                balances[from_cur] -= amount
                balances[to_cur] = balances.get(to_cur, 0.0) + amount
                cost = amount * rate
                total_spread_cost += cost
                log.append(f"t={now}: TRANSFER {amount:.1f} {from_cur}->{to_cur} rate={rate:.4f} cost={cost:.2f}")

    total_cost = num_missed * MISS_PENALTY + total_spread_cost
    return SimResult(
        total_cost=total_cost,
        num_missed=num_missed,
        num_obligations=len(obligations),
        total_spread_cost=total_spread_cost,
        log=log,
        decision_trace=decision_trace,
    )
