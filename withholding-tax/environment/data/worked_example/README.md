# Worked example

Seven rule behaviors across nine payments, with the correct answer shown
in `expected_answer.json`. Currency is USD throughout (rate 1.0) so the
numbers below aren't obscured by FX conversion. This is a teaching
example, not the graded dataset -- use it to check your understanding of
the rules (and to reproduce some of the given pipeline's bugs on a small
scale) before working through `/app/data/case/`.

- **PAY0001** (payee ENT0001, jurisdiction JUR-DE, no owner on record,
  acquired 2022-01-01, paid 2024-06-01): JUR-DE is a treaty partner, the
  payee has no owner so it is its own relevant parent, and the holding
  period (2022-01-01 to 2024-06-01, well over 365 days) is satisfied.
  Treaty rate (10%) applies. `10,000.00`.

- **PAY0002** (ENT0002, JUR-KY, no owner): JUR-KY is not a treaty
  partner. Statutory rate (30%) applies regardless of holding period.
  `30,000.00`.

- **PAY0003** (ENT0003, JUR-DE, no owner, acquired 2024-01-01, paid
  2024-06-01): JUR-DE is a treaty partner, but the holding period is
  only 152 days -- under 365. Statutory rate applies. `30,000.00`.

- **PAY0004** (ENT0004, JUR-SG, owned 80% by an entity in JUR-KY): the
  payee's own jurisdiction (JUR-SG, a treaty partner) is never
  consulted, because the payee has an owner. That owner's stake is 80%,
  over 50%, so the look-through continues to the owner; the owner has no
  further owner on record, so the owner itself is the relevant parent.
  The owner's jurisdiction is JUR-KY -- no treaty. Statutory rate
  applies. `30,000.00`.

- **PAY0005** (payee ENT0006, JUR-KY, owned 40% by an entity in JUR-DE,
  which is itself wholly owned by another JUR-KY entity): the payee's
  immediate owner holds only 40% -- 50% or less -- so the look-through
  STOPS there; that owner (JUR-DE, a treaty partner) is the relevant
  parent, regardless of what owns *that* entity in turn. Treaty rate
  applies. `10,000.00`. (This is the case to check most carefully: the
  payee's own jurisdiction, JUR-KY, is irrelevant here, and so is the
  grandparent's jurisdiction -- only the entity the walk stops at
  matters.)

- **PAY0006 + PAY0007** (both payee ENT0009, JUR-DE, no owner, $300,000
  each, paid 2024-03-01 and 2024-07-01): each individually qualifies for
  the treaty rate (10%) on its own facts. But their combined USD total,
  $600,000, exceeds the $500,000 annual threshold. Both payments --
  including the first one, already "paid" at the treaty rate -- are
  retroactively re-rated to the statutory rate (30%). Each shows
  `final_withholding_usd = 90,000.00` and `true_up_usd = 60,000.00`
  (the additional amount owed beyond what was withheld at the time of
  each payment).

- **PAY0008 + PAY0009** (both payee ENT0010, JUR-SG, owned by an entity
  in JUR-DE whose stake is 60% through June 30 and 40% from July 1
  onward; that owner is itself wholly owned by an entity in JUR-KY):
  PAY0008 (paid 2024-03-01, during the 60% window) has an owner stake
  over 50%, so the look-through continues past the owner to the
  JUR-KY grandparent -- no treaty, statutory rate, `30,000.00`. PAY0009
  (paid 2024-09-01, during the 40% window) has the SAME payee and the
  SAME owner, but the owner's stake as of *this* payment's date is only
  40%, so the look-through stops at the owner (JUR-DE, a treaty
  partner) -- treaty rate, `10,000.00`. The relevant parent must be
  resolved separately for each payment's own date; resolving it once for
  the payee (or reusing whichever answer was computed first) gives the
  same wrong rate to both payments instead of two different correct
  ones.

**Total liability across all nine payments: $330,000.00.**
