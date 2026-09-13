import sys, traceback
from datetime import date, timedelta
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

from prama.packs.banking.holidays import (
    easter_sunday, Rule, Observance, observed, MONDAY, SATURDAY, SUNDAY
)
from prama.core.errors import ValidationError

@block("PCK-001")
def _():
    got = [easter_sunday(y).isoformat() for y in (2024,2025,2026,2027)]
    exp = ["2024-03-31","2025-04-20","2026-04-05","2027-03-28"]
    R("PCK-001", got==exp, str(got))

@block("PCK-002")
def _():
    got = [easter_sunday(y).isoformat() for y in (1900,2000,2100,2038)]
    exp = ["1900-04-15","2000-04-23","2100-03-28","2038-04-25"]
    R("PCK-002", got==exp, str(got))

@block("PCK-003")
def _():
    r = Rule(name="Good Friday", kind="easter", offset=-2)
    d = r.dates_in(2026)[0]
    R("PCK-003", d.isoformat()=="2026-04-03" and d.weekday()==4, f"{d.isoformat()} weekday={d.weekday()}")

@block("PCK-004")
def _():
    r = Rule(name="Easter Monday", kind="easter", offset=1)
    d = r.dates_in(2026)[0]
    R("PCK-004", d.isoformat()=="2026-04-06" and d.weekday()==0, f"{d.isoformat()} weekday={d.weekday()}")

@block("PCK-005")
def _():
    r = Rule(name="Christmas Day", kind="fixed", month=12, day=25)
    got = r.dates_in(2025)
    R("PCK-005", [d.isoformat() for d in got]==["2025-12-25"], str(got))

@block("PCK-006")
def _():
    r1 = Rule(name="x", kind="nth_weekday", month=1, nth=3, weekday=MONDAY)
    r2 = Rule(name="x", kind="nth_weekday", month=2, nth=3, weekday=MONDAY)
    r3 = Rule(name="x", kind="nth_weekday", month=11, nth=4, weekday=3)
    got = [r1.dates_in(2026)[0].isoformat(), r2.dates_in(2026)[0].isoformat(), r3.dates_in(2026)[0].isoformat()]
    exp = ["2026-01-19","2026-02-16","2026-11-26"]
    R("PCK-006", got==exp, str(got))

@block("PCK-007")
def _():
    # first Monday June 2026, 2026-06-01 is Monday
    r = Rule(name="x", kind="nth_weekday", month=6, nth=1, weekday=MONDAY)
    d = r.dates_in(2026)[0]
    R("PCK-007", d.isoformat()=="2026-06-01", f"{d.isoformat()} (2026-06-01 weekday={date(2026,6,1).weekday()})")

@block("PCK-008")
def _():
    r1 = Rule(name="x", kind="last_weekday", month=5, weekday=MONDAY)
    r2 = Rule(name="x", kind="last_weekday", month=8, weekday=MONDAY)
    got = [r1.dates_in(2026)[0].isoformat(), r2.dates_in(2026)[0].isoformat()]
    R("PCK-008", got==["2026-05-25","2026-08-31"], str(got))

@block("PCK-009")
def _():
    r = Rule(name="x", kind="last_weekday", month=12, weekday=MONDAY)
    d = r.dates_in(2026)[0]
    R("PCK-009", d.isoformat()=="2026-12-28", d.isoformat())

@block("PCK-010")
def _():
    r = Rule(name="x", kind="last_weekday", month=2, weekday=MONDAY)
    got = [r.dates_in(2024)[0].isoformat(), r.dates_in(2025)[0].isoformat()]
    R("PCK-010", got==["2024-02-26","2025-02-24"], str(got))

@block("PCK-011")
def _():
    r = Rule(name="x", kind="lunar")
    try:
        r.dates_in(2026)
        R("PCK-011", False, "no exception raised")
    except ValidationError as e:
        ok = "lunar" in str(e) and all(k in str(e.remedy if hasattr(e,'remedy') else e) for k in ["fixed","easter","nth_weekday","last_weekday"])
        R("PCK-011", ok, f"{e}; remedy={getattr(e,'remedy',None)}")

@block("PCK-012")
def _():
    r = Rule(name="Labour Day", kind="fixed", month=5, day=1, observance=Observance.NONE)
    got = r.dates_in(2021)
    R("PCK-012", [d.isoformat() for d in got]==["2021-05-01"], str(got))

@block("PCK-013")
def _():
    r = Rule(name="Independence Day", kind="fixed", month=7, day=4, observance=Observance.SUNDAY_TO_MONDAY)
    d2027 = r.dates_in(2027)
    d2026 = r.dates_in(2026)
    R("PCK-013", [d.isoformat() for d in d2027]==["2027-07-05"] and [d.isoformat() for d in d2026]==["2026-07-04"],
      f"2027={[d.isoformat() for d in d2027]} 2026={[d.isoformat() for d in d2026]}")

@block("PCK-014")
def _():
    r = Rule(name="Independence Day", kind="fixed", month=7, day=4, observance=Observance.NEAREST_WEEKDAY)
    d2026 = r.dates_in(2026)
    d2027 = r.dates_in(2027)
    R("PCK-014", [d.isoformat() for d in d2026]==["2026-07-03"] and [d.isoformat() for d in d2027]==["2027-07-05"],
      f"2026={[d.isoformat() for d in d2026]} 2027={[d.isoformat() for d in d2027]}")

@block("PCK-015")
def _():
    r = Rule(name="Christmas Day", kind="fixed", month=12, day=25, observance=Observance.NEAREST_WEEKDAY)
    got = r.dates_in(2027)
    R("PCK-015", len(got)==1 and got[0].isoformat()=="2027-12-24", str(got))

@block("PCK-016")
def _():
    r = Rule(name="New Year's Day", kind="fixed", month=1, day=1, observance=Observance.ROLL_FORWARD)
    got = observed([r], [2022])
    R("PCK-016", date(2022,1,3) in got, str(sorted(got)))

@block("PCK-017")
def _():
    from prama.packs.banking.calendars import LONDON_RULES
    closed = observed(LONDON_RULES, [2021])
    R("PCK-017", date(2021,12,27) in closed and date(2021,12,28) in closed, str([d for d in sorted(closed) if d.year==2021 and d.month==12]))

@block("PCK-018")
def _():
    from prama.packs.banking.calendars import LONDON_RULES
    reversed_rules = tuple(reversed(LONDON_RULES))
    closed1 = observed(LONDON_RULES, [2021])
    closed2 = observed(reversed_rules, [2021])
    dec1 = sorted(d for d in closed1 if d.month==12)
    dec2 = sorted(d for d in closed2 if d.month==12)
    R("PCK-018", dec1==dec2, f"orig={dec1} reversed={dec2}")

@block("PCK-019")
def _():
    # 3 consecutive ROLL_FORWARD fixed holidays landing Fri/Sat/Sun
    # pick a year: need 3 consecutive dates on fri/sat/sun. Use fixed rules on arbitrary dates in a chosen year.
    # 2027-01-01 is Friday
    r1 = Rule(name="a", kind="fixed", month=1, day=1, observance=Observance.ROLL_FORWARD)
    r2 = Rule(name="b", kind="fixed", month=1, day=2, observance=Observance.ROLL_FORWARD)
    r3 = Rule(name="c", kind="fixed", month=1, day=3, observance=Observance.ROLL_FORWARD)
    closed = observed([r1,r2,r3], [2027])
    jan = sorted(d for d in closed if d.month==1)
    weekdays = [d.weekday() for d in jan]
    R("PCK-019", len(jan)==3 and all(w<5 for w in weekdays), f"{jan} weekdays={weekdays}")

@block("PCK-020")
def _():
    r = Rule(name="Juneteenth", kind="fixed", month=6, day=19, since=2021)
    R("PCK-020", r.dates_in(2020)==() and len(r.dates_in(2021))==1, f"2020={r.dates_in(2020)} 2021={r.dates_in(2021)}")

@block("PCK-021")
def _():
    from prama.packs.banking.calendars import FEDERAL_RESERVE_RULES, NYSE_RULES
    fed_closed = date(2021,6,19) in observed(FEDERAL_RESERVE_RULES, [2021])
    nyse_closed = date(2021,6,19) in observed(NYSE_RULES, [2021])
    R("PCK-021", fed_closed and not nyse_closed, f"fed={fed_closed} nyse={nyse_closed}")

@block("PCK-022")
def _():
    r = Rule(name="x", kind="fixed", month=1, day=1, until=2025)
    R("PCK-022", r.applies_in(2025) and not r.applies_in(2026), f"2025={r.applies_in(2025)} 2026={r.applies_in(2026)}")

@block("PCK-023")
def _():
    from prama.packs.banking.calendars import TARGET2_RULES
    closed = observed(TARGET2_RULES, [2026])
    bastille = date(2026,7,14) not in closed
    german = date(2026,10,3) not in closed
    R("PCK-023", bastille and german and len(TARGET2_RULES)==6, f"bastille_open={bastille} german_open={german} rules={len(TARGET2_RULES)}")

@block("PCK-024")
def _():
    from prama.packs.banking.calendars import FEDERAL_RESERVE_RULES, NYSE_RULES
    fed_closed = date(2026,4,3) in observed(FEDERAL_RESERVE_RULES, [2026])
    nyse_closed = date(2026,4,3) in observed(NYSE_RULES, [2026])
    R("PCK-024", not fed_closed and nyse_closed, f"fed_closed={fed_closed} nyse_closed={nyse_closed}")

@block("PCK-025")
def _():
    from prama.packs.banking.calendars import FEDERAL_RESERVE_RULES, NYSE_RULES
    columbus = date(2026,10,12)  # second Monday of Oct 2026? check
    veterans = date(2026,11,11)
    fed_c = columbus in observed(FEDERAL_RESERVE_RULES, [2026])
    nyse_c = columbus in observed(NYSE_RULES, [2026])
    fed_v = veterans in observed(FEDERAL_RESERVE_RULES, [2026])
    nyse_v = veterans in observed(NYSE_RULES, [2026])
    R("PCK-025", fed_c and not nyse_c and fed_v and not nyse_v, f"columbus={columbus} fed_c={fed_c} nyse_c={nyse_c} fed_v={fed_v} nyse_v={nyse_v}")

@block("PCK-026")
def _():
    from prama.packs.banking.calendars import LONDON_RULES
    closed = observed(LONDON_RULES, [2026])
    scot = date(2026,1,2) not in closed
    ni = date(2026,3,17) not in closed
    R("PCK-026", scot and ni, f"scot_open={scot} ni_open={ni}")

@block("PCK-027")
def _():
    from prama.packs.banking.calendars import SPECS
    import zoneinfo
    zones = {}
    for s in SPECS:
        zoneinfo.ZoneInfo(s.timezone)
        zones[s.name] = s.timezone
    exp_ok = zones.get("TARGET2")=="Europe/Brussels" and zones.get("London")=="Europe/London" and zones.get("FederalReserve")=="America/New_York" and zones.get("NYSE")=="America/New_York"
    R("PCK-027", exp_ok, str(zones))

@block("PCK-028")
def _():
    from prama.packs.banking.calendars import spec
    cal = spec("TARGET2").materialise()
    checks = {
        "2015-01-01": date(2015,1,1) in cal.holidays,
        "2040-12-25": date(2040,12,25) in cal.holidays,
        "2014-12-25": date(2014,12,25) in cal.holidays,
        "2041-12-25": date(2041,12,25) in cal.holidays,
    }
    ok = checks["2015-01-01"] and checks["2040-12-25"] and not checks["2014-12-25"] and not checks["2041-12-25"]
    R("PCK-028", ok, str(checks))

@block("PCK-029")
def _():
    from prama.packs.banking.calendars import spec
    cal = spec("TARGET2").materialise()
    # 2041-12-25 weekday?
    d = date(2041,12,25)
    result = cal.is_business_day(d)
    R("PCK-029", result is not True, f"is_business_day({d})={result} (weekday={d.weekday()}); expected a refusal naming horizon, not True")

print("=== PCK 001-029 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
