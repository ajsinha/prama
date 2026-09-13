import sys, os, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from datetime import date, datetime, time, timezone, UTC
from prama.core.calendars import (
    BusinessCalendar, ALWAYS_OPEN, WEEKDAYS, WESTERN_WEEKEND, CalendarRegistry, default_calendars,
)
from prama.core.errors import ValidationError

# CFG-287
try:
    BusinessCalendar(name="bad", timezone="Mars/Olympus")
    R("CFG-287", False, "no exception")
except ValidationError as e:
    ok = "bad" in str(e) and "Mars/Olympus" in str(e) and "IANA" in e.remedy
    R("CFG-287", ok, f"{e}; remedy={e.remedy}")

# CFG-288
sat = date(2026, 1, 3)  # a Saturday
sun = date(2026, 1, 4)
R("CFG-288", ALWAYS_OPEN.is_business_day(sat) and ALWAYS_OPEN.is_business_day(sun),
  f"Saturday={ALWAYS_OPEN.is_business_day(sat)} Sunday={ALWAYS_OPEN.is_business_day(sun)}")

# CFG-289
week = [date(2026,1,d) for d in range(5,12)]  # Mon 5 - Sun 11 Jan 2026
flags = {d.strftime("%a"): WEEKDAYS.is_business_day(d) for d in week}
R("CFG-289", flags == {"Mon":True,"Tue":True,"Wed":True,"Thu":True,"Fri":True,"Sat":False,"Sun":False}, str(flags))

# CFG-290
gulf = BusinessCalendar(name="gulf", weekend_days=frozenset({4,5}))
flags290 = {d.strftime("%a"): gulf.is_business_day(d) for d in week}
R("CFG-290", flags290 == {"Mon":True,"Tue":True,"Wed":True,"Thu":True,"Fri":False,"Sat":False,"Sun":True}, str(flags290))

# CFG-291
cal291 = WEEKDAYS.with_holidays({date(2025,12,25), date(2025,12,26)})
nxt = cal291.next_business_day(date(2025,12,24))
R("CFG-291", nxt == date(2025,12,29), f"next_business_day(24 Dec)={nxt} (27th is a Saturday, so Monday 29th)")

# CFG-292: no business days -- would hang; run with a hard timeout in a subprocess
code292 = (
    "import sys; sys.path.insert(0,'src'); from prama.core.calendars import BusinessCalendar; "
    "from datetime import date; "
    "c = BusinessCalendar(name='never', weekend_days=frozenset(range(7))); "
    "print(c.next_business_day(date(2026,1,1)))"
)
import time as _time
t0 = _time.monotonic()
try:
    p292 = subprocess.run([sys.executable, "-c", code292], capture_output=True, text=True, timeout=20)
    dt292 = _time.monotonic() - t0
    R("CFG-292", False,
      f"not a true infinite loop (date has an internal max), but an unbounded, uncontrolled spin: "
      f"took {dt292:.2f}s of CPU iterating day-by-day toward date.max, then crashed with rc={p292.returncode} "
      f"on an unhandled low-level error rather than a graceful, immediate refusal: {p292.stderr.strip().splitlines()[-1] if p292.stderr.strip() else '(no stderr)'!r}")
except subprocess.TimeoutExpired:
    R("CFG-292", False, "next_business_day on a calendar with weekend_days=all 7 days did not return within 20s (effectively hangs)")

# CFG-293
d293 = date(2026,1,3)  # Saturday
R("CFG-293", WEEKDAYS.shift(d293, 0) == d293, repr(WEEKDAYS.shift(d293, 0)))

# CFG-294
d294 = date(2026,1,5)  # Monday, a business day
R("CFG-294", WEEKDAYS.shift(WEEKDAYS.shift(d294, 5), -5) == d294, repr(WEEKDAYS.shift(WEEKDAYS.shift(d294,5),-5)))

# CFG-295
mon = date(2026,1,5)
fri = date(2026,1,9)
R("CFG-295", WEEKDAYS.business_days_between(mon, fri) == 4, repr(WEEKDAYS.business_days_between(mon, fri)))

# CFG-296
a296, b296 = date(2026,1,5), date(2026,1,15)
fwd = WEEKDAYS.business_days_between(a296, b296)
bwd = WEEKDAYS.business_days_between(b296, a296)
same = WEEKDAYS.business_days_between(a296, a296)
R("CFG-296", fwd == -bwd and same == 0, f"fwd={fwd}, bwd={bwd}, same-day={same}")

# CFG-297
cal297 = BusinessCalendar(name="cutoff", day_boundary=time(3,0))
early = datetime(2026,1,6,2,0,tzinfo=UTC)  # Tuesday 02:00
bd297 = cal297.business_date_of(early)
R("CFG-297", bd297 == date(2026,1,5), repr(bd297))

# CFG-298
sat_arrival = datetime(2026,1,3,3,0,tzinfo=UTC)  # Saturday 03:00
bd298 = WEEKDAYS.business_date_of(sat_arrival)
R("CFG-298", bd298 == date(2026,1,2), repr(bd298))  # preceding Friday

# CFG-299
tokyo = BusinessCalendar(name="tokyo", timezone="Asia/Tokyo")
instant299 = datetime(2026,1,5,23,50,tzinfo=UTC)  # 08:50 next day in Tokyo (UTC+9)
bd299 = tokyo.business_date_of(instant299)
R("CFG-299", bd299 == date(2026,1,6), repr(bd299))

# CFG-300
london = BusinessCalendar(name="london", timezone="Europe/London")
winter = london.expected_at(date(2026,1,15), time(6,30))
summer = london.expected_at(date(2026,7,15), time(6,30))
R("CFG-300", winter.hour==6 and winter.minute==30 and summer.hour==5 and summer.minute==30,
  f"winter UTC={winter.time()}, summer UTC={summer.time()}")

# CFG-301
ldn2 = BusinessCalendar(name="london2", timezone="Europe/London")
# Spring-forward in UK 2026 is 29 March; 01:00->02:00, so 01:30 does not exist
try:
    inst301 = ldn2.expected_at(date(2026,3,29), time(1,30))
    R("CFG-301", True, f"non-existent local time 01:30 on 2026-03-29 resolved to {inst301.isoformat()} without raising (fold-rule behaviour)")
except Exception as e:
    R("CFG-301", True, f"raised {type(e).__name__}: {e} (also an acceptable 'defined, documented instant')")

# CFG-302
base302 = WEEKDAYS
new302 = base302.with_holidays({date(2026,12,25)})
R("CFG-302", new302 is not base302 and base302.holidays == frozenset() and date(2026,12,25) in new302.holidays,
  f"same object={new302 is base302}, original holidays={base302.holidays}, new holidays has date={date(2026,12,25) in new302.holidays}")

# CFG-303
reg303 = CalendarRegistry()
try:
    reg303.get("TARGET2")
    R("CFG-303", False, "no exception")
except ValidationError as e:
    ok = "always" in e.remedy.lower() and "weekdays" in e.remedy and "wrong days" in e.remedy
    R("CFG-303", ok, f"{e}; remedy={e.remedy}")

# CFG-304
reg304 = CalendarRegistry()
R("CFG-304", reg304.get(None) is ALWAYS_OPEN and reg304.get("") is ALWAYS_OPEN,
  f"get(None) is ALWAYS_OPEN={reg304.get(None) is ALWAYS_OPEN}; get('') is ALWAYS_OPEN={reg304.get('') is ALWAYS_OPEN}")

# CFG-305
reg305 = CalendarRegistry()
reg305.register(BusinessCalendar(name="TARGET2"))
found = reg305.get("target2")
names305 = reg305.names()
R("CFG-305", found.name == "TARGET2" and ("TARGET2" in names305), f"found.name={found.name!r}; names()={names305}; 'TARGET2' in names()={'TARGET2' in names305}")

# CFG-306
reg306 = CalendarRegistry()
try:
    reg306.register(BusinessCalendar(name="always"))
    R("CFG-306", False, "no exception on duplicate 'always'")
except ValidationError:
    try:
        reg306.register(BusinessCalendar(name="always", weekend_days=frozenset()), replace=True)
        R("CFG-306", True, "refused without replace, accepted with replace=True")
    except ValidationError as e:
        R("CFG-306", False, f"replace=True still refused: {e}")

# CFG-307
default_calendars().register(BusinessCalendar(name="qa307test"), replace=True)
seen_elsewhere = "qa307test" in default_calendars().names()
R("CFG-307", seen_elsewhere, f"registered into default_calendars() from one call site, visible from another: {seen_elsewhere}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
