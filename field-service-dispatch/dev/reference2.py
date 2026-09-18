"""Second, independently-built exact reference policy.

Solves the same joint per-decision-point assignment problem as
solution/policy.py, but with a deliberately different implementation: a
min-cost-max-flow via SPFA-based successive shortest augmenting paths
(instead of the primary reference's Hungarian algorithm), and an inverse
(not linear) scarcity-penalty formula. Used only to cross-validate that
the pass-bar floor is a real property of the problem rather than an
artifact of one specific formula/search strategy -- never shipped as the
task's reference solution.
"""
from collections import deque

FATIGUE_THRESHOLD_MIN = 180
FATIGUE_MULTIPLIER = 1.25
BREACH_PENALTY = 200.0
_SAFETY_JOB_CAP = 120


def _duration_for(job, tech):
    if tech.continuous_work >= FATIGUE_THRESHOLD_MIN:
        return int(round(job.duration * FATIGUE_MULTIPLIER))
    return job.duration


def _scarcity_count(skill, techs):
    return sum(1 for t in techs if skill in t.skills)


def _pairing_cost(job, tech, now, all_techs):
    if job.required_skill not in tech.skills:
        return None
    dur = _duration_for(job, tech)
    finish = now + dur
    limit = tech.shift_end + tech.max_overtime
    if finish > limit:
        return None

    overtime = max(0, finish - max(now, tech.shift_end))
    fatigue_waste = dur - job.duration

    other_skills = tech.skills - {job.required_skill}
    if other_skills:
        rarest = min(_scarcity_count(s, all_techs) for s in other_skills)
    else:
        rarest = 10 ** 6
    # Inverse-shaped scarcity penalty (differs deliberately from the primary
    # reference's linear form): grows sharply as the rarest other skill's
    # supply count shrinks toward 1, and is negligible once supply is ample.
    scarcity_penalty = -(BREACH_PENALTY * 0.06) / max(1, rarest)

    if finish > job.deadline:
        avoided_breach_credit = 0.0
        cascade_risk = 45.0 if job.priority == "urgent" else 0.0
    else:
        avoided_breach_credit = -(BREACH_PENALTY * 0.92) - (28.0 if job.priority == "urgent" else 0.0)
        cascade_risk = 0.0

    return overtime * 1.5 + fatigue_waste + scarcity_penalty + avoided_breach_credit + cascade_risk


class _MCMF:
    """Min-cost max-flow via SPFA (queue-based Bellman-Ford) successive
    shortest augmenting paths. Handles negative edge costs (no negative
    cycles exist in this layered source/tech/job/sink graph)."""

    def __init__(self, n):
        self.n = n
        self.graph = [[] for _ in range(n)]
        self.edges = []  # [to, cap, cost]

    def add_edge(self, u, v, cap, cost):
        self.graph[u].append(len(self.edges))
        self.edges.append([v, cap, cost])
        self.graph[v].append(len(self.edges))
        self.edges.append([u, 0, -cost])

    def run(self, s, t):
        n = self.n
        total_flow = 0
        total_cost = 0.0
        while True:
            dist = [float("inf")] * n
            in_queue = [False] * n
            prev_edge = [-1] * n
            dist[s] = 0.0
            dq = deque([s])
            in_queue[s] = True
            while dq:
                u = dq.popleft()
                in_queue[u] = False
                for eid in self.graph[u]:
                    v, cap, cost = self.edges[eid]
                    if cap > 0 and dist[u] + cost < dist[v] - 1e-9:
                        dist[v] = dist[u] + cost
                        prev_edge[v] = eid
                        if not in_queue[v]:
                            dq.append(v)
                            in_queue[v] = True
            if dist[t] == float("inf"):
                break
            aug = float("inf")
            v = t
            while v != s:
                eid = prev_edge[v]
                aug = min(aug, self.edges[eid][1])
                v = self.edges[eid ^ 1][0]
            v = t
            while v != s:
                eid = prev_edge[v]
                self.edges[eid][1] -= aug
                self.edges[eid ^ 1][1] += aug
                v = self.edges[eid ^ 1][0]
            total_flow += aug
            total_cost += aug * dist[t]
        return total_flow, total_cost


def _best_assignment(jobs, techs, now, all_techs):
    R, C = len(techs), len(jobs)
    if R == 0 or C == 0:
        return []

    BONUS = 1_000_000.0
    s, t = 0, 1
    n = 2 + R + C
    g = _MCMF(n)
    for i in range(R):
        g.add_edge(s, 2 + i, 1, 0.0)
    for j in range(C):
        g.add_edge(2 + R + j, t, 1, 0.0)
    raw = {}
    for i, tech in enumerate(techs):
        for j, job in enumerate(jobs):
            c = _pairing_cost(job, tech, now, all_techs)
            if c is not None:
                raw[(i, j)] = c
                g.add_edge(2 + i, 2 + R + j, 1, c - BONUS)

    g.run(s, t)

    result = []
    for i in range(R):
        for eid in g.graph[2 + i]:
            v, cap, c = g.edges[eid]
            if 2 + R <= v < 2 + R + C and cap == 0 and c < 0:
                j = v - (2 + R)
                if (i, j) in raw:
                    result.append((jobs[j], techs[i]))
    return result


def decide(state):
    all_jobs = list(state.pending_jobs)
    all_techs = list(state.free_technicians)
    if not all_jobs or not all_techs:
        return []

    def job_priority(j):
        return (0 if j.priority == "urgent" else 1, j.deadline)

    jobs_batch = sorted(all_jobs, key=job_priority)[:_SAFETY_JOB_CAP]
    techs_batch = all_techs[:_SAFETY_JOB_CAP]

    pairs = _best_assignment(jobs_batch, techs_batch, state.current_time, all_techs)

    assignments = []
    used_techs = set()
    used_jobs = set()
    for job, tech in pairs:
        if tech.tech_id in used_techs or job.job_id in used_jobs:
            continue
        assignments.append((tech.tech_id, job.job_id))
        used_techs.add(tech.tech_id)
        used_jobs.add(job.job_id)
    return assignments
