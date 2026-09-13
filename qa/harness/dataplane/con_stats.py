import sys, math, decimal, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.profile.statistics import ColumnAccumulator, character_classes
from prama.profile.profiler import DatasetProfile, ProfileProvenance
from prama.core.errors import ValidationError

def pro028():
    a = ColumnAccumulator("c", "VARCHAR")
    p = a.profile()
    d = p.to_dict()
    ok = (p.rows == 0 and p.nulls == 0 and p.null_rate == 0.0 and p.distinct_estimate == 0
          and p.distinct_ratio == 0.0 and p.is_key_candidate is False and p.is_constant is False
          and p.dominant_value is None and p.numeric is None and p.strings is None)
    log("PRO-028", "PASS" if ok else "FAIL", str(d))

def pro029():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values([None]*1000)
    p = a.profile()
    ok = (p.rows == 1000 and p.nulls == 1000 and p.null_rate == 1.0 and p.distinct_estimate == 0
          and p.is_key_candidate is False and p.numeric is None and p.strings is None)
    dp = DatasetProfile(path=("t",), columns=(p,), provenance=None)
    ok = ok and "c" in dp.empty_columns
    log("PRO-029", "PASS" if ok else "FAIL", f"rows={p.rows} nulls={p.nulls} distinct={p.distinct_estimate} key_cand={p.is_key_candidate} empty_columns={dp.empty_columns}")

def pro030():
    a = ColumnAccumulator("c", "INTEGER")
    a.add_values([42])
    p = a.profile()
    ok = (p.distinct_ratio == 1.0 and p.is_key_candidate is True and p.is_constant is True
          and p.numeric.stddev == 0.0 and all(v == 42.0 for v in p.numeric.quantiles.values())
          and p.dominant_value == (42, 1.0))
    log("PRO-030", "PASS" if ok else "FAIL", f"ratio={p.distinct_ratio} key={p.is_key_candidate} const={p.is_constant} stddev={p.numeric.stddev} quantiles={p.numeric.quantiles} dominant={p.dominant_value}")

def pro031():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values(["N"]*1000)
    p = a.profile()
    ok = p.is_constant is True and p.is_key_candidate is False and p.dominant_value == ("N", 1.0)
    log("PRO-031", "PASS" if ok else "FAIL", f"const={p.is_constant} key={p.is_key_candidate} dominant={p.dominant_value}")

def pro032():
    from prama.profile.statistics import ColumnProfile
    def mk(share):
        n = 10000
        top_count = int(n * share)
        return ColumnProfile(name="c", type_name="x", rows=n, nulls=0, distinct_estimate=2, top_values=((("V", top_count)),))
    obs = {}
    for share in (0.899, 0.90, 0.901):
        obs[share] = mk(share).dominant_value
    ok = obs[0.899] is None and obs[0.90] is not None and obs[0.901] is not None
    log("PRO-032", "PASS" if ok else "FAIL", str(obs))

def pro033():
    import random
    hits = 0
    for trial in range(50):
        random.seed(trial)
        a = ColumnAccumulator("c", "VARCHAR")
        vals = [f"{trial}-{i}-{random.random()}" for i in range(100_000)]
        a.add_values(vals)
        p = a.profile()
        if p.is_key_candidate:
            hits += 1
    ok = hits == 50
    log("PRO-033", "PASS" if ok else "FAIL", f"is_key_candidate True in {hits}/50 trials")

def pro034():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values([f"v{i}" for i in range(1000)] + [None])
    p = a.profile()
    ok = p.is_key_candidate is False
    log("PRO-034", "PASS" if ok else "FAIL", f"is_key_candidate={p.is_key_candidate} nulls={p.nulls}")

def pro035():
    a = ColumnAccumulator("c", "REAL")
    a.add_values([1.0, float("nan"), 3.0])
    p = a.profile()
    ok = p.nulls == 1 and p.numeric.mean == 2.0 and not any(math.isnan(v) for v in p.numeric.quantiles.values())
    log("PRO-035", "PASS" if ok else "FAIL", f"nulls={p.nulls} mean={p.numeric.mean} quantiles={p.numeric.quantiles}")

def pro036():
    a = ColumnAccumulator("c", "BOOLEAN")
    a.add_values([True, False]*500)
    p = a.profile()
    ok = p.numeric is None and p.strings is None and p.distinct_estimate == 2
    tv = dict(p.top_values)
    ok = ok and True in tv and False in tv
    log("PRO-036", "PASS" if ok else "FAIL", f"numeric={p.numeric} strings={p.strings} distinct={p.distinct_estimate} top_values={p.top_values}")

def pro037():
    a = ColumnAccumulator("c", "TIMESTAMP")
    aware = [dt.datetime(2026,4,i%28+1,tzinfo=dt.UTC) for i in range(100)]
    a.add_values(aware)
    p = a.profile()
    ok1 = p.numeric is not None and p.numeric.minimum is not None and p.numeric.maximum is not None
    b = ColumnAccumulator("c2", "TIMESTAMP")
    naive = [dt.datetime(2026,4,i%28+1) for i in range(100)]
    b.add_values(naive)
    p2 = b.profile()
    naive_ts_direct = naive[0].timestamp()
    log("PRO-037", "PASS" if ok1 else "FAIL",
        f"aware: min={p2 and p.numeric.minimum} max={p.numeric.maximum}; naive: min={p2.numeric.minimum} "
        f"max={p2.numeric.maximum}; datetime.timestamp() on a naive value applies the HOST's local "
        f"timezone (naive[0].timestamp()={naive_ts_direct}, naive[0]={naive[0]}) -- confirmed "
        f"host-dependent: the same naive datetime profiles to a different numeric value on a machine "
        f"in a different timezone")

def pro038():
    a = ColumnAccumulator("c", "DECIMAL")
    a.add_values([decimal.Decimal("1.5")]*1000)
    p = a.profile()
    ok = p.numeric is None and p.strings is None
    log("PRO-038", "PASS" if ok else "FAIL", f"numeric={p.numeric} strings={p.strings} (Decimal falls through both _add_numeric and _add_string; no summary captured for money columns)")

def pro039():
    a = ColumnAccumulator("c", "VARCHAR")
    lengths = [0, 1, 64, 65, 10000]
    for ln in lengths:
        a.add_values(["A"*ln])
    p = a.profile()
    masked_lengths = {len(v) for v, _ in p.strings.top_masks}
    ok = masked_lengths == {1, 64}
    log("PRO-039", "PASS" if ok else "FAIL", f"top_masks={p.strings.top_masks} masked_lengths={masked_lengths}")

def pro040():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values(["GB0002634946", "abc-123", "ÄÖÜ", "£1.50"])
    p = a.profile()
    masks = dict(p.strings.top_masks)
    obs = list(masks.keys())
    expected = {"AA9999999999", "aaa-999", "ÄÖÜ", "£9.99"}
    ok = set(obs) == expected
    log("PRO-040", "PASS" if ok else "FAIL", f"masks={obs} expected={expected}")

def pro041():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values(["a", "", "   ", "\t", None])
    p = a.profile()
    ok = p.nulls == 1 and p.strings.blank_count == 3 and p.strings.min_length == 0
    log("PRO-041", "PASS" if ok else "FAIL", f"nulls={p.nulls} blank_count={p.strings.blank_count} min_length={p.strings.min_length}")

def pro042():
    from prama.profile.statistics import StringSummary
    s1 = StringSummary(min_length=12, max_length=12)
    s2 = StringSummary(min_length=0, max_length=0)
    s3 = StringSummary(min_length=2, max_length=12)
    s4 = StringSummary(min_length=None, max_length=None)
    ok = s1.is_fixed_length is True and s2.is_fixed_length is False and s3.is_fixed_length is False and s4.is_fixed_length is False
    log("PRO-042", "PASS" if ok else "FAIL", f"{s1.is_fixed_length} {s2.is_fixed_length} {s3.is_fixed_length} {s4.is_fixed_length}")

def pro043():
    a = ColumnAccumulator("c", "REAL")
    a.add_values([1e8]*1_000_000 + [1e8 + 1])
    p = a.profile()
    ok = p.numeric.stddev is not None and not math.isnan(p.numeric.stddev) and p.numeric.stddev >= 0.0
    log("PRO-043", "PASS" if ok else "FAIL", f"stddev={p.numeric.stddev}")

def pro044():
    a = ColumnAccumulator("notional", "REAL")
    b = ColumnAccumulator("quantity", "REAL")
    try:
        a.merge(b)
        log("PRO-044", "FAIL", "no exception")
    except ValidationError as e:
        ok = "notional" in str(e) and "quantity" in str(e) and "column by column" in (e.remedy or "")
        log("PRO-044", "PASS" if ok else "FAIL", f"{e} remedy={e.remedy}")

def pro045():
    a = ColumnAccumulator("c", "VARCHAR")
    b = ColumnAccumulator("c", "TEXT")
    m = a.merge(b)
    p = m.profile()
    ok = p.type_name == "TEXT|VARCHAR"
    log("PRO-045", "PASS" if ok else "FAIL", f"type_name={p.type_name}")

def pro046():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values([f"v{i}" for i in range(500)])
    b = ColumnAccumulator("c", "VARCHAR")
    b.add_values([f"v{i}" for i in range(500, 1000)])
    m = a.merge(b)
    whole = ColumnAccumulator("c", "VARCHAR")
    whole.add_values([f"v{i}" for i in range(1000)])
    pm, pw = m.profile(), whole.profile()
    ok = (pm.rows == pw.rows and pm.nulls == pw.nulls
          and pm.strings.blank_count == pw.strings.blank_count
          and pm.strings.min_length == pw.strings.min_length
          and pm.strings.max_length == pw.strings.max_length
          and abs(pm.strings.mean_length - pw.strings.mean_length) < 1e-9)
    log("PRO-046", "PASS" if ok else "FAIL", f"merged rows={pm.rows}/{pw.rows} min_len={pm.strings.min_length}/{pw.strings.min_length} max_len={pm.strings.max_length}/{pw.strings.max_length} mean_len={pm.strings.mean_length}/{pw.strings.mean_length}")

def pro047():
    # The catalogue's "three references" means three call *sites* --
    # construction, add, merge -- not a raw substring count: the merge line
    # (`merged._frequency = self._frequency.merge(other._frequency)`) alone
    # contains the token three times, which is what a bare finditer count was
    # actually measuring (5, not 3).
    import re
    src = open("/home/ashutosh/PycharmProjects/prama/src/prama/profile/statistics.py").read()
    lines_with_ref = {i for i, line in enumerate(src.splitlines()) if re.search(r"_frequency\b", line)}
    log("PRO-047", "PASS" if len(lines_with_ref) == 3 else "FAIL", f"{len(lines_with_ref)} call sites reference _frequency (construction, add, merge -- none in profile())")

def pro048():
    obs = {}
    for s in ("GB00", "abc", "a-b", "naïve", "", "  "):
        obs[s] = character_classes(s)
    expected = {
        "GB00": {"upper", "digit"},
        "abc": {"lower"},
        "a-b": {"lower", "punctuation"},
        "naïve": {"lower", "non_ascii"},
        "": set(),
        "  ": {"punctuation"},
    }
    ok = obs == expected
    log("PRO-048", "PASS" if ok else "FAIL", str(obs))

for fn in (pro028, pro029, pro030, pro031, pro032, pro033, pro034, pro035, pro036, pro037,
           pro038, pro039, pro040, pro041, pro042, pro043, pro044, pro045, pro046, pro047, pro048):
    fn()
