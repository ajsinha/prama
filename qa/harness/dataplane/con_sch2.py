import sys, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.schedule.cadence import (
    CadenceBounds, Observation, Decision, AdaptiveCadence, _round_interval, _period,
)
from prama.schedule.budget import Priority, Candidate, Deferral, Allocation, BudgetPolicy
from prama.core.errors import ValidationError

def sch033():
    b1 = CadenceBounds(floor_minutes=15, ceiling_minutes=1440, initial_minutes=0)
    b2 = CadenceBounds(floor_minutes=15, ceiling_minutes=1440, initial_minutes=60)
    ac1 = AdaptiveCadence(b1)
    ac2 = AdaptiveCadence(b2)
    d1 = ac1.decide(Observation())
    d2 = ac2.decide(Observation())
    ok = d1.minutes == 15 and d2.minutes == 60 and "nothing has been observed" in d1.reason
    log("SCH-033", "PASS" if ok else "FAIL", f"initial=0->minutes={d1.minutes} initial=60->minutes={d2.minutes} reason={d1.reason!r}")

def sch034():
    bounds = CadenceBounds(floor_minutes=15, ceiling_minutes=1440)
    ac = AdaptiveCadence(bounds)
    obs_fail = Observation(verdicts=("pass",)*40 + ("fail",))
    d1 = ac.decide(obs_fail, current_minutes=480)
    obs_error = Observation(verdicts=("pass",)*40 + ("error",))
    d2 = ac.decide(obs_error, current_minutes=480)
    ok = d1.minutes == 15 and "rather than easing back" in d1.reason and d2.minutes == 15
    log("SCH-034", "PASS" if ok else "FAIL", f"trailing_fail->{d1.minutes}/{d1.reason!r} trailing_error->{d2.minutes}")

def sch035():
    bounds = CadenceBounds(floor_minutes=60, ceiling_minutes=10080)
    ac = AdaptiveCadence(bounds)
    obs9 = Observation(verdicts=("pass",)*9)
    d9 = ac.decide(obs9, current_minutes=60)
    obs10 = Observation(verdicts=("pass",)*10)
    d10 = ac.decide(obs10, current_minutes=60)
    ok = d9.minutes == 60 and "sample" in d9.reason.lower() and d10.minutes == 90
    log("SCH-035", "PASS" if ok else "FAIL", f"9_passes->{d9.minutes}/{d9.reason!r} 10_passes->{d10.minutes}")

def sch036():
    bounds = CadenceBounds(floor_minutes=60, ceiling_minutes=240)
    ac = AdaptiveCadence(bounds)
    minutes = 240
    reasons = []
    for _ in range(50):
        d = ac.decide(Observation(verdicts=("pass",)*20), current_minutes=minutes)
        minutes = d.minutes
        reasons.append(d.reason)
    ok = minutes == 240 and "ceiling" in reasons[-1]
    log("SCH-036", "PASS" if ok else "FAIL", f"final_minutes={minutes} last_reason={reasons[-1]!r}")

def sch037():
    obs = {}
    for label, kwargs in (
        ("floor0", dict(floor_minutes=0, ceiling_minutes=100)),
        ("floor_neg", dict(floor_minutes=-5, ceiling_minutes=100)),
        ("ceiling_below_floor", dict(floor_minutes=60, ceiling_minutes=15)),
        ("equal", dict(floor_minutes=60, ceiling_minutes=60)),
    ):
        try:
            CadenceBounds(**kwargs)
            obs[label] = "OK"
        except ValidationError:
            obs[label] = "refused"
    ok = obs["floor0"] == "refused" and obs["floor_neg"] == "refused" and obs["ceiling_below_floor"] == "refused" and obs["equal"] == "OK"
    log("SCH-037", "PASS" if ok else "FAIL", str(obs))

def sch038():
    bounds = CadenceBounds(floor_minutes=15, ceiling_minutes=1440)
    ac = AdaptiveCadence(bounds)
    obs2 = Observation(verdicts=("pass",)*5 + ("indeterminate",)*2)
    d2 = ac.decide(obs2, current_minutes=60)
    obs3 = Observation(verdicts=("pass",)*5 + ("indeterminate",)*3)
    d3 = ac.decide(obs3, current_minutes=60)
    ok = (d2.minutes == 60 and ("sample" in d2.reason.lower() or "consecutive" in d2.reason.lower())
          and d3.minutes == 60 and "empty scope informative" in d3.reason)
    log("SCH-038", "PASS" if ok else "FAIL", f"2_indeterminate->{d2.minutes}/{d2.reason!r}; 3_indeterminate->{d3.minutes}/{d3.reason!r}")

def sch039():
    obs = {}
    for label, verdicts in (
        ("empty", ()), ("10pass", ("pass",)*10), ("fail_then_10pass", ("fail",)+("pass",)*10),
        ("10pass_then_fail", ("pass",)*10 + ("fail",)),
    ):
        o = Observation(verdicts=verdicts)
        obs[label] = (o.consecutive_passes, o.last_failed, o.recent_failures)
    ok = (obs["empty"] == (0, False, 0) and obs["10pass"] == (10, False, 0)
          and obs["fail_then_10pass"] == (10, False, 1) and obs["10pass_then_fail"] == (0, True, 1))
    log("SCH-039", "PASS" if ok else "FAIL", str(obs))

def sch040():
    verdicts = ("fail",)*50 + ("pass",)*50
    o = Observation(verdicts=verdicts)
    ok = o.recent_failures == 0
    log("SCH-040", "PASS" if ok else "FAIL", f"recent_failures={o.recent_failures}")

def sch041():
    obs = {}
    for n in (1, 7, 59, 60, 202, 1439, 1440, 5000):
        obs[n] = _round_interval(n)
    ok = (obs[1] == 5 and obs[7] == 5 and obs[59] == 60 and obs[60] == 60
          and obs[202] == 210 and obs[1439] == 1440 and obs[1440] == 1440 and obs[5000] == 5040)
    log("SCH-041", "PASS" if ok else "FAIL", str(obs))

def sch042():
    d0 = Decision(minutes=60, reason="x", previous_minutes=0)
    dsame = Decision(minutes=60, reason="x", previous_minutes=60)
    dwider = Decision(minutes=120, reason="x", previous_minutes=60)
    dnarrower = Decision(minutes=60, reason="x", previous_minutes=120)
    ok = (d0.changed is False and d0.direction == "unchanged"
          and dsame.changed is False and dsame.direction == "unchanged"
          and dwider.changed is True and dwider.direction == "widened"
          and dnarrower.changed is True and dnarrower.direction == "narrowed"
          and "instead of" not in d0.render() and "instead of" in dwider.render())
    log("SCH-042", "PASS" if ok else "FAIL", f"prev0={d0.changed}/{d0.direction} same={dsame.changed}/{dsame.direction} wider={dwider.changed}/{dwider.direction} narrower={dnarrower.changed}/{dnarrower.direction}")

def sch043():
    obs = {}
    for m in (5, 60, 90, 120, 1440, 2880, 1500):
        obs[m] = _period(m)
    ok = (obs[5] == "5 minutes" and obs[60] == "hour" and obs[90] == "hour 30 minutes"
          and obs[120] == "2 hours" and obs[1440] == "day" and obs[2880] == "2 days" and obs[1500] == "25 hours")
    log("SCH-043", "PASS" if ok else "FAIL", str(obs))

def sch044():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(10)
    candidates = [Candidate(identifier=f"crit{i}", dataset="d", priority=Priority.CRITICAL, cost=6.67) for i in range(3)]
    alloc = policy.allocate(candidates, now=now)
    ok = (len(alloc.admitted) == 3 and alloc.over_committed is True and abs(alloc.spent - 20.01) < 0.1
          and "exceeds the budget" in alloc.render() and "run anyway" in alloc.render()
          and "change one of the two" in alloc.render())
    log("SCH-044", "PASS" if ok else "FAIL", f"n_admitted={len(alloc.admitted)} over_committed={alloc.over_committed} spent={alloc.spent} render_excerpt={alloc.render()[:200]!r}")

def sch045():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(0)
    candidates = [Candidate(identifier=f"n{i}", dataset=f"d{i}", priority=Priority.NORMAL, cost=1) for i in range(12)]
    alloc = policy.allocate(candidates, now=now)
    rendered = alloc.render()
    lines_naming_each = all(f"n{i}" in rendered and f"d{i}" in rendered for i in range(12))
    ok = len(alloc.deferred) == 12 and lines_naming_each and "12 deferred" in rendered
    log("SCH-045", "PASS" if ok else "FAIL", f"n_deferred={len(alloc.deferred)} all_named_individually={lines_naming_each}")

def sch046():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(100)
    a = Candidate(identifier="A", dataset="d", priority=Priority.NORMAL, cost=1, deferrals=0)
    b = Candidate(identifier="B", dataset="d", priority=Priority.NORMAL, cost=100, deferrals=3)
    alloc = policy.allocate([a, b], now=now)
    admitted_ids = [c.identifier for c in alloc.admitted]
    log("SCH-046", "FAIL" if admitted_ids == ["B"] else "PASS",
        f"admitted={admitted_ids} deferred={[d.candidate.identifier for d in alloc.deferred]} "
        f"(sort key is (priority.rank, -deferrals, cost, identifier): B has 3 deferrals so -3 sorts "
        f"before A's -0, so B is considered FIRST and admitted (cost 100 <= budget 100), leaving no "
        f"room for A (cost 1) -- deferrals outrank cost, contradicting the docstring's 'by cost "
        f"ascending... within equal cost, deferred longest' ordering, exactly as the catalogue "
        f"states)")

def sch047():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(0)
    c2 = Candidate(identifier="c2def", dataset="d", priority=Priority.NORMAL, cost=1, deferrals=2)
    c3 = Candidate(identifier="c3def", dataset="d", priority=Priority.NORMAL, cost=1, deferrals=3)
    alloc = policy.allocate([c2, c3], now=now)
    starving_ids = [d.candidate.identifier for d in alloc.starving]
    c3_deferral = next(d for d in alloc.deferred if d.candidate.identifier == "c3def")
    ok = starving_ids == ["c3def"] and "deferral 4 in a row" in c3_deferral.render() and "does not exist" in alloc.render()
    log("SCH-047", "PASS" if ok else "FAIL", f"starving={starving_ids} c3_render={c3_deferral.render()!r}")

def sch048():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(10)
    a = Candidate(identifier="a", dataset="d", priority=Priority.NORMAL, cost=6)
    b = Candidate(identifier="b", dataset="d", priority=Priority.NORMAL, cost=4)
    alloc = policy.allocate([a, b], now=now)
    ok = len(alloc.admitted) == 2 and alloc.spent == 10 and alloc.headroom == 0.0 and alloc.over_committed is False
    log("SCH-048", "PASS" if ok else "FAIL", f"admitted={len(alloc.admitted)} spent={alloc.spent} headroom={alloc.headroom} over_committed={alloc.over_committed}")

def sch049():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    p1 = BudgetPolicy(0)
    p2 = BudgetPolicy(-5)
    ok = p1._budget == 0.0 and p2._budget == 0.0
    crit = Candidate(identifier="crit", dataset="d", priority=Priority.CRITICAL, cost=1)
    normals = [Candidate(identifier=f"n{i}", dataset="d", priority=Priority.NORMAL, cost=1) for i in range(3)]
    alloc = p1.allocate([crit] + normals, now=now)
    ok = ok and alloc.over_committed is True and len(alloc.deferred) == 3 and all(d.candidate.identifier.startswith("n") for d in alloc.deferred)
    log("SCH-049", "PASS" if ok else "FAIL", f"budget0_clamped={p1._budget==0.0} budgetneg5_clamped={p2._budget==0.0} over_committed={alloc.over_committed} n_deferred={len(alloc.deferred)}")

def sch050():
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(0)
    zero_cost = Candidate(identifier="zero", dataset="d", priority=Priority.NORMAL, cost=0)
    neg_cost = Candidate(identifier="neg", dataset="d", priority=Priority.NORMAL, cost=-5)
    alloc = policy.allocate([zero_cost, neg_cost], now=now)
    ok = len(alloc.admitted) == 2 and alloc.spent == -5.0
    log("SCH-050", "PASS" if ok else "FAIL", f"admitted={[c.identifier for c in alloc.admitted]} spent={alloc.spent}")

def sch051():
    # Two same-priority NORMAL candidates get reordered by allocate()'s
    # cost-ascending sort within a priority tier -- the cheaper one (5) is
    # tried first, admitted, leaving 5 (not 2) for the other. Giving the
    # cost-8 candidate CRITICAL priority makes it admitted first
    # deterministically, matching the catalogue's "spent 8" precondition.
    now = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    policy = BudgetPolicy(10)
    spender = Candidate(identifier="s1", dataset="d", priority=Priority.CRITICAL, cost=8)
    over = Candidate(identifier="s2", dataset="d", priority=Priority.NORMAL, cost=5)
    alloc = policy.allocate([spender, over], now=now)
    deferral = alloc.deferred[0]
    ok = "the budget has 2 left and this would cost 5" == deferral.reason
    log("SCH-051", "PASS" if ok else "FAIL", f"reason={deferral.reason!r}")

def sch052():
    now = dt.datetime(2026, 4, 1, 12, 0, tzinfo=dt.UTC)
    policy = BudgetPolicy(0, retry_after_minutes=60)
    candidates = [Candidate(identifier=f"c{i}", dataset="d", priority=Priority.NORMAL, cost=1) for i in range(3)]
    alloc = policy.allocate(candidates, now=now)
    expected = now + dt.timedelta(minutes=60)
    ok = all(d.next_attempt == expected for d in alloc.deferred)
    rendered_ok = all(expected.isoformat(timespec="minutes") in d.render() for d in alloc.deferred)
    log("SCH-052", "PASS" if (ok and rendered_ok) else "FAIL", f"all_next_attempt_correct={ok} all_rendered_with_time={rendered_ok} sample_render={alloc.deferred[0].render()!r}")

for fn in (sch033, sch034, sch035, sch036, sch037, sch038, sch039, sch040, sch041, sch042,
           sch043, sch044, sch045, sch046, sch047, sch048, sch049, sch050, sch051, sch052):
    fn()
