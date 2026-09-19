# Worked example

Four jobs, two families. Walk this through by hand against
`SCHEDULING_SPEC.md` to confirm you understand the timing and cost rules
before running anything against the full case data.

Jobs: `A` (family 0, proc 10, due 15, weight 2), `B` (family 1, proc 8,
due 20, weight 3), `C` (family 0, proc 12, due 55, weight 1), `D`
(family 1, proc 6, due 60, weight 4).

`setup_matrix = [[3, 20], [25, 4]]` (same-family setup: 3 for family 0,
4 for family 1; family 0 -> family 1 costs 20; family 1 -> family 0
costs 25). `initial_setup = [8, 30]`.

## Sequence A, B, C, D (due-date order)

- `A`: first job, family 0 -> `t = initial_setup[0] = 8`, then
  `t += proc = 18`. Due 15, so tardiness `= 18 - 15 = 3`.
  Cost added: `weight 2 * 3 = 6`. Running cost: `6`.
- `B`: family 1 follows family 0 -> `setup_matrix[0][1] = 20`,
  `t = 18 + 20 = 38`, then `t += 8 = 46`. Due 20, tardiness `= 26`.
  Cost added: `3 * 26 = 78`. Running cost: `84`.
- `C`: family 0 follows family 1 -> `setup_matrix[1][0] = 25`,
  `t = 46 + 25 = 71`, then `t += 12 = 83`. Due 55, tardiness `= 28`.
  Cost added: `1 * 28 = 28`. Running cost: `112`.
- `D`: family 1 follows family 0 -> `setup_matrix[0][1] = 20`,
  `t = 83 + 20 = 103`, then `t += 6 = 109`. Due 60, tardiness `= 49`.
  Cost added: `4 * 49 = 196`. Running cost: `308`.

**Total objective: 308.**

## Sequence A, C, D, B (grouped by family, B last)

- `A`: same as above -> running cost `6`, `t = 18`.
- `C`: family 0 follows family 0 -> `setup_matrix[0][0] = 3`,
  `t = 18 + 3 = 21`, then `t += 12 = 33`. Due 55, tardiness `= 0`.
  Cost added: `0`. Running cost: `6`.
- `D`: family 1 follows family 0 -> `setup_matrix[0][1] = 20`,
  `t = 33 + 20 = 53`, then `t += 6 = 59`. Due 60, tardiness `= 0`.
  Cost added: `0`. Running cost: `6`.
- `B`: family 1 follows family 1 -> `setup_matrix[1][1] = 4`,
  `t = 59 + 4 = 63`, then `t += 8 = 71`. Due 20, tardiness `= 51`.
  Cost added: `3 * 51 = 153`. Running cost: `159`.

**Total objective: 159.**

The second sequence is much better even though it makes `B` (the job
with the tightest due date) finish last — grouping same-family jobs
saves enough setup time overall to outweigh the extra tardiness. Neither
sequence shown here is claimed to be optimal; they exist to confirm your
own scoring/simulation code produces exactly `308` and exactly `159` for
these two sequences before you run anything against the larger case data.
