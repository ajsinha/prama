import sys, math
from datetime import date, datetime, timedelta
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.core.calendars import WEEKDAYS
from prama.monitor.season import (
    SeasonalModel, SeasonKey, Facet, Grouping, MINIMUM_GROUP, COMFORTABLE_GROUP,
    month_end_driver, weekday_driver, nth_weekday_driver, day_of_month_driver,
)

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

model = SeasonalModel(calendar=WEEKDAYS)

# MON-056 - period_end last business day of period; month ending on Sunday
# Find a month that ends on Sunday. e.g. 2026-05-31 is a Sunday? check.
import calendar as cal_mod
def find_month_ending_on(weekday_target):
    for year in range(2020, 2035):
        for month in range(1,13):
            last = cal_mod.monthrange(year, month)[1]
            d = date(year, month, last)
            if d.weekday() == weekday_target:
                return d
    return None
sunday_end = find_month_ending_on(6)  # Sunday=6
friday_before = sunday_end - timedelta(days=2)
pe_friday = model.period_end(friday_before)
pe_sunday = model.period_end(sunday_end)
ok = pe_friday == "month" and pe_sunday == "none"
line("MON-056", "PASS" if ok else "FAIL", f"month_end_sunday={sunday_end} friday={friday_before} pe_friday={pe_friday} pe_sunday={pe_sunday}")

# MON-057 - year > quarter > month ordering
pe_dec31 = model.period_end(date(2025,12,31))  # Wed
pe_mar31 = model.period_end(date(2026,3,31))  # Tue
pe_apr30 = model.period_end(date(2026,4,30))  # Thu
ok = pe_dec31 == "year" and pe_mar31 == "quarter" and pe_apr30 == "month"
line("MON-057", "PASS" if ok else "FAIL", f"dec31={pe_dec31} mar31={pe_mar31} apr30={pe_apr30}")

# MON-058 - non-business day never a period end
sat_end = find_month_ending_on(5)  # Saturday=5
pe_sat = model.period_end(sat_end)
ok = pe_sat == "none"
line("MON-058", "PASS" if ok else "FAIL", f"sat_end={sat_end} pe={pe_sat}")

# MON-059 - grouping key includes every configured facet
drivers = {"payroll": day_of_month_driver(15), "rebalance": nth_weekday_driver(4,3)}
m2 = SeasonalModel(calendar=WEEKDAYS, intraday=True, drivers=drivers)
moment = datetime(2026,1,15,14,0,0)
k = m2.key(moment)
names = [n for n,v in k.facets]
ok = "business_day" in names and "period_end" in names and "day_of_week" in names and "hour" in names and "declared:payroll" in names and "declared:rebalance" in names
line("MON-059", "PASS" if ok else "FAIL", f"facet_names={names}")

# MON-060 - drivers sorted deterministically regardless of registration order
d1 = {"zzz": day_of_month_driver(1), "aaa": day_of_month_driver(2)}
d2 = {"aaa": day_of_month_driver(2), "zzz": day_of_month_driver(1)}
m_a = SeasonalModel(calendar=WEEKDAYS, drivers=d1)
m_b = SeasonalModel(calendar=WEEKDAYS, drivers=d2)
ka = m_a.key(datetime(2026,1,15,0,0,0))
kb = m_b.key(datetime(2026,1,15,0,0,0))
ok = ka.facets == kb.facets
line("MON-060", "PASS" if ok else "FAIL", f"ka={ka.facets} kb={kb.facets}")

# MON-061 - grouping stops at first usable, most specific first; year end -> ~24 period ends not 500
history = []
d = date(2024,1,1)
while d < date(2026,1,1):
    if WEEKDAYS.is_business_day(d):
        history.append(datetime(d.year,d.month,d.day))
    d += timedelta(days=1)
year_end = date(2025,12,31)  # confirmed 'year' above? check business day
target_moment = datetime(2025,12,31)
g = model.group(history, target_moment)
ok = g.size < 50 and g.size >= MINIMUM_GROUP
line("MON-061", "PASS" if ok else "FAIL", f"group_size={g.size} key={g.key.render()} relaxed={[f.value for f in g.relaxed]}")

# MON-062 - facet blurred before dropped: period_end not in relaxed for MON-061 scenario
ok = Facet.PERIOD_END not in g.relaxed
line("MON-062", "PASS" if ok else "FAIL", f"relaxed={[f.value for f in g.relaxed]} period_end_key={dict(g.key.facets).get('period_end')}")

# MON-063 - relaxation order: hour, day_of_week, period_end, business_day
m3 = SeasonalModel(calendar=WEEKDAYS, intraday=True)
target_key = m3.key(datetime(2025,12,31,10,0,0))
order = m3._relaxation_order(target_key)
ok = order == (Facet.HOUR, Facet.DAY_OF_WEEK, Facet.PERIOD_END, Facet.BUSINESS_DAY)
line("MON-063", "PASS" if ok else "FAIL", f"order={[f.value for f in order]}")

# MON-064 - declared driver dropped last / survives every relaxation - check thin history + final fallback
drivers2 = {"rare": day_of_month_driver(31)}
m4 = SeasonalModel(calendar=WEEKDAYS, drivers=drivers2, intraday=True)
# thin history: only 5 points, all distinct facets, forcing full relaxation
thin_history = [datetime(2026,1,5,9,0), datetime(2026,1,6,10,0), datetime(2026,1,7,11,0),
                 datetime(2026,1,8,12,0), datetime(2026,1,9,13,0)]
target_moment4 = datetime(2026,1,12,14,0)
g4 = m4.group(thin_history, target_moment4)
declared_survives_in_key = any(name.startswith("declared:") for name,_ in g4.key.facets)
declared_in_relaxed = any(f == Facet.DECLARED for f in g4.relaxed)
fell_back_to_everything = g4.size == len(thin_history)
# Expected: "the driver survives every relaxation, including the final fall-back" --
# i.e. declared_survives_in_key should be True. Observed: the total fallback returns
# SeasonKey() (empty), which drops the declared facet along with everything else,
# AND relaxed=tuple(order) never includes Facet.DECLARED (order is [HOUR,DAY_OF_WEEK,
# PERIOD_END,BUSINESS_DAY], DECLARED is not in it) -- so the loss is not even reported.
ok = fell_back_to_everything and declared_survives_in_key
line("MON-064", "PASS" if ok else "FAIL", f"final_key={g4.key.facets} declared_survives_in_key={declared_survives_in_key} relaxed={[f.value for f in g4.relaxed]} declared_in_relaxed={declared_in_relaxed} (expected the driver to survive the fallback; it does not, and its loss is not reported in `relaxed` either)")

# MON-065 - group below minimum never returned: exactly 19 vs 20
# construct 19 identical-key business days plus enough padding of a different key so relaxation would find only these matches
history19 = [datetime(2026,1,d) for d in range(1,20) if WEEKDAYS.is_business_day(date(2026,1,d))]
# note weekdays in Jan 2026 - count may not be 19; let's construct directly using synthetic keys via mocking not possible; test group() using minimum param instead
m5 = SeasonalModel(calendar=WEEKDAYS, minimum=20)
# build history of 19 Mondays (all same day_of_week, non-period-end, business day) plus far padding
mondays = []
dd = date(2020,1,6)  # a Monday
count = 0
while count < 19:
    if WEEKDAYS.is_business_day(dd) and dd.weekday()==0 and model.period_end(dd)=="none":
        mondays.append(datetime(dd.year,dd.month,dd.day,9,0))
        count += 1
    dd += timedelta(days=1)
target5 = datetime(2026,6,1,9,0)  # a Monday, ordinary
while not (WEEKDAYS.is_business_day(target5.date()) and target5.weekday()==0 and model.period_end(target5.date())=="none"):
    target5 += timedelta(days=1)
g19 = m5.group(mondays, target5)
ok19 = g19.size != 19 or Facet.DAY_OF_WEEK in g19.relaxed  # relaxed past since <20 -> should not stop at exact monday match
# Now add a 20th
dd2 = mondays[-1] + timedelta(days=7)
while not (WEEKDAYS.is_business_day(dd2.date()) and dd2.weekday()==0 and model.period_end(dd2.date())=="none"):
    dd2 += timedelta(days=1)
mondays20 = mondays + [dd2]
g20 = m5.group(mondays20, target5)
ok = (g19.size != 19 or Facet.DAY_OF_WEEK in g19.relaxed) and g20.size >= 20
line("MON-065", "PASS" if ok else "FAIL", f"g19_size={g19.size} g19_relaxed={[f.value for f in g19.relaxed]} g20_size={g20.size} g20_relaxed={[f.value for f in g20.relaxed]}")

# MON-066 - with nothing specific enough, everything compared and says so
history25 = []
dd3 = date(2020,1,1)
count=0
while count < 25:
    if WEEKDAYS.is_business_day(dd3):
        history25.append(datetime(dd3.year,dd3.month,dd3.day, dd3.day % 24))
        count += 1
    dd3 += timedelta(days=90)  # spread out to get variety of weekdays/period-ends
m6 = SeasonalModel(calendar=WEEKDAYS, intraday=True, minimum=30)  # minimum higher than history size forces total fallback
target6 = datetime(2026,3,31,10,0)  # ordinary-ish moment
g6 = m6.group(history25, target6)
desc = g6.describe()
ok = g6.size == 25 and set(g6.relaxed) == {Facet.HOUR, Facet.DAY_OF_WEEK, Facet.PERIOD_END, Facet.BUSINESS_DAY} and "ignored" in desc
line("MON-066", "PASS" if ok else "FAIL", f"size={g6.size} relaxed={[f.value for f in g6.relaxed]} describe={desc!r}")

# MON-067 - resolution = 1/(n+1)
members = tuple(range(24))
g7 = Grouping(key=SeasonKey(), members=members)
res = g7.resolution
desc7 = g7.describe()
ok = abs(res - 1/25) < 1e-9 and "0.040" in desc7
line("MON-067", "PASS" if ok else "FAIL", f"resolution={res} describe={desc7!r}")

# MON-068 - resolution of empty group is 1.0
g8 = Grouping(key=SeasonKey(), members=())
ok = g8.resolution == 1.0
line("MON-068", "PASS" if ok else "FAIL", f"resolution={g8.resolution}")

# MON-069 - describe names group size, key, resolution caveat, dropped facets
g9 = Grouping(key=SeasonKey(facets=(("business_day","True"),)), members=tuple(range(15)),
              relaxed=(Facet.HOUR, Facet.DAY_OF_WEEK))
desc9 = g9.describe()
ok = "15" in desc9 and "business_day=True" in desc9 and "p-value" in desc9 and "hour" in desc9 and "day_of_week" in desc9
line("MON-069", "PASS" if ok else "FAIL", f"describe={desc9!r}")

# MON-070 - _matches accepts coarsened facet members
target_any = SeasonKey(facets=(("period_end","any"),))
cand_month = SeasonKey(facets=(("period_end","month"),))
cand_quarter = SeasonKey(facets=(("period_end","quarter"),))
cand_year = SeasonKey(facets=(("period_end","year"),))
cand_none = SeasonKey(facets=(("period_end","none"),))
results = [SeasonalModel._matches(c, target_any) for c in [cand_month, cand_quarter, cand_year, cand_none]]
ok = results == [True, True, True, False]
line("MON-070", "PASS" if ok else "FAIL", f"results={results}")

# MON-071 - month_end_driver identifies exactly 12 true days over a year (month ends, incl quarter/year)
driver = month_end_driver(WEEKDAYS)
d = date(2026,1,1)
count = 0
true_days = []
while d < date(2027,1,1):
    if driver(d):
        count += 1
        true_days.append(d)
    d += timedelta(days=1)
ok = count == 12
line("MON-071", "PASS" if ok else "FAIL", f"count={count} days={true_days}")

# MON-072 - nth_weekday_driver third Friday
driver72 = nth_weekday_driver(4, 3)
d = date(2026,1,1)
count72 = 0
days72 = []
while d < date(2027,1,1):
    if driver72(d):
        count72 += 1
        days72.append(d)
    d += timedelta(days=1)
ok = count72 == 12 and all(dd.weekday()==4 and 15<=dd.day<=21 for dd in days72)
line("MON-072", "PASS" if ok else "FAIL", f"count={count72} days={days72}")

# MON-073 - day_of_month_driver(31) handles month without that day
driver73 = day_of_month_driver(31)
d = date(2026,1,1)
count73 = 0
feb_count = 0
while d < date(2027,1,1):
    if driver73(d):
        count73 += 1
        if d.month == 2:
            feb_count += 1
    d += timedelta(days=1)
ok = count73 == 7 and feb_count == 0
line("MON-073", "PASS" if ok else "FAIL", f"count={count73} feb_count={feb_count}")

# MON-074 - driver is a predicate (callable date->bool)
driver74 = month_end_driver()
result74 = driver74(date(2026,1,31))
ok = isinstance(result74, bool)
line("MON-074", "PASS" if ok else "FAIL", f"type={type(result74)} value={result74}")
