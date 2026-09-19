"""Independently-written scorer (trusted, Stage 2 only). Deliberately
structured differently from solution/scheduler.py's sequence_objective --
computes per-job finish times into a list first, then sums cost in a
second pass, rather than accumulating in a single running loop -- to
catch a shared-bug risk between the reference solution and the grader."""


def score_sequence(job_ids_in_order, jobs_by_id, setup_matrix, initial_setup):
    finish_times = []
    prev_family = None
    clock = 0
    for jid in job_ids_in_order:
        job = jobs_by_id[jid]
        fam = job["family"]
        gap = initial_setup[fam] if prev_family is None else setup_matrix[prev_family][fam]
        clock = clock + gap + job["proc_time"]
        finish_times.append(clock)
        prev_family = fam

    total = 0
    for jid, finish in zip(job_ids_in_order, finish_times):
        job = jobs_by_id[jid]
        late = finish - job["due_date"]
        if late > 0:
            total += job["weight"] * late
    return total
