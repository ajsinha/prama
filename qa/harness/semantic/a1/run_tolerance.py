import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.semantic.relationships import Tolerance, TimeOffset, OffsetUnit
from prama.core.errors import ValidationError

def report(cid, ok, observed):
    print(f"### {cid} :: {'PASS' if ok else 'FAIL'} :: {observed}")

def expect_raises(fn, exc_types=(ValidationError,)):
    try:
        fn()
        return None, "NO EXCEPTION RAISED"
    except exc_types as e:
        return e, None
    except Exception as e:
        return None, f"WRONG EXCEPTION: {type(e).__name__}: {e}"

# SEM-070
t = Tolerance(absolute=1.00)
r = t.permits(difference=0.50, magnitude=1_000_000)
report("SEM-070", r is True, f"permits(0.50, 1_000_000)={r}")

# SEM-071
t = Tolerance(absolute=1.00)
r = t.permits(1.00, 1_000_000)
report("SEM-071", r is True, f"permits(1.00, 1_000_000)={r}")

# SEM-072
t = Tolerance(absolute=1.00)
r = t.permits(1.01, 1_000_000)
report("SEM-072", r is False, f"permits(1.01, 1_000_000)={r}")

# SEM-073
t = Tolerance(relative=0.001)
r1 = t.permits(900, 1_000_000)
r2 = t.permits(1100, 1_000_000)
r3 = t.permits(900, 100_000)
ok = r1 is True and r2 is False and r3 is False
report("SEM-073", ok, f"permits(900,1e6)={r1}, permits(1100,1e6)={r2}, permits(900,1e5)={r3}")

# SEM-074
t = Tolerance(absolute=1.00, relative=0.001)
r = t.permits(500.00, 1_000_000)
report("SEM-074", r is True, f"permits(500.00, 1_000_000)={r} [C2 regression case]")

# SEM-075
t = Tolerance(absolute=1.00, relative=0.001)
r = t.permits(0.75, 100)
report("SEM-075", r is True, f"permits(0.75, 100)={r}")

# SEM-076
t = Tolerance(absolute=1.00, relative=0.001)
r = t.permits(5000, 1_000_000)
report("SEM-076", r is False, f"permits(5000, 1_000_000)={r}")

# SEM-077
t = Tolerance(relative=0.001)
r1 = t.permits(0.0, 0.0)
r2 = t.permits(0.01, 0.0)
ok = r1 is True and r2 is False
report("SEM-077", ok, f"permits(0.0,0.0)={r1}, permits(0.01,0.0)={r2}")

# SEM-078
t = Tolerance(absolute=1.00, relative=0.001)
r = t.permits(0.50, 0.0)
report("SEM-078", r is True, f"permits(0.50, 0.0)={r}")

# SEM-079
t = Tolerance(absolute=1.00)
r1 = t.permits(-0.50, 100)
r2 = t.permits(-5.00, 100)
ok = r1 is True and r2 is False
report("SEM-079", ok, f"permits(-0.50,100)={r1}, permits(-5.00,100)={r2}")

# SEM-080
t = Tolerance(relative=0.10)
r = t.permits(5, -100)
report("SEM-080", r is True, f"permits(5, -100)={r}")

# SEM-081
e, err = expect_raises(lambda: Tolerance())
if e:
    ok = "1.00 EUR" in e.remedy or "0.1%" in e.remedy
    report("SEM-081", ok, f"message={e.message!r} remedy={e.remedy!r}")
else:
    report("SEM-081", False, err)

# SEM-082
e, err = expect_raises(lambda: Tolerance(absolute=-1.0))
if e:
    ok = e.context.get("absolute") == -1.0
    report("SEM-082", ok, f"message={e.message!r} context={e.context!r}")
else:
    report("SEM-082", False, err)

# SEM-083
try:
    t = Tolerance(absolute=0.0)
    r1 = t.permits(0, 100)
    r2 = t.permits(0.01, 100)
    ok = r1 is True and r2 is False
    report("SEM-083", ok, f"constructed; permits(0,100)={r1}, permits(0.01,100)={r2}")
except Exception as e:
    report("SEM-083", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-084
res = []
for val in (1.5, -0.001, 10):
    e, err = expect_raises(lambda v=val: Tolerance(relative=v))
    res.append((val, e is not None, e.message if e else err, e.remedy if e else None))
ok = all(r[1] for r in res)
report("SEM-084", ok, "; ".join(f"relative={r[0]}->{'ValidationError msg='+repr(r[2])+' remedy='+repr(r[3]) if r[1] else r[2]}" for r in res))

# SEM-085
try:
    t0 = Tolerance(relative=0.0)
    t1 = Tolerance(relative=1.0)
    report("SEM-085", True, f"relative=0.0 constructed ({t0.relative}); relative=1.0 constructed ({t1.relative})")
except Exception as e:
    report("SEM-085", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-086
t = Tolerance(absolute=1.0, relative=0.001, currency="EUR")
rendered = t.render()
ok = rendered == "within 1 EUR or 0.1%"
report("SEM-086", ok, f"render()={rendered!r}")

# SEM-087
try:
    t = Tolerance(absolute=0.0, rounding_scale=2)
    r = t.permits(0.004, 100)
    ok = r is False
    report("SEM-087", ok, f"permits(0.004, 100) with rounding_scale=2 -> {r} (expected False: rounding_scale not applied)")
except Exception as e:
    report("SEM-087", False, f"EXCEPTION {type(e).__name__}: {e}")

import subprocess
grep = subprocess.run(["grep", "-rn", "rounding_scale", "/home/ashutosh/PycharmProjects/prama/src"], capture_output=True, text=True)
print("### SEM-087-grep ::", grep.stdout.replace("\n", " | "))

# SEM-088
try:
    t = Tolerance(absolute=1.0, currency="EURO")
    rendered = t.render()
    ok = "EURO" in rendered
    report("SEM-088", ok, f"constructed with currency='EURO'; render()={rendered!r}")
except Exception as e:
    report("SEM-088", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-089
t = Tolerance(absolute=1.0, relative=0.001, currency="EUR", rounding_scale=2)
d = t.to_dict()
t2 = Tolerance.from_dict(d)
ok = t == t2 and t.permits(0.5, 1000) == t2.permits(0.5, 1000)
report("SEM-089", ok, f"to_dict={d!r} eq={t==t2} permits_match={t.permits(0.5,1000)==t2.permits(0.5,1000)}")

# SEM-090
off = TimeOffset()
ok = off.is_zero is True and off.render() == "same period"
report("SEM-090", ok, f"is_zero={off.is_zero} render={off.render()!r}")
# also verify RelationshipDeclaration.render omits it
from prama.semantic.relationships import RelationshipDeclaration, RelationshipKind, MatchKey
d = RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id="a", to_dataset_id="b",
                             match_keys=(MatchKey("x"),), compare=("amount",), tolerance=Tolerance(absolute=1.0),
                             offset=TimeOffset())
rendered_decl = d.render()
print(f"### SEM-090-decl :: 'same period' in decl render ({rendered_decl!r}) -> {'same period' in rendered_decl}")

# SEM-091
e, err = expect_raises(lambda: TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar=None))
if e:
    ok = "TARGET2" in e.remedy and "SIFMA" in e.remedy
    report("SEM-091", ok, f"message={e.message!r} remedy={e.remedy!r}")
else:
    report("SEM-091", False, err)

# SEM-092
try:
    off = TimeOffset(amount=0, unit=OffsetUnit.BUSINESS_DAYS)
    report("SEM-092", True, f"constructed with amount=0, no calendar: {off!r}")
except Exception as e:
    report("SEM-092", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-093
try:
    off = TimeOffset(amount=1, unit=OffsetUnit.CALENDAR_DAYS)
    report("SEM-093", True, f"constructed with amount=1, calendar_days, no calendar: {off!r}")
except Exception as e:
    report("SEM-093", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-094
res = []
for side in ("left", "TO", ""):
    e, err = expect_raises(lambda s=side: TimeOffset(lagging_side=s))
    res.append((side, e is not None, e.message if e else err))
ok = all(r[1] for r in res)
report("SEM-094", ok, "; ".join(f"{r[0]!r}->{'ValidationError' if r[1] else r[2]}" for r in res))

# SEM-095
try:
    off = TimeOffset(amount=-1, unit=OffsetUnit.CALENDAR_DAYS)
    rendered = off.render()
    ok = "the second lags by -1 calendar day" in rendered
    report("SEM-095", ok, f"constructed, render={rendered!r}")
except Exception as e:
    report("SEM-095", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-096
try:
    off1 = TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET-2")
    off2 = TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="NOT_A_CALENDAR")
    report("SEM-096", True, f"both accepted at declaration: {off1.calendar!r}, {off2.calendar!r}")
except Exception as e:
    report("SEM-096", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-097
r1 = TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2").render()
r2 = TimeOffset(amount=-1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2").render()
r3 = TimeOffset(amount=2, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2").render()
ok = "business day" in r1 and "business days" not in r1 and "business day" in r2 and "business days" not in r2 and "business days" in r3
report("SEM-097", ok, f"amount=1: {r1!r}; amount=-1: {r2!r}; amount=2: {r3!r}")
