"""Reference policy: at each decision point, treats tech<->job assignment
as a genuine weighted bipartite matching problem and solves it exactly
(brute force; batches are capped at MAX_JOINT so this stays fast), rather
than picking greedily one job at a time in a fixed priority order. Every
factor that matters -- avoiding a self-inflicted breach, reserving
scarce-skill technicians, minimizing overtime and fatigue-inflated
duration -- is folded into ONE per-pairing cost so the search can legitimately
trade them off (e.g. deliberately serving a slightly-less-urgent job first
when serving the most-urgent one would breach it anyway but the other
still makes its deadline), which no fixed-priority greedy rule can do
correctly in general."""
import itertools

FATIGUE_THRESHOLD_MIN = 180
FATIGUE_MULTIPLIER = 1.25
MAX_JOINT = 12  # cap on jobs considered jointly per decision (keeps brute force fast);
                # kept well above typical technician-pool size so a moderate-priority
                # job stuck behind a temporary rush of more urgent ones doesn't fall
                # out of consideration and starve
BREACH_PENALTY = 200.0


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
        return None  # infeasible

    overtime = max(0, finish - max(now, tech.shift_end))
    fatigue_waste = dur - job.duration
    # scarcity is only a reason to hesitate about the technician's OTHER
    # skills, not the one this job actually needs -- using a rare-skill
    # technician for exactly the job that needs that rare skill is correct,
    # not wasteful, so it must never be penalized like spending them on
    # generic work would be
    other_skills = tech.skills - {job.required_skill}
    other_skills_scarcity = min((_scarcity(s, all_techs) for s in other_skills), default=99)
    # reward spending a technician whose OTHER skills are abundant (safe to
    # use); lower scarcity count means MORE scarce, so the penalty for
    # spending them must fall as the count rises
    scarcity_penalty = -other_skills_scarcity * 5.0

    if finish > job.deadline:
        # this pairing does not actually save the job from breaching, so it
        # earns none of the avoided-breach credit below, and an urgent miss
        # additionally risks spawning a cascade follow-up
        avoided_breach_credit = 0.0
        cascade_risk = 50.0 if job.priority == "urgent" else 0.0
    else:
        # completing the job now genuinely avoids its breach; credit close
        # to the real BREACH_PENALTY so the search prefers serving whichever
        # job is actually savable when it can't serve every pending job.
        # among jobs that are all savable, still give urgent ones a modest
        # edge (much smaller than the breach-avoidance gap) since an urgent
        # miss is more costly than a standard one
        avoided_breach_credit = -(BREACH_PENALTY * 0.9) - (30.0 if job.priority == "urgent" else 0.0)
        cascade_risk = 0.0

    return overtime * 1.5 + fatigue_waste + scarcity_penalty + avoided_breach_credit + cascade_risk


def _best_matching(jobs, techs, now, all_techs):
    """Exact brute-force minimum-cost matching over which subset of jobs
    (size m = min(len(jobs), len(techs))) to serve and which technician
    serves each."""
    n = len(jobs)
    m = min(n, len(techs))
    if m == 0:
        return []
    best = []
    best_key = (0, 0.0)
    for job_subset in itertools.combinations(jobs, m):
        for tech_perm in itertools.permutations(techs, m):
            assignment = []
            total_cost = 0.0
            feasible_count = 0
            for j, t in zip(job_subset, tech_perm):
                cost = _pairing_cost(j, t, now, all_techs)
                if cost is not None:
                    assignment.append((j, t))
                    feasible_count += 1
                    total_cost += cost
            key = (feasible_count, -total_cost)
            if key > best_key:
                best_key = key
                best = assignment
    return best


def decide(state):
    all_jobs = list(state.pending_jobs)
    all_techs = list(state.free_technicians)
    if not all_jobs or not all_techs:
        return []

    techs_ranked = all_techs[:MAX_JOINT]

    # rank by urgency/deadline only to decide which jobs enter the joint
    # search when the backlog exceeds MAX_JOINT -- the search itself (via
    # avoided_breach_credit above) is free to prefer a lower-ranked job over
    # a higher-ranked one once inside that window
    def job_priority(j):
        return (0 if j.priority == "urgent" else 1, j.deadline)

    servable_now = [j for j in all_jobs if any(j.required_skill in t.skills for t in techs_ranked)]
    jobs_to_serve = sorted(servable_now, key=job_priority)[:MAX_JOINT]

    result = _best_matching(jobs_to_serve, techs_ranked, state.current_time, all_techs)

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
