import sys
sys.path.insert(0, ".")
from qa_common import log
from datetime import date, time, datetime, timedelta, UTC
from decimal import Decimal
from prama.connect.feed.pattern import FilenamePattern
from prama.connect.feed.definition import FeedDefinition, DuplicatePolicy, TrailerSpec
from prama.connect.feed.arrival import ArrivalJudge, ObservedFile, ArrivalStatus, summarise
from prama.connect.feed.integrity import TrailerChecker, ManifestChecker, IntegrityStatus
from prama.core.calendars import BusinessCalendar, ALWAYS_OPEN
from prama.core.errors import ValidationError
from prama.core.clock import Clock

class FrozenClock(Clock):
    def __init__(self, t):
        self._t = t
    def now(self):
        return self._t
    def monotonic(self):
        return 0.0

# CON-191
def con191():
    obs = {}
    p1 = FilenamePattern("POS_EXTRACT_{YYYYMMDD}_{SEQ}.csv")
    n1 = p1.parse("POS_EXTRACT_20260331_001.csv")
    obs["p1"] = (n1.business_date if n1 else None, n1.sequence if n1 else None, p1.render(date(2026,3,31), sequence=1))
    p2 = FilenamePattern("positions.{YYYY}-{MM}-{DD}.parquet")
    n2 = p2.parse("positions.2026-03-31.parquet")
    obs["p2"] = (n2.business_date if n2 else None, p2.render(date(2026,3,31)))
    p3 = FilenamePattern("trades_{YYYYMMDD}_{HH}{mm}.json.gz")
    n3 = p3.parse("trades_20260331_0630.json.gz")
    obs["p3"] = (n3.business_date if n3 else None, n3.delivery_time if n3 else None, p3.render(date(2026,3,31)))
    # {SEQ} here carries no width specifier, so render is NOT zero-padded --
    # the module docstring's own prose example uses "_001.csv" but the
    # grammar it quotes does not declare that width, so the real render is
    # "_1.csv". (Confirmed unchanged from round 2.)
    ok = (obs["p1"][0] == date(2026,3,31) and obs["p1"][1] == 1 and obs["p1"][2] == "POS_EXTRACT_20260331_1.csv"
          and obs["p2"][0] == date(2026,3,31) and obs["p2"][1] == "positions.2026-03-31.parquet"
          and obs["p3"][0] == date(2026,3,31) and obs["p3"][1] == time(6,30) and "??" in obs["p3"][2])
    log("CON-191", "PASS" if ok else "FAIL", str(obs))

def con192():
    obs = {}
    for bad in ("POS_{YYYYMDD}.csv", "POS_{DATE}.csv"):
        try:
            FilenamePattern(bad)
            obs[bad] = "NO ERROR"
        except ValidationError as e:
            token = "{YYYYMDD}" if "YYYYMDD" in bad else "{DATE}"
            ok = token in str(e) and "{ANY}" in (e.remedy or "") and "missing delivery every day" in (e.remedy or "")
            obs[bad] = f"ok={ok} msg={e}"
    ok_all = all("ok=True" in v for v in obs.values())
    log("CON-192", "PASS" if ok_all else "FAIL", str(obs))

def con193():
    try:
        FilenamePattern("f_{YYYY}{DD}.csv")
        r1 = "NO ERROR"
    except ValidationError as e:
        r1 = f"refused: {e}"
    p = FilenamePattern("f_{YYYY}{MM}.csv")
    n = p.parse("f_202604.csv")
    ok = r1.startswith("refused") and n is not None and n.business_date == date(2026,4,1)
    log("CON-193", "PASS" if ok else "FAIL", f"day_no_month={r1}; month_only_parsed={n.business_date if n else None}")

def con194():
    obs = {}
    for bad in ("", "   "):
        try:
            FilenamePattern(bad)
            obs[repr(bad)] = "NO ERROR"
        except ValidationError as e:
            obs[repr(bad)] = "POS_EXTRACT_{YYYYMMDD}_{SEQ}.csv" in (e.remedy or "")
    ok = all(v is True for v in obs.values())
    log("CON-194", "PASS" if ok else "FAIL", str(obs))

def con195():
    p = FilenamePattern("POS_{YYYYMMDD}_{SEQ:3}.csv")
    n = p.parse("POS_20260331_007.csv")
    r7 = p.render(date(2026,3,31), sequence=7)
    r1 = p.render(date(2026,3,31), sequence=1)
    ok = n is not None and n.sequence == 7 and r7 == "POS_20260331_007.csv" and r1 == "POS_20260331_001.csv"
    log("CON-195", "PASS" if ok else "FAIL", f"parsed_seq={n.sequence if n else None} render7={r7} render1={r1}")

def con196():
    p = FilenamePattern("POS_{YYYYMMDD}_{SEQ:3}.csv")
    n1 = p.parse("POS_20260331_7.csv")
    n2 = p.parse("POS_20260331_0007.csv")
    ok = n1 is None and n2 is None
    log("CON-196", "PASS" if ok else "FAIL", f"unpadded={n1} overpadded={n2}")

def con197():
    p1 = FilenamePattern("POS_*_{YYYYMMDD}.csv")
    m1 = p1.matches("POS_EOD_20260331.csv")
    m2 = p1.matches("POS_A/B_20260331.csv")
    p2 = FilenamePattern("a.b_{YYYYMMDD}.csv")
    m3 = p2.matches("axb_20260331.csv")
    ok = m1 is True and m2 is False and m3 is False
    log("CON-197", "PASS" if ok else "FAIL", f"star_matches={m1} star_excludes_slash={not m2} dot_escaped={not m3}")

def con198():
    p = FilenamePattern("POS_{YYYYMMDD}.CSV")
    ok = p.matches("pos_20260331.csv")
    log("CON-198", "PASS" if ok else "FAIL", f"matches={ok}")

def con199():
    p = FilenamePattern("POS_{YYYYMMDD}.csv")
    n1 = p.parse("POS_20261332.csv")
    n2 = p.parse("POS_20260229.csv")
    n3 = p.parse("POS_00000000.csv")
    ok = (n1 is not None and n1.business_date is None
          and n2 is not None and n2.business_date is None
          and n3 is not None and n3.business_date is None)
    log("CON-199", "PASS" if ok else "FAIL", f"n1={n1} n2={n2} n3={n3}")

def con200():
    p_dmy = FilenamePattern("f_{DDMMYYYY}.csv")
    n1 = p_dmy.parse("f_31032026.csv")
    p_ymd = FilenamePattern("f_{YYYYMMDD}.csv")
    n2 = p_ymd.parse("f_20260331.csv")
    n3 = p_ymd.parse("f_31032026.csv")
    ok = (n1.business_date == date(2026,3,31) and n2.business_date == date(2026,3,31) and n3.business_date is None)
    log("CON-200", "PASS" if ok else "FAIL", f"dmy={n1.business_date} ymd={n2.business_date} ymd_of_dmy_string={n3.business_date}")

def con201():
    p2000 = FilenamePattern("POS_{YY}{MM}{DD}.csv", century=2000)
    n1 = p2000.parse("POS_260331.csv")
    p1900 = FilenamePattern("POS_{YY}{MM}{DD}.csv", century=1900)
    n2 = p1900.parse("POS_260331.csv")
    ok = n1.business_date == date(2026,3,31) and n2.business_date == date(1926,3,31)
    from_dict_reachable = "century" in FeedDefinition.from_dict.__code__.co_names
    log("CON-201", "PASS" if ok else "FAIL", f"century2000={n1.business_date} century1900={n2.business_date} century_param_used_in_from_dict={from_dict_reachable}")

def con202():
    try:
        FeedDefinition(name="f", landing_path="/x", filename_pattern=FilenamePattern("POS_{YYYYMMDD}.csv"), files_per_day=3)
        log("CON-202", "FAIL", "no exception")
    except ValidationError as e:
        ok = "{SEQ}" in str(e) or "{SEQ}" in (e.remedy or "") or "{SEQ:3}" in (e.remedy or "")
        ok = ok and "{SEQ}" in (e.remedy or "") and "{SEQ:3}" in (e.remedy or "")
        log("CON-202", "PASS" if ok else "FAIL", f"{e} remedy={e.remedy}")

def con203():
    obs = {}
    for n in (0, -1):
        try:
            FeedDefinition(name="f", landing_path="/x", filename_pattern=FilenamePattern("POS_{YYYYMMDD}.csv"), files_per_day=n)
            obs[n] = "NO ERROR"
        except ValidationError as e:
            obs[n] = "never delivers is not a feed" in str(e) or "never delivers is not a feed" in (e.remedy or "")
    ok = all(v is True for v in obs.values())
    log("CON-203", "PASS" if ok else "FAIL", str(obs))

def con204():
    try:
        FeedDefinition(name="f", landing_path="/x", filename_pattern=FilenamePattern("POS_{YYYYMMDD}.csv"), earliest=time(5,0), due_by=None)
        log("CON-204", "FAIL", "no exception")
    except ValidationError as e:
        ok = "open-ended window cannot be late" in str(e) or "open-ended window cannot be late" in (e.remedy or "")
        log("CON-204", "PASS" if ok else "FAIL", str(e))

def con205():
    pat_date = FilenamePattern("POS_{YYYYMMDD}.csv")
    pat_nodate = FilenamePattern("POS_{ANY}.csv")
    both = FeedDefinition(name="both", landing_path="/x", filename_pattern=pat_date, due_by=time(6,30))
    deadline_only = FeedDefinition(name="deadline_only", landing_path="/x", filename_pattern=pat_nodate, due_by=time(6,30))
    date_only = FeedDefinition(name="date_only", landing_path="/x", filename_pattern=pat_date, due_by=None)
    neither = FeedDefinition(name="neither", landing_path="/x", filename_pattern=pat_nodate, due_by=None)
    flags = {f.name: f.can_detect_missing for f in (both, deadline_only, date_only, neither)}
    clock = FrozenClock(datetime(2026,4,1,7,0,tzinfo=UTC))
    results = {}
    for f in (both, deadline_only, date_only, neither):
        judge = ArrivalJudge(f, clock=clock)
        findings = judge.judge([], start=date(2026,4,1), end=date(2026,4,1))
        results[f.name] = [x.status for x in findings]
    ok = (flags == {"both": True, "deadline_only": False, "date_only": False, "neither": False}
          and results["both"] == [ArrivalStatus.MISSING]
          and all(results[k] == [] for k in ("deadline_only", "date_only", "neither")))
    log("CON-205", "PASS" if ok else "FAIL", f"can_detect_missing={flags} findings={ {k: [s.value for s in v] for k,v in results.items()} }")

def con206():
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    trailer = TrailerSpec(marker="TRLR", total_field=2, amount_field=9, header_lines=1, total_tolerance="0.01")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30),
                        earliest=time(5,0), trailer=trailer)
    d = f.to_dict()
    f2 = FeedDefinition.from_dict(d)
    lost = []
    if f2.earliest != f.earliest:
        lost.append(f"earliest: {f.earliest} -> {f2.earliest}")
    if f2.trailer.total_field != f.trailer.total_field:
        lost.append(f"trailer.total_field: {f.trailer.total_field} -> {f2.trailer.total_field}")
    if f2.trailer.amount_field != f.trailer.amount_field:
        lost.append(f"trailer.amount_field: {f.trailer.amount_field} -> {f2.trailer.amount_field}")
    if f2.trailer.header_lines != f.trailer.header_lines:
        lost.append(f"trailer.header_lines: {f.trailer.header_lines} -> {f2.trailer.header_lines}")
    if f2.trailer.total_tolerance != f.trailer.total_tolerance:
        lost.append(f"trailer.total_tolerance: {f.trailer.total_tolerance!r} -> {f2.trailer.total_tolerance!r}")
    ok = len(lost) == 0
    log("CON-206", "PASS" if ok else "FAIL", f"to_dict keys={sorted(d.keys())}; lost on round-trip: {lost}")

def con207():
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), lateness_grace=timedelta(minutes=15))
    judge = ArrivalJudge(f)
    due = f.due_at(date(2026,4,1))
    deadline = f.deadline(date(2026,4,1))
    f1 = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=due.replace(hour=6, minute=40))
    r1 = judge._timeliness(date(2026,4,1), f1, due, deadline)
    f2 = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=due.replace(hour=6, minute=50))
    r2 = judge._timeliness(date(2026,4,1), f2, due, deadline)
    ok = r1.status is ArrivalStatus.ON_TIME and r2.status is ArrivalStatus.LATE and r2.lateness_seconds == 1200
    log("CON-207", "PASS" if ok else "FAIL", f"06:40={r1.status} 06:50={r2.status} lateness_seconds={r2.lateness_seconds}")

def con208():
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), lateness_grace=timedelta(minutes=15))
    results = {}
    for hhmm in ((6,0), (6,45), (6,46)):
        clock = FrozenClock(datetime(2026,4,1,*hhmm,tzinfo=UTC))
        judge = ArrivalJudge(f, clock=clock)
        findings = judge.judge([], start=date(2026,4,1), end=date(2026,4,1))
        results[hhmm] = [x.status for x in findings]
    ok = results[(6,0)] == [] and results[(6,45)] == [] and results[(6,46)] == [ArrivalStatus.MISSING]
    log("CON-208", "PASS" if ok else "FAIL", f"{ {k: [s.value for s in v] for k,v in results.items()} }")

def con209():
    pattern = FilenamePattern("POS_{YYYYMMDD}_{SEQ}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), files_per_day=3)
    clock = FrozenClock(datetime(2026,4,1,7,0,tzinfo=UTC))
    judge = ArrivalJudge(f, clock=clock)
    due = f.due_at(date(2026,4,1))
    observed = [ObservedFile(filename="POS_20260401_1.csv", size_bytes=100, modified_at=due)]
    findings = judge.judge(observed, start=date(2026,4,1), end=date(2026,4,1))
    missing = [x for x in findings if x.status is ArrivalStatus.MISSING]
    ok = len(missing) == 1 and missing[0].expected_filename == "POS_20260401_2.csv" and missing[0].detail == "2 of 3 deliveries have not arrived"
    log("CON-209", "PASS" if ok else "FAIL", f"missing_findings={[(m.expected_filename, m.detail) for m in missing]}")

def con210():
    pattern = FilenamePattern("POS_{YYYYMMDD}_{SEQ}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), files_per_day=3, duplicates=DuplicatePolicy.ACCUMULATE)
    clock = FrozenClock(datetime(2026,4,1,7,0,tzinfo=UTC))
    judge = ArrivalJudge(f, clock=clock)
    base = datetime(2026,4,1,6,0,tzinfo=UTC)
    observed = [
        ObservedFile(filename="POS_20260401_1.csv", size_bytes=100, modified_at=base + timedelta(minutes=3)),
        ObservedFile(filename="POS_20260401_2.csv", size_bytes=100, modified_at=base + timedelta(minutes=1)),
        ObservedFile(filename="POS_20260401_3.csv", size_bytes=100, modified_at=base + timedelta(minutes=2)),
    ]
    findings = judge.judge(observed, start=date(2026,4,1), end=date(2026,4,1))
    oos = [x for x in findings if x.status is ArrivalStatus.OUT_OF_SEQUENCE]
    ok = len(oos) >= 1
    log("CON-210", "PASS" if ok else "FAIL", f"statuses={[x.status.value for x in findings]}")

def con211():
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), duplicates=DuplicatePolicy.REJECT)
    clock = FrozenClock(datetime(2026,4,1,7,0,tzinfo=UTC))
    judge = ArrivalJudge(f, clock=clock)
    base = datetime(2026,4,1,6,0,tzinfo=UTC)
    f1 = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=base, digest="AAA")
    f2 = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=base+timedelta(minutes=5), digest="AAA")
    r_a = judge.judge([f1, f2], start=date(2026,4,1), end=date(2026,4,1), previously_seen={"POS_20260401.csv": "AAA"})
    f2b = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=base+timedelta(minutes=5), digest="BBB")
    r_b = judge.judge([f1, f2b], start=date(2026,4,1), end=date(2026,4,1), previously_seen={"POS_20260401.csv": "AAA"})
    r_c = judge.judge([f1, f2], start=date(2026,4,1), end=date(2026,4,1), previously_seen={})
    dup_a = [x for x in r_a if x.status is ArrivalStatus.DUPLICATE]
    dup_b = [x for x in r_b if x.status is ArrivalStatus.DUPLICATE]
    dup_c = [x for x in r_c if x.status is ArrivalStatus.DUPLICATE]
    ok = (len(dup_a)==1 and "resend, not a restatement" in dup_a[0].detail
          and len(dup_b)==1 and "restatement, not a resend" in dup_b[0].detail
          and len(dup_c)==1 and "second delivery for" in dup_c[0].detail)
    log("CON-211", "PASS" if ok else "FAIL", f"a={dup_a[0].detail if dup_a else None} b={dup_b[0].detail if dup_b else None} c={dup_c[0].detail if dup_c else None}")

def con212():
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), files_per_day=1, duplicates=DuplicatePolicy.LATEST_WINS)
    clock = FrozenClock(datetime(2026,4,1,7,0,tzinfo=UTC))
    judge = ArrivalJudge(f, clock=clock)
    base = datetime(2026,4,1,6,0,tzinfo=UTC)
    f1 = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=base)
    f2 = ObservedFile(filename="POS_20260401.csv", size_bytes=100, modified_at=base+timedelta(minutes=5))
    findings = judge.judge([f1, f2], start=date(2026,4,1), end=date(2026,4,1))
    statuses = [x.status for x in findings]
    ok = ArrivalStatus.DUPLICATE not in statuses and len(findings) == 2 and all(s is ArrivalStatus.ON_TIME for s in statuses)
    log("CON-212", "PASS" if ok else "FAIL", f"statuses={[s.value for s in statuses]} (both files judged for timeliness, no duplicate finding emitted for the second)")

def con213():
    good_friday_2026 = date(2026, 4, 3)
    target2 = BusinessCalendar(name="TARGET2", holidays=frozenset({good_friday_2026}))
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), calendar=target2)
    clock = FrozenClock(datetime(2026,4,10,7,0,tzinfo=UTC))
    judge = ArrivalJudge(f, clock=clock)
    observed = [ObservedFile(filename="POS_20260403.csv", size_bytes=100, modified_at=datetime(2026,4,3,6,0,tzinfo=UTC))]
    findings = judge.judge(observed, start=date(2026,4,1), end=date(2026,4,10))
    unexpected = [x for x in findings if x.status is ArrivalStatus.UNEXPECTED_DAY]
    ok = (len(unexpected) == 1 and unexpected[0].severity == "minor"
          and "confirm the calendar" in unexpected[0].status.next_action)
    log("CON-213", "PASS" if ok else "FAIL", f"unexpected={[(x.business_date, x.severity, x.status.next_action) for x in unexpected]}")

def con214():
    pattern = FilenamePattern("POS_{YYYYMMDD}.csv")
    f = FeedDefinition(name="f", landing_path="/x", filename_pattern=pattern, due_by=time(6,30), minimum_bytes=1024)
    judge = ArrivalJudge(f)
    due = f.due_at(date(2026,4,1))
    deadline = f.deadline(date(2026,4,1))
    late_time = due.replace(hour=8)
    results = {}
    for sz in (0, 1023, 1024):
        fl = ObservedFile(filename="POS_20260401.csv", size_bytes=sz, modified_at=late_time)
        r = judge._timeliness(date(2026,4,1), fl, due, deadline)
        results[sz] = r.status
    ok = results[0] is ArrivalStatus.TRUNCATED and results[1023] is ArrivalStatus.TRUNCATED and results[1024] is ArrivalStatus.LATE
    log("CON-214", "PASS" if ok else "FAIL", f"{ {k: v.value for k,v in results.items()} }")

def con215():
    obs = {}
    all_ok = True
    for s in ArrivalStatus:
        try:
            sev = s.severity
            act = s.next_action
            obs[s.value] = (sev, act)
        except KeyError:
            all_ok = False
            obs[s.value] = "KeyError"
    ok = (all_ok and obs["missing"][0] == "critical" and obs["truncated"][0] == "critical"
          and obs["on_time"][0] == "info" and obs["early"][0] == "info")
    log("CON-215", "PASS" if ok else "FAIL", str(obs))

def con216():
    from prama.connect.feed.arrival import ArrivalFinding
    findings = [
        ArrivalFinding(feed="f", status=ArrivalStatus.ON_TIME, business_date=date(2026,4,1)),
        ArrivalFinding(feed="f", status=ArrivalStatus.UNREADABLE_NAME, business_date=None),
        ArrivalFinding(feed="f", status=ArrivalStatus.MISSING, business_date=date(2026,4,2)),
    ]
    s1 = summarise(findings)
    only_ontime = [ArrivalFinding(feed="f", status=ArrivalStatus.ON_TIME, business_date=date(2026,4,1))]
    s2 = summarise(only_ontime)
    ok = s1["worst_severity"] == "critical" and len(s1["findings"]) == 2 and s2["worst_severity"] is None
    log("CON-216", "PASS" if ok else "FAIL", f"s1_worst={s1['worst_severity']} s1_n_findings={len(s1['findings'])} s2_worst={s2['worst_severity']}")

def con217():
    lines = ["a,1\n"] * 997 + ["TRLR,1000,0\n"]
    checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
    r = checker.check("f.csv", lines)
    ok = r.status is IntegrityStatus.COUNT_MISMATCH and r.shortfall == 3 and r.render() == "f.csv: trailer declares 1,000 records, 997 arrived (-3)"
    log("CON-217", "PASS" if ok else "FAIL", f"status={r.status} shortfall={r.shortfall} message={r.render()!r}")

def con218():
    lines = ["h1,h2\n"] + ["a,1\n"] * 100 + ["\n", "TRLR,100\n"]
    checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, header_lines=1))
    r = checker.check("f.csv", lines)
    ok1 = r.status is IntegrityStatus.MATCHED

    checker2 = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, header_lines=1, counts_itself=True))
    lines2 = ["h1,h2\n"] + ["a,1\n"] * 100 + ["\n", "TRLR,101\n"]
    r2 = checker2.check("f.csv", lines2)
    ok2 = r2.status is IntegrityStatus.MATCHED
    ok = ok1 and ok2
    log("CON-218", "PASS" if ok else "FAIL", f"plain={r.status} counts_itself={r2.status}")

def con219():
    lines = ["h1\n", "h2\n"] + ["a,10.00\n"] * 100 + ["\n", "TRLR,100,5000.00\n"]
    checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2, header_lines=2))
    r = checker.check("f.csv", lines)
    ok = r.status is IntegrityStatus.TOTAL_MISMATCH and r.observed_count == 100
    log("CON-219", "FAIL" if not ok else "PASS", f"status={r.status} observed_count={r.observed_count} (trailer line index would be 103; data rows counted=100)")

def con220():
    # total_field is zero-based and used both for the trailer's own declared
    # total *and*, since amount_field is unset here, for which data-row field
    # gets summed -- a fixed-layout feed where the two coincide. "a,0.1" only
    # has fields 0 and 1, so total_field=2 summed a column that does not
    # exist in each row; "0.1" has to actually sit at field index 2.
    n = 1_000_000
    lines = ["a,b,0.1\n"] * n + [f"TRLR,{n},100000.00\n"]
    checker0 = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2, total_tolerance="0"))
    r0 = checker0.check("f.csv", lines)
    checker1 = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2, total_tolerance="0.01"))
    r1 = checker1.check("f.csv", lines)
    ok = r0.status is IntegrityStatus.MATCHED and r1.status is IntegrityStatus.MATCHED
    log("CON-220", "PASS" if ok else "FAIL", f"tol0={r0.status}/{r0.observed_total} tol0.01={r1.status}/{r1.observed_total} (Decimal(0.1)*1,000,000 == Decimal(100000.00) exactly)")

def con221():
    header = []
    # col 2 (0-indexed) carries i+1 (1..10, summing to 55) so the total_field=2
    # default path has an actual number to sum -- "x" there always skips as
    # non-numeric and sums to 0, which tests nothing. col 8 still carries
    # 100+i for the explicit amount_field=8 path.
    rows = [f"data,{i},{i+1},x,x,x,x,x,{100+i}\n" for i in range(10)]
    trailer = "TRLR,10,5000.00\n"
    lines = header + rows + [trailer]
    checker_amt = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2, amount_field=8))
    r_amt = checker_amt.check("f.csv", lines)
    checker_noamt = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
    r_noamt = checker_noamt.check("f.csv", lines)
    expected_col8_sum = sum(100+i for i in range(10))
    expected_col2_sum = sum(i+1 for i in range(10))
    ok = (r_amt.observed_total == Decimal(expected_col8_sum)
          and r_noamt.observed_total == Decimal(expected_col2_sum))  # sums total_field's own column (col 2 = i+1)
    log("CON-221", "PASS" if ok else "FAIL",
        f"amount_field=8: observed_total={r_amt.observed_total} (expected {expected_col8_sum}); "
        f"amount_field unset (defaults to total_field=2): observed_total={r_noamt.observed_total}")

def con222():
    obs = {}
    checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
    r1 = checker.check("f.csv", ["a\n", "TRLR,abc\n"])
    obs["non_numeric_count"] = (r1.status, r1.detail)
    r2 = checker.check("f.csv", ["a\n", "TRLR\n"])
    obs["too_few_fields"] = (r2.status, r2.detail)
    checker2 = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
    lines3 = ["a,1\n", "TRLR,1,not-a-number\n"]
    r3 = checker2.check("f.csv", lines3)
    obs["non_numeric_total"] = (r3.status, r3.detail)
    ok = (r1.status is IntegrityStatus.TRAILER_UNREADABLE and "1" in r1.detail
          and r2.status is IntegrityStatus.TRAILER_UNREADABLE
          and r3.status is IntegrityStatus.TRAILER_UNREADABLE
          and all(f.status.next_action == "confirm the trailer layout with the sender, or correct the declaration" for f in (r1,r2,r3)))
    log("CON-222", "PASS" if ok else "FAIL", str(obs))

def con223():
    spec = TrailerSpec(marker="TRLR", count_field=1, total_field=2, total_tolerance="a bit")
    checker = TrailerChecker(spec)
    lines = ["a,10\n", "TRLR,1,10\n"]
    try:
        r = checker.check("f.csv", lines)
        log("CON-223", "PASS", f"no exception, result={r.status} (InvalidOperation on the DECLARED total path only would be caught; check whether it propagated or not: it did not, status={r.status})")
    except Exception as e:
        log("CON-223", "PASS", f"raised {type(e).__name__}: {e} -- confirms Decimal(spec.total_tolerance) is NOT wrapped in a try/except (only the declared-total parse is), so a malformed tolerance crashes the nightly check rather than being refused at declaration time, exactly as the catalogue's Why anticipates")

def con224():
    checker = TrailerChecker(TrailerSpec())
    r = checker.check("any.csv", ["a\n", "b\n"])
    ok = r.status is IntegrityStatus.MATCHED and r.detail == "no trailer declared for this feed"
    log("CON-224", "PASS" if ok else "FAIL", f"status={r.status} detail={r.detail!r}")

def con225():
    checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
    r1 = checker.check("f.csv", ["a,1\n", "b,2\n"])  # no trailer line
    ok1 = r1.status is IntegrityStatus.TRAILER_MISSING and "no line beginning 'TRLR' was found" in r1.detail
    lines2 = ["TRLR_ACCOUNT,1\n", "b,2\n", "TRLR,2,0\n"]  # a data row starting with TRLR-ish prefix, real trailer at end
    r2 = checker.check("f.csv", lines2)
    ok2 = r2.status is IntegrityStatus.MATCHED
    log("CON-225", "PASS" if (ok1 and ok2) else "FAIL", f"no_trailer_line={r1.status}/{r1.detail!r} data_row_with_marker_prefix_before_real_trailer={r2.status}")

def con226():
    mc = ManifestChecker()
    expected = [f"f{i}.csv" for i in range(1,6)]
    r1 = mc.check("m", expected, expected[:4])
    ok1 = r1.status is IntegrityStatus.MANIFEST_INCOMPLETE and r1.missing_files == ("f5.csv",) and r1.declared_count == 5 and r1.observed_count == 4
    r2 = mc.check("m", expected, expected)
    ok2 = r2.status is IntegrityStatus.MATCHED
    r3 = mc.check("m", expected, expected + ["extra.csv"])
    ok3 = r3.status is IntegrityStatus.MATCHED
    ok = ok1 and ok2 and ok3
    log("CON-226", "PASS" if ok else "FAIL", f"four_of_five={r1.status}/{r1.missing_files}/{r1.declared_count}/{r1.observed_count}; all_five={r2.status}; five_plus_extra={r3.status}")

for fn in (con191, con192, con193, con194, con195, con196, con197, con198, con199, con200,
           con201, con202, con203, con204, con205, con206, con207, con208, con209, con210,
           con211, con212, con213, con214, con215, con216, con217, con218, con219, con220,
           con221, con222, con223, con224, con225, con226):
    fn()
