import sys, traceback
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.semantic.values import (
    Grain, Rhythm, Frequency, ValueDomain, ValueDomainKind,
    Criticality, Sensitivity, Authoritativeness, LifecycleState, Optionality,
)
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

# SEM-001
try:
    g = Grain(attributes=("account_id",), statement="one row per account")
    ok = g.arity == 1 and g.render() == "one row per account"
    report("SEM-001", ok, f"arity={g.arity}, render={g.render()!r}")
except Exception as e:
    report("SEM-001", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-002
e, err = expect_raises(lambda: Grain(attributes=()))
if e is not None:
    ok = "what does one row represent?" in e.remedy
    report("SEM-002", ok, f"ValidationError remedy={e.remedy!r}")
else:
    report("SEM-002", False, err)

# SEM-003
e, err = expect_raises(lambda: Grain(attributes=("account_id","account_id")))
if e is not None:
    ok = "repeats an attribute" in str(e.message) and e.context.get("attributes") == ["account_id","account_id"]
    report("SEM-003", ok, f"message={e.message!r} context={e.context!r}")
else:
    report("SEM-003", False, err)

# SEM-004
bad_names = ["Account ID", "ACCOUNT_ID", "1st_leg", "_hidden", "", "account-id"]
results = []
for name in bad_names:
    e, err = expect_raises(lambda n=name: Grain(attributes=(n,)))
    if e is not None:
        results.append((name, True, e.message, e.remedy))
    else:
        results.append((name, False, err, None))
ok_all = all(r[1] for r in results)
report("SEM-004", ok_all, "; ".join(f"{r[0]!r}->{'ValidationError' if r[1] else r[2]}" for r in results))

# SEM-005
name63 = "a" * 63
name64 = "a" * 64
assert len(name63) == 63 and len(name64) == 64
ok63 = True
msg = ""
try:
    Grain(attributes=(name63,))
except Exception as e:
    ok63 = False
    msg += f"63-char refused: {e}; "
e, err = expect_raises(lambda: Grain(attributes=(name64,)))
ok64 = e is not None
if not ok64:
    msg += f"64-char: {err}"
report("SEM-005", ok63 and ok64, f"63-accepted={ok63}, 64-refused={ok64} {msg}")

# SEM-006
g = Grain(("account_id", "business_date"))
rendered = g.render()
ok = rendered == "one record per account id per business date"
report("SEM-006", ok, f"render={rendered!r}")

# SEM-007
stmt = "Reconcile to €0.01, per client's spec — naïve check!"
g = Grain(("account_id",), statement=stmt)
ok = g.render() == stmt
report("SEM-007", ok, f"render={g.render()!r} == statement={stmt!r}")

# SEM-008
g = Grain(("account_id", "business_date"), statement="stmt")
d = g.to_dict()
g2 = Grain.from_dict(d)
ok = (g == g2) and isinstance(g2.attributes, tuple) and g2.attributes == ("account_id", "business_date")
report("SEM-008", ok, f"to_dict={d!r} from_dict.attributes={g2.attributes!r} type={type(g2.attributes)} eq={g==g2}")

# SEM-009
e1, err1 = expect_raises(lambda: Grain.from_dict({}))
e2, err2 = expect_raises(lambda: Grain.from_dict({"statement": "x"}))
ok = e1 is not None and e2 is not None
report("SEM-009", ok, f"from_dict({{}})={'ValidationError' if e1 else err1}; from_dict(statement only)={'ValidationError' if e2 else err2}")

# SEM-010
g1 = Grain(("account_id",), statement="a")
g2 = Grain(("account_id",), statement="b")
eq = (g1 == g2)
try:
    h1 = hash(g1); h2 = hash(g2)
    hashable = True
except Exception as e:
    hashable = False
    h1 = h2 = None
report("SEM-010", True, f"g1==g2 -> {eq} (statement participates in equality: {not eq}); hashable={hashable} hash_equal={h1==h2 if hashable else 'n/a'}")

# SEM-011
r = Rhythm()
ok = (r.frequency == Frequency.DAILY and r.arrival_by is None and r.has_arrival_expectation is False and r.lateness_tolerance_seconds == 0.0)
report("SEM-011", ok, f"frequency={r.frequency}, arrival_by={r.arrival_by}, has_arrival_expectation={r.has_arrival_expectation}, lateness={r.lateness_tolerance_seconds}")

# SEM-012
times = ["06:30", "00:00", "23:59"]
res = []
for t in times:
    try:
        Rhythm(arrival_by=t)
        res.append((t, True))
    except Exception as e:
        res.append((t, False, str(e)))
ok = all(r[1] for r in res)
report("SEM-012", ok, "; ".join(f"{r[0]}:{'accepted' if r[1] else 'refused:'+str(r[2])}" for r in res))

# SEM-013
bad_times = ["6:30", "24:00", "23:60", "06:30:00", "6.30am", "0630", " 06:30"]
res = []
for t in bad_times:
    e, err = expect_raises(lambda tt=t: Rhythm(arrival_by=tt))
    res.append((t, e is not None, e.remedy if e else err))
ok = all(r[1] for r in res)
report("SEM-013", ok, "; ".join(f"{r[0]!r}->{'ValidationError remedy='+repr(r[2]) if r[1] else r[2]}" for r in res))

# SEM-014
e, err = expect_raises(lambda: Rhythm(expected_volume_min=100, expected_volume_max=10))
if e:
    ok = "swap the two bounds" in e.remedy.lower() and e.context == {"min":100, "max":10}
    report("SEM-014", ok, f"message={e.message!r} remedy={e.remedy!r} context={e.context!r}")
else:
    report("SEM-014", False, err)

# SEM-015
try:
    r = Rhythm(expected_volume_min=5000, expected_volume_max=5000)
    report("SEM-015", True, f"constructed: min={r.expected_volume_min}, max={r.expected_volume_max}")
except Exception as e:
    report("SEM-015", False, f"EXCEPTION: {e}")

# SEM-016
try:
    r = Rhythm(arrival_by="06:30", lateness_tolerance_seconds=-3600)
    computed = int(-3600 // 60)
    ok = computed == -60
    report("SEM-016", ok, f"constructed, lateness_tolerance_seconds={r.lateness_tolerance_seconds}, int(-3600//60)={computed}")
except Exception as e:
    report("SEM-016", False, f"EXCEPTION: {e}")

# SEM-017
try:
    r = Rhythm(expected_volume_min=-1)
    report("SEM-017", True, f"constructed: expected_volume_min={r.expected_volume_min}")
except Exception as e:
    report("SEM-017", False, f"EXCEPTION: {e}")

# SEM-018
cases_18 = [
    (Rhythm(), "frequency only"),
    (Rhythm(arrival_by="06:30"), "frequency+arrival"),
    (Rhythm(arrival_by="06:30", calendar="TARGET2"), "+calendar"),
    (Rhythm(arrival_by="06:30", calendar="TARGET2", expected_volume_min=1000, expected_volume_max=5000), "+both bounds"),
    (Rhythm(arrival_by="06:30", calendar="TARGET2", expected_volume_min=1000), "+only min"),
]
outs = [(label, r.render()) for r, label in cases_18]
expected_full = "daily, by 06:30, on TARGET2 business days, (1000 to 5000 records)"
expected_min_only_has_q = "?" in outs[4][1]
ok = outs[3][1] == expected_full and expected_min_only_has_q
report("SEM-018", ok, "; ".join(f"{label}={out!r}" for label, out in outs))

# SEM-019
r = Rhythm(volume_drivers=("month_end", "trading_days"))
d = r.to_dict()
r2 = Rhythm.from_dict(d)
ok = r == r2 and isinstance(r2.volume_drivers, tuple) and r2.volume_drivers == ("month_end", "trading_days")
report("SEM-019", ok, f"round-tripped volume_drivers={r2.volume_drivers!r} type={type(r2.volume_drivers)} eq={r==r2}")

# SEM-020
try:
    Rhythm.from_dict({"frequency": "fortnightly"})
    report("SEM-020", False, "NO EXCEPTION RAISED")
except ValidationError as e:
    report("SEM-020", False, f"Got ValidationError instead of bare ValueError (contradicts catalogue's 'currently'): {e}")
except ValueError as e:
    report("SEM-020", True, f"bare ValueError raised (no remedy): {e}")
except Exception as e:
    report("SEM-020", False, f"WRONG EXCEPTION: {type(e).__name__}: {e}")

# SEM-021
e, err = expect_raises(lambda: ValueDomain(kind=ValueDomainKind.CODELIST))
if e:
    ok = "codelist" in e.message.lower() or "code" in e.message.lower()
    report("SEM-021", ok, f"message={e.message!r} remedy={e.remedy!r}")
else:
    report("SEM-021", False, err)

# SEM-022
vd = ValueDomain(kind=ValueDomainKind.CODELIST, allowed_values=("BUY", "SELL"))
ok = vd.is_constrained is True
report("SEM-022", ok, f"constructed, is_constrained={vd.is_constrained}")

# SEM-023
e, err = expect_raises(lambda: ValueDomain(kind=ValueDomainKind.PATTERN))
if e:
    ok = "different domain" in e.remedy.lower() or "pattern" in e.remedy.lower()
    report("SEM-023", ok, f"message={e.message!r} remedy={e.remedy!r}")
else:
    report("SEM-023", False, err)

# SEM-024
try:
    ValueDomain(kind=ValueDomainKind.PATTERN, pattern="[unclosed")
    report("SEM-024", False, "NO EXCEPTION RAISED")
except ValidationError as e:
    ok = e.__cause__ is not None and isinstance(e.__cause__, Exception) and "compiled at declaration time" in e.remedy
    report("SEM-024", ok, f"message={e.message!r} remedy={e.remedy!r} cause={e.__cause__!r}")
except Exception as e:
    report("SEM-024", False, f"WRONG EXCEPTION: {type(e).__name__}: {e}")

# SEM-025
e, err = expect_raises(lambda: ValueDomain(kind=ValueDomainKind.RANGE))
if e:
    ok = "supply a minimum" in e.remedy.lower()
    report("SEM-025", ok, f"message={e.message!r} remedy={e.remedy!r}")
else:
    report("SEM-025", False, err)

# SEM-026
try:
    vd_min = ValueDomain(kind=ValueDomainKind.RANGE, minimum=0)
    vd_max = ValueDomain(kind=ValueDomainKind.RANGE, maximum=100)
    report("SEM-026", True, f"min-only constructed(min={vd_min.minimum}), max-only constructed(max={vd_max.maximum})")
except Exception as e:
    report("SEM-026", False, f"EXCEPTION: {e}")

# SEM-027
try:
    vd = ValueDomain(kind=ValueDomainKind.RANGE, minimum=100, maximum=1)
    report("SEM-027", True, f"constructed unchecked: minimum={vd.minimum}, maximum={vd.maximum}")
except Exception as e:
    report("SEM-027", False, f"EXCEPTION: {e}")

# SEM-028
import subprocess
grep = subprocess.run(
    ["grep", "-rn", "case_sensitive", "/home/ashutosh/PycharmProjects/prama/src"],
    capture_output=True, text=True,
)
report("SEM-028", True, f"grep hits:\n{grep.stdout}")

# SEM-029
vd = ValueDomain(kind=ValueDomainKind.CODELIST, allowed_values=("BUY", "SELL"))
d = vd.to_dict()
vd2 = ValueDomain.from_dict(d)
ok = vd2.kind == ValueDomainKind.CODELIST and isinstance(vd2.allowed_values, tuple) and vd2.allowed_values == ("BUY", "SELL")
report("SEM-029", ok, f"kind={vd2.kind!r} allowed_values={vd2.allowed_values!r} type={type(vd2.allowed_values)}")

# SEM-030
ok = (Criticality.TIER_1 < Criticality.TIER_4) and (int(Criticality.TIER_1) == 1)
report("SEM-030", ok, f"TIER_1<TIER_4={Criticality.TIER_1 < Criticality.TIER_4}, int(TIER_1)={int(Criticality.TIER_1)}")

# SEM-031
labels = {}
try:
    for c in Criticality:
        labels[c] = c.label
    ok = len(labels) == 4
    report("SEM-031", ok, f"labels={labels}")
except Exception as e:
    report("SEM-031", False, f"EXCEPTION: {e}")

# SEM-032
e1, err1 = expect_raises(lambda: Criticality(0), (ValueError,))
e2, err2 = expect_raises(lambda: Criticality(5), (ValueError,))
ok = e1 is not None and e2 is not None
report("SEM-032", ok, f"Criticality(0)={'ValueError' if e1 else err1}; Criticality(5)={'ValueError' if e2 else err2}")

# SEM-033
sens_results = {s: s.masked_by_default for s in Sensitivity}
expected_masked = {Sensitivity.PII, Sensitivity.MNPI, Sensitivity.RESTRICTED}
actual_masked = {s for s, v in sens_results.items() if v}
ok = actual_masked == expected_masked
report("SEM-033", ok, f"masked_by_default={ {s.value: v for s, v in sens_results.items()} }")

# SEM-034
ext_results = {s: s.may_reach_external_model for s in Sensitivity}
expected_ext = {Sensitivity.PUBLIC, Sensitivity.INTERNAL}
actual_ext = {s for s, v in ext_results.items() if v}
ok = actual_ext == expected_ext
report("SEM-034", ok, f"may_reach_external_model={ {s.value: v for s, v in ext_results.items()} }")

# SEM-035
copy_results = {a: a.is_copy for a in Authoritativeness}
expected_copy = {Authoritativeness.REPLICA, Authoritativeness.EXTRACT}
actual_copy = {a for a, v in copy_results.items() if v}
ok = actual_copy == expected_copy
report("SEM-035", ok, f"is_copy={ {a.value: v for a, v in copy_results.items()} }")

# SEM-036
live_results = {ls: ls.is_live for ls in LifecycleState}
expected_live = {LifecycleState.ACTIVE, LifecycleState.DEPRECATED}
actual_live = {ls for ls, v in live_results.items() if v}
ok = actual_live == expected_live
report("SEM-036", ok, f"is_live={ {ls.value: v for ls, v in live_results.items()} }")
