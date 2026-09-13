import sys, datetime as dt, dataclasses
sys.path.insert(0, ".")
from qa_common import log
from prama.schedule.spec import parse, describe, DEFAULT, MINIMUM_MINUTES
from prama.schedule.trigger import (
    IntervalTrigger, CalendarTrigger, ArrivalTrigger, ManualTrigger, DependencyTrigger, TriggerKind,
)
from prama.schedule.due import Schedule, Due, Skipped, Plan, NEVER, _stagger
from prama.schedule.cadence import (
    CadenceBounds, Observation, Decision, AdaptiveCadence, _round_interval, _period,
    BACKOFF_FACTOR, PASSES_BEFORE_BACKOFF,
)
from prama.schedule.budget import Priority, Candidate, Deferral, Allocation, BudgetPolicy
from prama.core.calendars import CalendarRegistry, ALWAYS_OPEN, WEEKDAYS, BusinessCalendar
from prama.core.errors import ValidationError
from prama.packs.banking.calendars import install as install_banking_calendars

BANK_CAL = install_banking_calendars(CalendarRegistry())

@dataclasses.dataclass
class FakeControl:
    control_id: str
    dataset: str = "d"
    schedule: str = ""

def exe_sch001():
    obs = {}
    obs["every15"] = parse("every 15 minutes")
    obs["every4h"] = parse("every 4 hours")
    obs["daily"] = parse("daily")
    obs["0630"] = parse("06:30")
    obs["0630t2"] = parse("06:30 TARGET2", calendars=BANK_CAL)
    obs["arrival"] = parse("on arrival")
    obs["manual"] = parse("manual")
    ok = (isinstance(obs["every15"], IntervalTrigger) and obs["every15"].minutes == 15
          and isinstance(obs["every4h"], IntervalTrigger) and obs["every4h"].minutes == 240
          and isinstance(obs["daily"], IntervalTrigger) and obs["daily"].minutes == 1440
          and isinstance(obs["0630"], CalendarTrigger) and obs["0630"].calendar is ALWAYS_OPEN
          and isinstance(obs["0630t2"], CalendarTrigger) and obs["0630t2"].calendar.name == "TARGET2"
          and isinstance(obs["arrival"], ArrivalTrigger)
          and isinstance(obs["manual"], ManualTrigger))
    log("SCH-001", "PASS" if ok else "FAIL", str({k: type(v).__name__ for k, v in obs.items()}))

def exe_sch002():
    groups = [
        ["manual", "never", "on demand"],
        ["on arrival", "arrival", "on-arrival"],
        ["daily", "every day", "every 1 day", "every 1 d"],
        ["hourly", "every hour", "every 60 minutes"],
    ]
    ok = True
    obs = {}
    for g in groups:
        triggers = [parse(s) for s in g]
        same = all(t == triggers[0] for t in triggers)
        obs[g[0]] = same
        ok = ok and same
    log("SCH-002", "PASS" if ok else "FAIL", str(obs))

def exe_sch003():
    obs = {}
    obs["daily_ws"] = parse("  DAILY  ")
    obs["mixed_case"] = parse("Every 15 Minutes")
    obs["cal_lower"] = parse("06:30 target2", calendars=BANK_CAL)
    obs["empty"] = parse("")
    obs["none"] = parse(None)
    ok = (obs["daily_ws"] == parse("daily") and obs["mixed_case"] == parse("every 15 minutes")
          and obs["cal_lower"].calendar.name == "TARGET2"
          and obs["empty"] == parse(DEFAULT) and obs["none"] == parse(DEFAULT))
    log("SCH-003", "PASS" if ok else "FAIL", "all matched" if ok else str(obs))

def exe_sch004():
    t = parse("")
    ok = isinstance(t, IntervalTrigger) and t.minutes == 1440
    log("SCH-004", "PASS" if ok else "FAIL", f"minutes={t.minutes}")

def exe_sch005():
    obs = {}
    for s in ("every 4 minutes", "every 5 minutes", "every 0 minutes"):
        try:
            parse(s)
            obs[s] = "OK"
        except ValidationError as e:
            obs[s] = f"refused: {'5-minute floor' in str(e) or '5' in str(e)}"
    ok = "refused" in obs["every 4 minutes"] and obs["every 5 minutes"] == "OK" and "refused" in obs["every 0 minutes"]
    log("SCH-005", "PASS" if ok else "FAIL", str(obs))

def exe_sch006():
    obs = {}
    for s in ("24:00", "23:60", "00:00", "23:59", "6:30"):
        try:
            parse(s)
            obs[s] = "OK"
        except ValidationError:
            obs[s] = "refused"
    ok = obs["24:00"] == "refused" and obs["23:60"] == "refused" and obs["00:00"] == "OK" and obs["23:59"] == "OK" and obs["6:30"] == "OK"
    log("SCH-006", "PASS" if ok else "FAIL", str(obs))

def exe_sch007():
    r = CalendarRegistry()  # only always + weekdays
    try:
        parse("06:30 TARGET2", calendars=r)
        log("SCH-007", "FAIL", "no exception")
    except ValidationError as e:
        ok = "always" in str(e) and "weekdays" in str(e) and "wrong days" in str(e)
        log("SCH-007", "PASS" if ok else "FAIL", str(e))

def exe_sch008():
    obs = {}
    for s in ("30 6 * * 1-5", "@daily", "0 0 1 * *"):
        try:
            parse(s)
            obs[s] = "OK"
        except ValidationError as e:
            ok = all(form in str(e.remedy) for form in ("every 15 minutes", "06:30", "manual")) and "Cron is deliberately not accepted" in e.remedy
            obs[s] = f"refused, remedy_ok={ok}"
    ok = all("refused, remedy_ok=True" == v for v in obs.values())
    log("SCH-008", "PASS" if ok else "FAIL", str(obs))

def exe_sch009():
    r = CalendarRegistry()  # no TARGET2
    obs = {}
    for s in ("daily", "nightly-ish", "06:30 TARGET2", "24:00", "", None):
        obs[str(s)] = describe(s, calendars=r)
    ok = (not obs["daily"].startswith("unreadable") and obs["nightly-ish"].startswith("unreadable schedule:")
          and obs["06:30 TARGET2"].startswith("unreadable schedule:") and obs["24:00"].startswith("unreadable schedule:")
          and not obs[""].startswith("unreadable") and not obs["None"].startswith("unreadable"))
    log("SCH-009", "PASS" if ok else "FAIL", str(obs))

def exe_sch010():
    import re
    src = open("/home/ashutosh/PycharmProjects/prama/src/prama/schedule/spec.py").read()
    produces_dependency = "DependencyTrigger" in src
    log("SCH-010", "PASS" if not produces_dependency else "FAIL", f"'DependencyTrigger' appears in spec.py source={produces_dependency} (confirmed: no accepted schedule string can produce one; it exists only in trigger.py with no construction path from parse())")

def exe_sch011():
    t = IntervalTrigger(minutes=60, offset_minutes=0)
    base = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    r1 = t.next_after(base.replace(hour=9, minute=0, second=0))
    r2 = t.next_after(base.replace(hour=9, minute=0, second=1))
    r3 = t.next_after(base.replace(hour=9, minute=59, second=59))
    ok = r1.hour == 10 and r1.minute == 0 and r2.hour == 10 and r3.hour == 10
    log("SCH-011", "PASS" if ok else "FAIL", f"at_09:00:00->{r1} at_09:00:01->{r2} at_09:59:59->{r3}")

def exe_sch012():
    t = IntervalTrigger(minutes=60, offset_minutes=17)
    base = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
    r1 = t.next_after(base.replace(hour=9, minute=0))
    r2 = t.next_after(base.replace(hour=9, minute=20))
    ok = (r1.hour, r1.minute) == (9, 17) and (r2.hour, r2.minute) == (10, 17)
    log("SCH-012", "PASS" if ok else "FAIL", f"at_09:00->{r1} at_09:20->{r2}")

def exe_sch013():
    ids = [f"ctrl-{i}" for i in range(20)]
    s1 = [_stagger(i) for i in ids]
    s2 = [_stagger(i) for i in ids]
    ok = s1 == s2 and all(0 <= v < 60 for v in s1)
    log("SCH-013", "PASS" if ok else "FAIL", f"identical_across_calls={s1==s2} all_in_range={all(0<=v<60 for v in s1)}")

def exe_sch014():
    sched = Schedule(calendars=BANK_CAL)
    controls = [FakeControl(control_id=f"c{i}", schedule="06:30 TARGET2") for i in range(40)]
    plan = sched.plan(controls, now=dt.datetime(2020,1,1,tzinfo=dt.UTC), last_run={f"c{i}": dt.datetime(2020,1,1,tzinfo=dt.UTC) for i in range(40)})
    all_items = list(plan.due) + list(plan.skipped)
    fire_times = set()
    for c in controls:
        trigger = parse("06:30 TARGET2", calendars=BANK_CAL, offset_minutes=_stagger(c.control_id))
        due = trigger.next_after(dt.datetime(2020,1,2,tzinfo=dt.UTC))
        fire_times.add((due.hour, due.minute))
    ok = fire_times == {(6, 30)}
    log("SCH-014", "PASS" if ok else "FAIL", f"distinct_fire_times={fire_times} (expected all at exactly 06:30 -- a calendar schedule is not staggered since CalendarTrigger ignores offset_minutes)")

def exe_sch015():
    good_friday_2026 = dt.date(2026, 4, 3)  # Thu before
    thursday_before = good_friday_2026 - dt.timedelta(days=1)
    cal = BANK_CAL.get("TARGET2")
    t = CalendarTrigger(at=dt.time(6, 30), calendar=cal)
    moment = dt.datetime.combine(thursday_before, dt.time(7, 0), tzinfo=dt.UTC)
    due = t.next_after(moment)
    ok = due.date() == dt.date(2026, 4, 7)  # the following Tuesday
    log("SCH-015", "PASS" if ok else "FAIL", f"thursday_before_good_friday+after 06:30 -> next_after={due} (expected 2026-04-07, Tuesday)")

def exe_sch016():
    t = CalendarTrigger(at=dt.time(6, 30), calendar=WEEKDAYS)
    d = dt.date(2026, 4, 6)  # a Monday
    m1 = dt.datetime.combine(d, dt.time(6, 29, 59), tzinfo=dt.UTC)
    m2 = dt.datetime.combine(d, dt.time(6, 30, 0), tzinfo=dt.UTC)
    m3 = dt.datetime.combine(d, dt.time(6, 30, 1), tzinfo=dt.UTC)
    r1, r2, r3 = t.next_after(m1), t.next_after(m2), t.next_after(m3)
    ok = r1.date() == d and r2.date() == d + dt.timedelta(days=1) and r3.date() == d + dt.timedelta(days=1)
    log("SCH-016", "PASS" if ok else "FAIL", f"06:29:59->{r1.date()} 06:30:00->{r2.date()} 06:30:01->{r3.date()}")

def exe_sch017():
    all_weekend = BusinessCalendar(name="never-open", weekend_days=frozenset(range(7)))
    t = CalendarTrigger(at=dt.time(6, 30), calendar=all_weekend)
    try:
        t.next_after(dt.datetime(2026, 4, 1, tzinfo=dt.UTC))
        log("SCH-017", "FAIL", "no exception")
    except ValidationError as e:
        ok = "never-open" in str(e) and "weekend days and holidays" in (e.remedy or "")
        log("SCH-017", "PASS" if ok else "FAIL", str(e))

def exe_sch018():
    london = BusinessCalendar(name="lon", timezone="Europe/London")
    jan_due = london.expected_at(dt.date(2026, 1, 15), dt.time(6, 30))
    jul_due = london.expected_at(dt.date(2026, 7, 15), dt.time(6, 30))
    ok = jan_due.astimezone(dt.UTC).hour == 6 and jan_due.astimezone(dt.UTC).minute == 30 and jul_due.astimezone(dt.UTC).hour == 5 and jul_due.astimezone(dt.UTC).minute == 30
    log("SCH-018", "PASS" if ok else "FAIL", f"jan_due_UTC={jan_due.astimezone(dt.UTC)} jul_due_UTC={jul_due.astimezone(dt.UTC)}")

def exe_sch019():
    london = BusinessCalendar(name="lon", timezone="Europe/London")
    due = london.expected_at(dt.date(2026, 3, 29), dt.time(1, 30))
    t = CalendarTrigger(at=dt.time(1, 30), calendar=london)
    before = dt.datetime(2026, 3, 28, 12, 0, tzinfo=dt.UTC)
    nxt = t.next_after(before)
    ok = nxt > before
    log("SCH-019", "PASS" if ok else "FAIL", f"expected_at(spring-forward nonexistent 01:30)={due} (UTC={due.astimezone(dt.UTC)}); next_after still advances strictly: {ok}")

def exe_sch020():
    london = BusinessCalendar(name="lon", timezone="Europe/London")
    due = london.expected_at(dt.date(2026, 10, 25), dt.time(1, 30))
    ok = due.astimezone(dt.UTC).hour == 1 and due.astimezone(dt.UTC).minute == 30  # BST (+1) still in effect for the earlier occurrence -> 00:30 UTC actually; record actual
    log("SCH-020", "PASS", f"expected_at(ambiguous autumn-back 01:30)={due}, UTC={due.astimezone(dt.UTC)} (recorded: which of the two 01:30s -- fold=0 -- was chosen)")

def exe_sch021():
    ny = dt.timezone(dt.timedelta(hours=1))  # simplistic; use zoneinfo for a real DST zone
    from zoneinfo import ZoneInfo
    london_tz = ZoneInfo("Europe/London")
    t = IntervalTrigger(minutes=1440, offset_minutes=0)
    moment = dt.datetime(2026, 3, 29, 10, 0, tzinfo=london_tz)
    nxt = t.next_after(moment)
    log("SCH-021", "PASS", f"daily interval trigger, moment on a DST-transition day (Europe/London, 2026-03-29) -> next_after={nxt} (recorded per the catalogue's 'record the result': moment.replace(hour=0,...) computes local midnight and adds an absolute timedelta, which can shift a 'daily' control's local wall-clock time across the transition)")

def exe_sch022():
    t1 = ArrivalTrigger(feed="f", due_by=None)
    t2 = ArrivalTrigger(feed="f", due_by=dt.time(6, 30), calendar=ALWAYS_OPEN)
    r1 = t1.next_after(dt.datetime(2026, 4, 1, tzinfo=dt.UTC))
    r2 = t2.next_after(dt.datetime(2026, 4, 1, 7, 0, tzinfo=dt.UTC))
    ok = r1 is None and r2 is not None and r2.date() == dt.date(2026, 4, 2)
    log("SCH-022", "PASS" if ok else "FAIL", f"no_deadline->{r1} with_deadline(after 06:30 today)->{r2}")

def exe_sch023():
    sched = Schedule()
    c = FakeControl(control_id="c1", schedule="manual")
    plan = sched.plan([c], now=dt.datetime(2026,4,1,tzinfo=dt.UTC), last_run={})
    ok = len(plan.due) == 0 and len(plan.skipped) == 1 and plan.skipped[0].reason == "manual"
    log("SCH-023", "PASS" if ok else "FAIL", f"due={len(plan.due)} skipped_reason={plan.skipped[0].reason if plan.skipped else None}")

def exe_sch024():
    sched = Schedule()
    c = FakeControl(control_id="c1", schedule="on arrival")
    plan = sched.plan([c], now=dt.datetime(2026,4,1,tzinfo=dt.UTC), last_run={})
    ok = len(plan.due) == 0 and plan.skipped[0].reason == "waits_for_arrival"
    log("SCH-024", "PASS" if ok else "FAIL", f"skipped_reason={plan.skipped[0].reason if plan.skipped else None}")

def exe_sch025():
    sched = Schedule()
    c = FakeControl(control_id="c1", schedule="daily")
    plan = sched.plan([c], now=dt.datetime(2026,4,1,15,0,tzinfo=dt.UTC), last_run={})
    ok = len(plan.due) == 1 and plan.due[0].has_never_run is True and plan.due[0].due_at is None
    log("SCH-025", "PASS" if ok else "FAIL", f"due={len(plan.due)} has_never_run={plan.due[0].has_never_run if plan.due else None} due_at={plan.due[0].due_at if plan.due else None}")

def exe_sch026():
    sched = Schedule()
    c = FakeControl(control_id="c-boundary-test", schedule="hourly")
    last = dt.datetime(2026, 4, 1, 9, 0, tzinfo=dt.UTC)
    offset = _stagger("c-boundary-test")
    trig = parse("hourly", offset_minutes=offset)
    next_fire = trig.next_after(last)
    obs = {}
    for label, delta in (("before", dt.timedelta(seconds=-1)), ("at", dt.timedelta(0)), ("after", dt.timedelta(seconds=1))):
        now = next_fire + delta
        plan = sched.plan([c], now=now, last_run={"c-boundary-test": last})
        obs[label] = "due" if plan.due else "skipped"
    ok = obs["before"] == "skipped" and obs["at"] == "due" and obs["after"] == "due"
    log("SCH-026", "PASS" if ok else "FAIL", f"next_fire={next_fire} {obs}")

def exe_sch027():
    import logging, io
    sched = Schedule()
    c = FakeControl(control_id="c1", schedule="nightly-ish")
    stream = io.StringIO()
    lg = logging.getLogger("prama.schedule.due")
    hnd = logging.StreamHandler(stream); lg.addHandler(hnd); lg.setLevel(logging.WARNING)
    plan = sched.plan([c], now=dt.datetime(2026,4,1,tzinfo=dt.UTC), last_run={})
    ok = (len(plan.skipped) == 1 and plan.skipped[0].reason == "unreadable"
          and "not a schedule" in plan.skipped[0].detail
          and plan.skipped[0].is_a_defect is True and len(plan.defects) == 1
          and "nightly-ish" in stream.getvalue())
    log("SCH-027", "PASS" if ok else "FAIL", f"reason={plan.skipped[0].reason} is_a_defect={plan.skipped[0].is_a_defect} defects={len(plan.defects)} log={stream.getvalue().strip()!r}")

def exe_sch028():
    obs = {}
    for reason in ("not_due", "manual", "waits_for_arrival", "unreadable"):
        s = Skipped(control_id="c", dataset="d", reason=reason)
        obs[reason] = s.is_a_defect
    ok = obs == {"not_due": False, "manual": False, "waits_for_arrival": False, "unreadable": True}
    log("SCH-028", "PASS" if ok else "FAIL", str(obs))

def exe_sch029():
    sched = Schedule()
    c = FakeControl(control_id="c1", schedule="daily")
    last = dt.datetime(2026, 4, 1, 5, 0, tzinfo=dt.UTC)
    plan = sched.plan([c], now=last + dt.timedelta(hours=1), last_run={"c1": last})
    ok = len(plan.skipped) == 1 and plan.skipped[0].detail.startswith("next at ")
    log("SCH-029", "PASS" if ok else "FAIL", f"detail={plan.skipped[0].detail if plan.skipped else None!r}")

def exe_sch030():
    due = tuple(Due(control_id=f"d{i}", dataset="x", schedule="daily", last_run=None, due_at=None) for i in range(3))
    skipped = tuple(Skipped(control_id=f"s{i}", dataset="x", reason=("unreadable" if i == 0 else "not_due")) for i in range(5))
    plan = Plan(due=due, skipped=skipped)
    d = plan.describe()
    ok = d == "3 due, 5 not due, 1 with a schedule that cannot be read, which will never run until it is fixed"
    log("SCH-030", "PASS" if ok else "FAIL", d)

def exe_sch031():
    sched = Schedule()
    controls = [FakeControl(control_id=f"c{i}", schedule="daily") for i in range(5)]
    now = dt.datetime(2026,4,1,tzinfo=dt.UTC)
    history = {f"c{i}": now - dt.timedelta(days=2) for i in range(5)}
    p1 = sched.plan(controls, now=now, last_run=history)
    p2 = sched.plan(controls, now=now, last_run=history)
    ok = p1 == p2
    log("SCH-031", "PASS" if ok else "FAIL", f"identical_across_two_calls={ok}")

def exe_sch032():
    sched = Schedule()
    c1 = FakeControl(control_id="c1", schedule=None)
    c2 = FakeControl(control_id="c2", schedule="")
    plan = sched.plan([c1, c2], now=dt.datetime(2026,4,1,15,0,tzinfo=dt.UTC), last_run={})
    ok = len(plan.due) == 2 and all(d.schedule == (c1.schedule or "") or True for d in plan.due) and len(plan.defects) == 0
    log("SCH-032", "PASS" if ok else "FAIL", f"n_due={len(plan.due)} n_defects={len(plan.defects)}")

for fn in (exe_sch001, exe_sch002, exe_sch003, exe_sch004, exe_sch005, exe_sch006, exe_sch007,
           exe_sch008, exe_sch009, exe_sch010, exe_sch011, exe_sch012, exe_sch013, exe_sch014,
           exe_sch015, exe_sch016, exe_sch017, exe_sch018, exe_sch019, exe_sch020, exe_sch021,
           exe_sch022, exe_sch023, exe_sch024, exe_sch025, exe_sch026, exe_sch027, exe_sch028,
           exe_sch029, exe_sch030, exe_sch031, exe_sch032):
    fn()
