import sys, math, asyncio
sys.path.insert(0, ".")
from qa_common import log
from datetime import date, datetime, timedelta, UTC
from prama.profile.segments import Segmentation, Segment, SegmentGrain, MAX_SEGMENTS, _literal
from prama.core.errors import ValidationError

def q(ident):
    return f'"{ident.replace(chr(34), chr(34)*2)}"'

def pro064():
    s = Segmentation("booked", SegmentGrain.DAY)
    segs = s.over_dates(date(2026,3,30), date(2026,4,1))
    keys = [x.key for x in segs]
    ok1 = keys == ["2026-03-30", "2026-03-31", "2026-04-01"]
    ok1 = ok1 and segs[0].lower == date(2026,3,30) and segs[0].upper == date(2026,3,31)
    single = s.over_dates(date(2026,4,1), date(2026,4,1))
    ok2 = len(single) == 1
    log("PRO-064", "PASS" if (ok1 and ok2) else "FAIL", f"keys={keys} single_day_count={len(single)}")

def pro065():
    s = Segmentation("booked", SegmentGrain.MONTH)
    segs = s.over_dates(date(2026,11,15), date(2027,2,3))
    keys = [x.key for x in segs]
    dec = next(x for x in segs if x.key == "2026-12")
    ok = keys == ["2026-11", "2026-12", "2027-01", "2027-02"] and dec.upper == date(2027,1,1)
    log("PRO-065", "PASS" if ok else "FAIL", f"keys={keys} dec.upper={dec.upper}")

def pro066():
    s = Segmentation("booked", SegmentGrain.DAY)
    try:
        s.over_dates(date(2026,4,1), date(2026,3,1))
        log("PRO-066", "FAIL", "no exception")
    except ValidationError as e:
        ok = "ends before it begins" in str(e) and "earlier date first" in (e.remedy or "")
        log("PRO-066", "PASS" if ok else "FAIL", f"{e} remedy={e.remedy}")

def pro067():
    s = Segmentation("booked", SegmentGrain.DAY)
    ok2000 = len(s.over_dates(date(2020,1,1), date(2020,1,1)+timedelta(days=1999))) == 2000
    try:
        s.over_dates(date(2020,1,1), date(2020,1,1)+timedelta(days=2000))
        r2001 = "NO ERROR"
    except ValidationError as e:
        r2001 = f"refused: {e.context}"
    try:
        s.over_values([str(i) for i in range(2001)])
        r2001v = "NO ERROR"
    except ValidationError as e:
        r2001v = f"refused: {e.context}"
    ok = ok2000 and "refused" in r2001 and "refused" in r2001v
    log("PRO-067", "PASS" if ok else "FAIL", f"2000_days_ok={ok2000} 2001_days={r2001} 2001_values={r2001v}")

def pro068():
    s1 = Segmentation("region", SegmentGrain.VALUE)
    s2 = Segmentation("", SegmentGrain.NONE)
    obs = {}
    for name, s in (("VALUE", s1), ("NONE", s2)):
        try:
            s.over_dates(date(2026,1,1), date(2026,1,2))
            obs[name] = "NO ERROR"
        except ValidationError as e:
            obs[name] = "over_values" in (e.remedy or "")
    ok = obs["VALUE"] is True and obs["NONE"] is True
    log("PRO-068", "PASS" if ok else "FAIL", str(obs))

def pro069():
    try:
        Segmentation("", SegmentGrain.DAY)
        r1 = "NO ERROR"
    except ValidationError as e:
        r1 = f"refused, remedy={e.remedy}"
    try:
        s = Segmentation("", SegmentGrain.NONE)
        r2 = "OK"
    except ValidationError as e:
        r2 = f"refused: {e}"
    ok = r1.startswith("refused") and "business date" in r1 and r2 == "OK"
    log("PRO-069", "PASS" if ok else "FAIL", f"day_no_column={r1} none_no_column={r2}")

def pro070():
    s = Segmentation("region", SegmentGrain.VALUE)
    segs = s.over_values(["EMEA", None, "APAC", "EMEA", 3, "3"])
    keys = [x.key for x in segs]
    ok = len(segs) == 4 and keys == sorted(keys) and "None" not in keys
    threes = [x for x in segs if x.key == "3"]
    ok = ok and len(threes) == 2 and {x.value for x in threes} == {3, "3"}
    log("PRO-070", "PASS" if ok else "FAIL", f"n={len(segs)} keys={keys} three_segments_values={[x.value for x in threes]}")

def pro071():
    seg = Segment(key="k", column='desk"name', grain=SegmentGrain.VALUE, value="O'Brien Desk")
    pred = seg.predicate(q)
    ok = pred == '"desk""name" = \'O\'\'Brien Desk\''
    log("PRO-071", "PASS" if ok else "FAIL", pred)

def pro072():
    from datetime import datetime as DT
    obs = {}
    for label, v in (("none", None), ("true", True), ("false", False), ("int", 7), ("float", 7.5),
                      ("nan", float("nan")), ("inf", float("inf")), ("date", date(2026,4,1)),
                      ("datetime", DT(2026,4,1,6,30)), ("str", "x")):
        obs[label] = _literal(v)
    expected = {"none": "NULL", "true": "1", "false": "0", "int": "7", "float": "7.5",
                "nan": "nan", "inf": "inf", "date": "'2026-04-01'", "datetime": "'2026-04-01T06:30:00'", "str": "'x'"}
    ok = obs == expected
    log("PRO-072", "PASS" if ok else "FAIL", str(obs))

def pro073():
    seg = Segment(key="all", column="c", grain=SegmentGrain.NONE)
    pred = seg.predicate(q)
    ok = pred == '"c" >= NULL AND "c" < NULL'
    log("PRO-073", "PASS" if ok else "FAIL", pred)

for fn in (pro064, pro065, pro066, pro067, pro068, pro069, pro070, pro071, pro072, pro073):
    fn()
