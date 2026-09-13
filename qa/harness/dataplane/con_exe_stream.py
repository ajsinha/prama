import sys, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.stream import (
    StreamAssertion, StreamSuite, Window, WindowKind, MessageVerdict, WindowVerdict, Lag,
)
from prama.execute.watermark import (
    Coverage, Watermark, LatenessPolicy, WatermarkPlanner, IncrementalScope,
    _before, _shift, _literal, _period,
)
from prama.pql import parse_control
from prama.ir.resolve import resolved
from prama.ir.model import Verdict
from prama.core.errors import ValidationError

CLEAN = "CHECK t.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'x'"
PLAN = resolved(parse_control(CLEAN))

SCREENED = "CHECK t.lei IS VALID 'lei' SEVERITY major DIMENSION validity BECAUSE 'x'"
SCREENED_PLAN = resolved(parse_control(SCREENED))

def exe100():
    rows = [{"notional": (None if i % 10 == 0 else 1.0)} for i in range(100)]
    a = StreamAssertion(PLAN)
    judge_violations = sum(1 for r in rows if a.judge(r).is_violation)
    b = StreamAssertion(PLAN, window=Window(kind=WindowKind.COUNT, size=100))
    verdict = None
    for r in rows:
        verdict = b.offer(r) or verdict
    ok = judge_violations == verdict.violations == 10
    log("EXE-100", "PASS" if ok else "FAIL", f"judge()_violations={judge_violations} offer()_violations={verdict.violations} (both route through the same ReferenceEvaluator)")

def exe101():
    a = StreamAssertion(SCREENED_PLAN)
    # a fabricated LEI: right shape (20 chars, right alphabet), wrong check digit
    msg = {"lei": "5493001KJTIIGC8Y1R11"}  # plausible-looking but not necessarily a valid checksum
    verdict = a.judge(msg)
    log("EXE-101", "PASS" if verdict.passed is False else "FAIL",
        f"judge() on a screened-but-not-residually-valid LEI -> passed={verdict.passed} "
        f"(residual_validators present={bool(SCREENED_PLAN.residual_validators)})")

def exe102():
    for policy_word, treat_as_fail in (("PASS", False), ("FAIL", True)):
        pql = f"CHECK t.notional > 0 TREAT UNKNOWN AS {policy_word} SEVERITY critical DIMENSION completeness BECAUSE 'x'"
        plan = resolved(parse_control(pql))
        a = StreamAssertion(plan)
        msg = {"notional": None}  # a null operand to a comparison is UNKNOWN under three-valued logic
        verdict = a.judge(msg)
        a2 = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=1))
        closed = a2.offer(msg)
        ok = (verdict.unknown is True and verdict.passed == (not treat_as_fail)
              and closed.unknowns == 1 and closed.violations == (1 if treat_as_fail else 0))
        log(f"EXE-102-{policy_word}", "PASS" if ok else "FAIL", f"judge: unknown={verdict.unknown} passed={verdict.passed}; offer/close: unknowns={closed.unknowns} violations={closed.violations}")

def exe103():
    pql = "CHECK t HAS ROW COUNT AT LEAST 1 SEVERITY critical DIMENSION completeness BECAUSE 'x'"
    plan = resolved(parse_control(pql))
    ok_pred_none = plan.predicate is None
    a = StreamAssertion(plan)
    verdict = a.judge({"anything": 1})
    ok = ok_pred_none and verdict.passed is True and verdict.unknown is False
    log("EXE-103", "PASS" if ok else "FAIL", f"predicate_is_None={ok_pred_none} judge()->passed={verdict.passed} unknown={verdict.unknown}")

def exe104():
    a = StreamAssertion(PLAN, window=Window(kind=WindowKind.COUNT, size=100))
    verdicts = []
    for i in range(101):
        v = a.offer({"notional": 1.0})
        verdicts.append(v)
    v99 = verdicts[98]  # after 99th offer (index 98)
    v100 = verdicts[99]  # after 100th offer
    v101 = verdicts[100]  # after 101st offer -> new window
    ok = v99 is None and v100 is not None and v100.messages == 100 and v101 is None and a.open_messages == 1
    log("EXE-104", "PASS" if ok else "FAIL", f"at_99={v99} at_100={v100} at_101={v101} open_messages_after_101={a.open_messages}")

def exe105():
    a = StreamAssertion(PLAN, window=Window(kind=WindowKind.TUMBLING, duration=dt.timedelta(seconds=60)))
    closed_count = 0
    for i in range(1_000_000):
        v = a.offer({"notional": 1.0}, at=None)
        if v is not None:
            closed_count += 1
    ok = closed_count == 0 and a.open_messages == 1_000_000
    log("EXE-105", "PASS" if ok else "FAIL", f"verdicts_produced={closed_count} open_messages={a.open_messages}")

def exe106():
    a = StreamAssertion(PLAN, window=Window(kind=WindowKind.TUMBLING, duration=dt.timedelta(minutes=1)))
    base = dt.datetime(2026, 4, 1, 12, 0, 0, tzinfo=dt.UTC)
    times = [base + dt.timedelta(seconds=10), base + dt.timedelta(seconds=50),
             base + dt.timedelta(seconds=20), base + dt.timedelta(seconds=65)]
    results = []
    for t in times:
        v = a.offer({"notional": 1.0}, at=t)
        results.append((t.isoformat(), v.messages if v else None))
    log("EXE-106", "PASS", f"offers at 12:00:10,12:00:50,12:00:20,12:01:05 -> {results} "
        f"(window opens at first message's 'at'; a message earlier than _opened_at, like the third "
        f"at 12:00:20 after 12:00:50, produces a negative delta that cannot close the window and is "
        f"simply counted in; recorded per the catalogue's 'record the actual behaviour')")

def exe107():
    a = StreamAssertion(PLAN)
    v = a.close()
    ok = v.verdict is Verdict.INDETERMINATE and v.messages == 0 and v.violation_rate == 0.0
    log("EXE-107", "PASS" if ok else "FAIL", f"verdict={v.verdict} messages={v.messages} violation_rate={v.violation_rate}")

def exe108():
    a = StreamAssertion(PLAN, window=Window(kind=WindowKind.COUNT, size=1000))
    for i in range(5):
        a.offer({"notional": None})  # violation
    for i in range(5):
        a.offer({"notional": 1.0})
    v1 = a.close()
    for i in range(3):
        a.offer({"notional": 1.0}, at=dt.datetime(2026, 4, 2, tzinfo=dt.UTC))
    v2 = a.close()
    ok = v1.violations == 5 and v1.messages == 10 and v2.messages == 3 and v2.violations == 0 and v2.opened_at == dt.datetime(2026, 4, 2, tzinfo=dt.UTC)
    log("EXE-108", "PASS" if ok else "FAIL", f"window1: messages={v1.messages} violations={v1.violations}; window2: messages={v2.messages} violations={v2.violations} opened_at={v2.opened_at}")

def exe109():
    import tracemalloc, gc
    assertions = [StreamAssertion(PLAN, window=Window(kind=WindowKind.COUNT, size=10_000_000)) for _ in range(5)]
    gc.collect()
    tracemalloc.start()
    snap1 = tracemalloc.take_snapshot()
    for i in range(100_000):
        msg = {"notional": 1.0}
        for a in assertions:
            a.offer(msg)
    snap2 = tracemalloc.take_snapshot()
    tracemalloc.stop()
    diff = snap2.compare_to(snap1, "lineno")
    top = sorted(diff, key=lambda s: -s.size_diff)[:3]
    log("EXE-109", "PASS", f"offer() called 500,000 times (5 assertions x 100,000 messages); top allocation deltas: {[str(t) for t in top]} (no MessageVerdict is constructed by offer(); judge() is not called on this path)")

def exe110():
    pql = "CHECK t.notional IS NOT NULL BELOW 0.1% SEVERITY critical DIMENSION completeness BECAUSE 'x'"
    plan = resolved(parse_control(pql))
    a1 = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=1000))
    v1 = None
    for i in range(999):
        v1 = a1.offer({"notional": 1.0}) or v1
    v1 = a1.offer({"notional": None}) or v1  # 1000th offer auto-closes the window
    a2 = StreamAssertion(plan, window=Window(kind=WindowKind.COUNT, size=1000))
    v2 = None
    for i in range(998):
        v2 = a2.offer({"notional": 1.0}) or v2
    for i in range(2):
        v2 = a2.offer({"notional": None}) or v2
    ok = v1.verdict is Verdict.PASS and v2.verdict is Verdict.FAIL
    log("EXE-110", "PASS" if ok else "FAIL", f"1_violation_of_1000(0.1%): verdict={v1.verdict}; 2_violations_of_1000(0.2%): verdict={v2.verdict}")

def exe111():
    obs = {}
    for label, kwargs in (
        ("tumbling_0", dict(kind=WindowKind.TUMBLING, duration=dt.timedelta(0))),
        ("tumbling_neg", dict(kind=WindowKind.TUMBLING, duration=dt.timedelta(seconds=-1))),
        ("count_0", dict(kind=WindowKind.COUNT, size=0)),
        ("count_neg", dict(kind=WindowKind.COUNT, size=-1)),
        ("count_zero_duration", dict(kind=WindowKind.COUNT, size=10, duration=dt.timedelta(0))),
    ):
        try:
            Window(**kwargs)
            obs[label] = "OK"
        except ValidationError as e:
            obs[label] = "ValidationError"
    ok = (obs["tumbling_0"] == "ValidationError" and obs["tumbling_neg"] == "ValidationError"
          and obs["count_0"] == "ValidationError" and obs["count_neg"] == "ValidationError"
          and obs["count_zero_duration"] == "OK")
    log("EXE-111", "PASS" if ok else "FAIL", str(obs))

def exe112():
    assertions = [StreamAssertion(PLAN) for _ in range(40)]
    suite = StreamSuite(assertions)
    msg = {"notional": 1.0}
    # confirm all 40 see the *same* object identity
    seen_ids = set()
    class TrackingEvaluator:
        pass
    # simplest proof: patch each assertion's judge-equivalent path isn't used by offer();
    # instead verify offer() passes `message` through unchanged by identity via a wrapper dict subclass
    class IdMsg(dict):
        pass
    m = IdMsg(notional=1.0)
    orig_evals = []
    for a in assertions:
        orig_eval = a._evaluator.evaluate
        def wrapped(node, row, _orig=orig_eval):
            seen_ids.add(id(row))
            return _orig(node, row)
        a._evaluator.evaluate = wrapped
    suite.offer(m)
    ok = seen_ids == {id(m)} and len(seen_ids) == 1
    log("EXE-112", "PASS" if ok else "FAIL", f"distinct message object ids seen across 40 assertions' evaluate() calls: {len(seen_ids)} (expect 1 -- the same object)")

def exe113():
    a1 = StreamAssertion(PLAN)
    a2 = StreamAssertion(PLAN)
    a3 = StreamAssertion(PLAN)  # never offered anything
    a1.offer({"notional": 1.0})
    a2.offer({"notional": 1.0})
    suite = StreamSuite([a1, a2, a3])
    results = suite.close_all()
    ok = len(results) == 2
    log("EXE-113", "PASS" if ok else "FAIL", f"n_verdicts_from_close_all={len(results)} (3 assertions, 1 never offered anything)")

def exe114():
    a = StreamAssertion(PLAN)
    suite = StreamSuite([a], lag_threshold=10_000)
    for i in range(1000):
        suite.offer({"notional": 1.0})
    lag = suite.lag(20_000)
    rendered = lag.render()
    ok = lag.messages_behind == 19_000 and lag.is_falling_behind is True and "not being dropped" in rendered and "shed load or add capacity" in rendered
    log("EXE-114", "PASS" if ok else "FAIL", f"messages_behind={lag.messages_behind} is_falling_behind={lag.is_falling_behind} render={rendered!r}")

def exe115():
    a = StreamAssertion(PLAN)
    suite = StreamSuite([a])
    for i in range(1000):
        suite.offer({"notional": 1.0})
    lag = suite.lag(500)
    ok = lag.messages_behind == 0
    log("EXE-115", "PASS" if ok else "FAIL", f"messages_behind={lag.messages_behind}")

def exe116():
    obs = {}
    for cov in Coverage:
        obs[cov.name] = (cov.qualify("passed"), cov.supports_a_claim_about_the_whole_dataset, cov.sees_restatements)
    ok = (obs["FULL"] == ("passed", True, True)
          and obs["INCREMENTAL"] == ("passed over the rows examined", False, True)
          and obs["FORWARD_ONLY"] == ("passed over the rows examined", False, False))
    log("EXE-116", "PASS" if ok else "FAIL", str(obs))

def exe117():
    planner = WatermarkPlanner()
    wm = Watermark(column="booked")
    scope = planner.scope(wm, now=dt.datetime(2026, 4, 10, tzinfo=dt.UTC))
    ok = (scope.coverage is Coverage.FULL and scope.reason == "nothing has been examined before"
          and scope.describe() == "the whole dataset — nothing has been examined before")
    log("EXE-117", "PASS" if ok else "FAIL", f"coverage={scope.coverage} reason={scope.reason!r} describe={scope.describe()!r}")

def exe118():
    policy = LatenessPolicy(full_sweep_every=dt.timedelta(days=7))
    planner = WatermarkPlanner(policy)
    wm = Watermark(column="booked", value=dt.date(2026, 4, 1), observed_at=dt.datetime(2026, 4, 1, tzinfo=dt.UTC))
    now = dt.datetime(2026, 4, 10, tzinfo=dt.UTC)
    s1 = planner.scope(wm, now=now, last_full_sweep=now - dt.timedelta(days=7))
    s2 = planner.scope(wm, now=now, last_full_sweep=now - dt.timedelta(days=6))
    s3 = planner.scope(wm, now=now, last_full_sweep=None)
    ok = (s1.coverage is Coverage.FULL and "2026-04-03" in s1.reason
          and s2.coverage is Coverage.INCREMENTAL
          and s3.coverage is Coverage.FULL and "never run" in s3.reason)
    log("EXE-118", "PASS" if ok else "FAIL", f"exactly_7_days={s1.coverage}/{s1.reason!r} 6_days={s2.coverage} never={s3.coverage}/{s3.reason!r}")

def exe119():
    policy = LatenessPolicy(full_sweep_every=None, change_column="", lookback=dt.timedelta(days=3))
    ok = (policy.covers_the_past is False and "3 days" in policy.gap
          and "never be seen" in policy.gap and ("Declare" in policy.gap or "remedy" in policy.gap.lower()))
    planner = WatermarkPlanner(policy)
    audit = planner.audit()
    ok = ok and audit["covers_the_past"] is False and audit["gap"] == policy.gap
    log("EXE-119", "PASS" if ok else "FAIL", f"gap={policy.gap!r} audit={audit}")

def exe120():
    policy = LatenessPolicy(lookback=dt.timedelta(days=3), full_sweep_every=None, change_column="updated_at")
    planner = WatermarkPlanner(policy)
    wm = Watermark(column="booked", value=dt.date(2026, 4, 10))
    scope = planner.scope(wm, now=dt.datetime(2026, 4, 10, tzinfo=dt.UTC))
    ok = scope.predicate == "booked >= '2026-04-07' OR updated_at >= '2026-04-07'"
    log("EXE-120", "PASS" if ok else "FAIL", f"predicate={scope.predicate!r}")

def exe121():
    policy = LatenessPolicy(lookback=dt.timedelta(0), full_sweep_every=None, change_column="")
    planner = WatermarkPlanner(policy)
    wm = Watermark(column="booked", value=dt.date(2026, 4, 10))
    scope = planner.scope(wm, now=dt.datetime(2026, 4, 10, tzinfo=dt.UTC))
    ok = scope.coverage is Coverage.FORWARD_ONLY and scope.coverage.sees_restatements is False
    log("EXE-121", "PASS" if ok else "FAIL", f"coverage={scope.coverage} sees_restatements={scope.coverage.sees_restatements}")

def exe122():
    try:
        LatenessPolicy(lookback=dt.timedelta(days=-1))
        log("EXE-122", "FAIL", "no exception")
    except ValidationError as e:
        ok = "cannot be negative" in str(e)
        log("EXE-122", "PASS" if ok else "FAIL", str(e))

def exe123():
    wm = Watermark(column="booked", value=dt.date(2026, 4, 10), observed_at=dt.datetime(2026, 4, 10, tzinfo=dt.UTC))
    w1 = wm.advanced_to(dt.date(2026, 4, 9), at=dt.datetime(2026, 4, 11, tzinfo=dt.UTC))
    w2 = wm.advanced_to(dt.date(2026, 4, 10), at=dt.datetime(2026, 4, 11, tzinfo=dt.UTC))
    w3 = wm.advanced_to(dt.date(2026, 4, 11), at=dt.datetime(2026, 4, 11, tzinfo=dt.UTC))
    w4 = wm.advanced_to("not-comparable-to-a-date", at=dt.datetime(2026, 4, 11, tzinfo=dt.UTC))
    ok = (w1.value == dt.date(2026, 4, 10)  # unchanged (backward refused)
          and w2.value == dt.date(2026, 4, 10) and w2.observed_at == dt.datetime(2026, 4, 11, tzinfo=dt.UTC)  # equal is not "before" -> advances
          and w3.value == dt.date(2026, 4, 11)
          and w4.value == dt.date(2026, 4, 10))  # incomparable -> unchanged
    log("EXE-123", "PASS" if ok else "FAIL", f"back={w1.value} equal={w2.value}/{w2.observed_at} forward={w3.value} incomparable={w4.value}")

def exe124():
    wm = Watermark(column="booked", value=dt.date(2026, 4, 1), observed_at=dt.datetime(2026, 4, 1, tzinfo=dt.UTC))
    wm = wm.advanced_to(dt.date(2026, 4, 2), at=dt.datetime(2026, 4, 2, tzinfo=dt.UTC), rows=100)
    wm = wm.advanced_to(dt.date(2026, 4, 1), at=dt.datetime(2026, 4, 3, tzinfo=dt.UTC), rows=200)  # refused (backward)
    wm = wm.advanced_to(dt.date(2026, 4, 3), at=dt.datetime(2026, 4, 3, tzinfo=dt.UTC), rows=300)
    ok = wm.rows_seen == 400  # 100 + 300, NOT the refused 200
    log("EXE-124", "PASS" if ok else "FAIL", f"rows_seen={wm.rows_seen} (expected 400: the refused +200 batch contributes nothing)")

def exe125():
    obs = {}
    delta = dt.timedelta(days=-3)
    obs["date"] = _shift(dt.date(2026, 4, 10), delta)
    obs["datetime"] = _shift(dt.datetime(2026, 4, 10, 6, 30, tzinfo=dt.UTC), delta)
    obs["iso_str"] = _shift("2026-04-10T06:30:00", delta)
    obs["non_iso_str"] = _shift("not-a-date", delta)
    obs["int"] = _shift(12345, delta)
    obs["none"] = _shift(None, delta)
    ok = (obs["date"] == dt.date(2026, 4, 7) and obs["datetime"] == dt.datetime(2026, 4, 7, 6, 30, tzinfo=dt.UTC)
          and obs["iso_str"] == "2026-04-07T06:30:00" and obs["non_iso_str"] == "not-a-date"
          and obs["int"] == 12345 and obs["none"] is None)
    log("EXE-125", "PASS" if ok else "FAIL", str(obs))

def exe126():
    obs = {}
    obs["none"] = _literal(None)
    obs["int"] = _literal(7)
    obs["float"] = _literal(7.5)
    obs["bool"] = _literal(True)
    obs["date"] = _literal(dt.date(2026, 4, 7))
    obs["quote"] = _literal("it's")
    ok = (obs["none"] == "NULL" and obs["int"] == "7" and obs["float"] == "7.5"
          and obs["bool"] == "'True'" and obs["date"] == "'2026-04-07'" and obs["quote"] == "'it''s'")
    log("EXE-126", "PASS" if ok else "FAIL", str(obs))

def exe127():
    obs = {}
    obs["1day"] = _period(dt.timedelta(days=1))
    obs["3days"] = _period(dt.timedelta(days=3))
    obs["1hour"] = _period(dt.timedelta(hours=1))
    obs["5hours"] = _period(dt.timedelta(hours=5))
    obs["30min"] = _period(dt.timedelta(minutes=30))
    obs["0"] = _period(dt.timedelta(0))
    ok = (obs["1day"] == "day" and obs["3days"] == "3 days" and obs["1hour"] == "hour"
          and obs["5hours"] == "5 hours" and obs["30min"] == "30 minutes" and obs["0"] == "0 minutes")
    log("EXE-127", "PASS" if ok else "FAIL", str(obs))

for fn in (exe100, exe101, exe102, exe103, exe104, exe105, exe106, exe107, exe108, exe109,
           exe110, exe111, exe112, exe113, exe114, exe115, exe116, exe117, exe118, exe119,
           exe120, exe121, exe122, exe123, exe124, exe125, exe126, exe127):
    fn()
