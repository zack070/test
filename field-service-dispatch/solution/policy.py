"""Reference policy: at each decision point, treats tech<->job assignment
as a genuine weighted bipartite matching problem and solves it EXACTLY via
the Hungarian algorithm (O((techs+jobs)^3), no batch truncation needed at
these scales), rather than picking greedily one job at a time in a fixed
priority order. Every factor that matters -- avoiding a self-inflicted
breach, reserving scarce-skill technicians, minimizing overtime and
fatigue-inflated duration -- is folded into ONE per-pairing cost so the
search can legitimately trade them off (e.g. deliberately serving a
slightly-less-urgent job first when serving the most-urgent one would
breach it anyway but the other still makes its deadline), which no
fixed-priority greedy rule can do correctly in general.

An earlier version of this reference capped the batch considered per
decision to a small MAX_JOINT and picked which jobs entered that window by
a fixed priority pre-filter. Under enough backlog that pre-filter can
silently exclude a job an exact search would have served, making the
"exact" matching perform worse than a full-consideration greedy on that
job -- a real correctness bug, not a difficulty feature. The Hungarian
formulation below has no such window: every currently pending job and
every currently free technician is in the search every time.
"""
FATIGUE_THRESHOLD_MIN = 180
FATIGUE_MULTIPLIER = 1.25
BREACH_PENALTY = 200.0

# Safety valve only (never expected to bind at realistic shift scales): caps
# how many pending jobs enter the matching in one decision, by taking the
# most urgent/soonest-due ones first, purely to bound worst-case runtime.
_SAFETY_JOB_CAP = 120


def _scarcity(skill, techs):
    return sum(1 for t in techs if skill in t.skills)


def _duration_for(job, tech):
    if tech.continuous_work >= FATIGUE_THRESHOLD_MIN:
        return int(round(job.duration * FATIGUE_MULTIPLIER))
    return job.duration


def _pairing_cost(job, tech, now, all_techs):
    if job.required_skill not in tech.skills:
        return None  # not eligible to do this job at all
    dur = _duration_for(job, tech)
    finish = now + dur
    shift_limit = tech.shift_end + tech.max_overtime
    if finish > shift_limit:
        return None  # infeasible: can't even finish within the overtime cap
    if finish > job.deadline:
        # this pairing would not actually save the job from breaching --
        # the breach fires at the same wall-clock moment whether or not
        # anyone is assigned, so tying up a technician here buys nothing
        # and only removes them from the pool for work that IS savable.
        # Never a legitimate choice, so it's infeasible, not merely
        # "neutral" -- a neutral cost could still be chosen over leaving
        # the technician free if some other term made it look cheap.
        return None

    overtime = max(0, finish - max(now, tech.shift_end))
    fatigue_waste = dur - job.duration
    # scarcity is only a reason to hesitate about the technician's OTHER
    # skills, not the one this job actually needs -- using a rare-skill
    # technician for exactly the job that needs that rare skill is correct,
    # not wasteful, so it must never be penalized like spending them on
    # generic work would be
    other_skills = tech.skills - {job.required_skill}
    if other_skills:
        # lower scarcity count means MORE scarce
        other_skills_scarcity = min(_scarcity(s, all_techs) for s in other_skills)
    else:
        # nothing else to protect: this technician has no other skill this
        # assignment could waste, which is the SAFEST possible case, not a
        # neutral one -- treat it as at least as safe as the most abundant
        # skill any technician could have (every technician "has" it)
        other_skills_scarcity = len(all_techs)
    # reward spending a technician whose other skills are abundant (safe
    # to use) or nonexistent (nothing to waste); the reward must shrink as
    # the count falls toward genuine scarcity, so a true specialist is the
    # LEAST attractive choice for work anyone could do, not a bonus pick
    scarcity_penalty = -other_skills_scarcity * 5.0

    # completing the job now genuinely avoids its breach; credit close to
    # the real BREACH_PENALTY so the search prefers serving whichever job
    # is actually savable when it can't serve every pending job. among
    # jobs that are all savable, still give urgent ones a modest edge
    # (much smaller than the breach-avoidance gap) since an urgent miss is
    # more costly than a standard one
    avoided_breach_credit = -(BREACH_PENALTY * 0.9) - (30.0 if job.priority == "urgent" else 0.0)

    return overtime * 1.5 + fatigue_waste + scarcity_penalty + avoided_breach_credit


def _hungarian_min_cost(cost):
    """Classic O(n^3) Kuhn-Munkres on a square cost matrix (list of lists
    of floats). Returns result[i] = column index assigned to row i."""
    n = len(cost)
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    result = [0] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            result[p[j] - 1] = j - 1
    return result


def _best_matching(jobs, techs, now, all_techs):
    """Exact minimum-cost matching (maximize jobs served, then minimize
    real cost among ways of doing that) via the Hungarian algorithm on a
    padded square matrix: real tech/job pairs carry a large negative bonus
    when feasible (so serving a job is always preferred to leaving it, as
    long as any feasible pairing exists), dummy rows/columns represent
    "leave this technician idle" / "leave this job unserved" at cost 0, and
    infeasible real pairs get a cost far larger than any bonus so they are
    never chosen over a dummy option."""
    R, C = len(techs), len(jobs)
    if R == 0 or C == 0:
        return []

    BONUS = 1_000_000.0
    BIG = 1_000_000_000.0
    n = R + C  # pad to a square matrix with R dummy jobs and C dummy techs
    cost = [[0.0] * n for _ in range(n)]
    raw = {}
    for i, t in enumerate(techs):
        for j, jb in enumerate(jobs):
            c = _pairing_cost(jb, t, now, all_techs)
            if c is None:
                cost[i][j] = BIG
            else:
                raw[(i, j)] = c
                cost[i][j] = c - BONUS
    # dummy jobs (columns C..C+R-1): tech i can "skip" via its own dummy column at cost 0
    for i in range(R):
        cost[i][C + i] = 0.0
    # dummy techs (rows R..R+C-1): job j can go "unserved" via its own dummy row at cost 0
    for j in range(C):
        cost[R + j][j] = 0.0
    # dummy-dummy block stays at the default 0.0 already set above

    assign = _hungarian_min_cost(cost)  # assign[i] = column for row i

    result = []
    for i in range(R):
        j = assign[i]
        if j < C and (i, j) in raw:
            result.append((jobs[j], techs[i]))
    return result


# Tracks whether the t=0 arrival batch has finished materializing. Every
# job with arrival_time=0 fires as its own "arrival" event, strictly
# before the simulator's guaranteed "start" event (arrivals are pushed to
# the event queue first, "start" last, and the heap breaks same-timestamp
# ties by push order) -- so as long as nothing is assigned yet, the
# pending count at t=0 strictly grows with each arrival and then holds
# steady exactly once on the "start" call. Reacting only once it holds
# steady means every t=0 job gets jointly matched together instead of
# being committed one at a time as it happens to arrive, which is the
# only way the joint search's batch reasoning ever has more than one job
# to actually reason across (job arrivals are always revealed one at a
# time, even when several share a timestamp).
_t0_state = {"last_pending_count": -1, "settled": False}


def decide(state):
    all_jobs = list(state.pending_jobs)
    all_techs = list(state.free_technicians)
    if not all_jobs or not all_techs:
        return []

    if state.current_time == 0 and not _t0_state["settled"]:
        if len(all_jobs) > _t0_state["last_pending_count"]:
            _t0_state["last_pending_count"] = len(all_jobs)
            return []  # more t=0 arrivals may still be coming; wait
        _t0_state["settled"] = True  # pending count held steady: batch is complete

    def job_priority(j):
        return (0 if j.priority == "urgent" else 1, j.deadline)

    jobs_to_serve = sorted(all_jobs, key=job_priority)[:_SAFETY_JOB_CAP]
    techs_batch = all_techs[:_SAFETY_JOB_CAP]

    result = _best_matching(jobs_to_serve, techs_batch, state.current_time, all_techs)

    assignments = []
    used_techs = set()
    used_jobs = set()
    for j, t in result:
        if t.tech_id in used_techs or j.job_id in used_jobs:
            continue
        assignments.append((t.tech_id, j.job_id))
        used_techs.add(t.tech_id)
        used_jobs.add(j.job_id)
    return assignments
