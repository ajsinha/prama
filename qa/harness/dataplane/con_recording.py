import sys
sys.path.insert(0, ".")
from qa_common import log
from prama.profile.recording import points_from_profile
from prama.profile.statistics import ColumnAccumulator
from prama.profile.profiler import DatasetProfile, ProfileProvenance
from prama.connect.spi import SamplePlan, SamplingStrategy, Snapshot, SnapshotKind
from prama.core.clock import utc_now

def build_profile(rows=200, numeric=True, string=True, empty_numeric=False):
    cols = []
    if numeric:
        a = ColumnAccumulator("amt", "REAL")
        if empty_numeric:
            a.add_values([1.0]*rows)  # will still have stddev 0 unless single unique... use constant to get stddev None? stddev always computed.
        else:
            a.add_values([float(i) for i in range(rows)])
        cols.append(a)
    if string:
        b = ColumnAccumulator("name", "VARCHAR")
        b.add_values([f"v{i}" for i in range(rows)])
        cols.append(b)
    profiles = tuple(c.profile() for c in cols)
    snap = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="SNAP1", captured_at=utc_now())
    prov = ProfileProvenance(computed_at=utc_now(), snapshot=snap, plan=SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01), rows_examined=rows, duration_seconds=1.5)
    return DatasetProfile(path=("t",), columns=profiles, provenance=prov)

def pro095():
    dp = build_profile()
    pts = points_from_profile(dp, tenant_id="ten", dataset_id="ds")
    p = pts[0]
    ok = (p.snapshot_id == "SNAP1" and p.snapshot_exact is True and p.sampling == dp.provenance.plan.describe()
          and p.representative == dp.provenance.plan.strategy.is_representative and p.rows_examined == dp.provenance.rows_examined)
    log("PRO-095", "PASS" if ok else "FAIL", f"snapshot_id={p.snapshot_id} snapshot_exact={p.snapshot_exact} sampling={p.sampling!r} representative={p.representative} rows_examined={p.rows_examined}")

def pro096():
    dp = build_profile()
    pts = points_from_profile(dp, tenant_id="ten", dataset_id="ds")
    names = {(p.metric, p.attribute) for p in pts}
    metric_names = {p.metric for p in pts}
    ok = ("top_values" not in metric_names and "top_masks" not in metric_names
          and "row_count" in metric_names and "duration_seconds" in metric_names
          and "null_count" in metric_names and "min" in metric_names and "stddev" in metric_names
          and "min_length" in metric_names and "blank_count" in metric_names
          and sum(1 for m in metric_names if m.startswith("quantile_")) == 7)
    log("PRO-096", "PASS" if ok else "FAIL", f"metric_names={sorted(metric_names)}")

def pro097():
    # a numeric summary whose stddev is None only happens if numeric is None entirely per code
    # (NumericSummary always computes stddev via math.sqrt(variance), never None) -- construct directly
    from prama.profile.statistics import ColumnProfile, NumericSummary, StringSummary
    ns = NumericSummary(minimum=1.0, maximum=2.0, mean=1.5, stddev=None)
    ss = StringSummary(min_length=None, max_length=5, mean_length=3.0, blank_count=0)
    cp = ColumnProfile(name="c", type_name="X", rows=10, nulls=0, distinct_estimate=5, numeric=ns, strings=ss)
    snap = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="S", captured_at=utc_now())
    prov = ProfileProvenance(computed_at=utc_now(), snapshot=snap, plan=SamplePlan(), rows_examined=10, duration_seconds=0.1)
    dp = DatasetProfile(path=("t",), columns=(cp,), provenance=prov)
    pts = points_from_profile(dp, tenant_id="ten", dataset_id="ds")
    names = {p.metric for p in pts}
    ok = "stddev" not in names and "min_length" not in names and "min" in names and "max_length" in names
    log("PRO-097", "PASS" if ok else "FAIL", f"metric_names={sorted(names)}")

def pro098():
    a = ColumnAccumulator("c", "VARCHAR")
    a.add_values([None]*100)
    cp = a.profile()
    snap = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="S", captured_at=utc_now())
    prov = ProfileProvenance(computed_at=utc_now(), snapshot=snap, plan=SamplePlan(), rows_examined=100, duration_seconds=0.1)
    dp = DatasetProfile(path=("t",), columns=(cp,), provenance=prov)
    pts = points_from_profile(dp, tenant_id="ten", dataset_id="ds")
    by_metric = {p.metric: p.value for p in pts if p.attribute == "c"}
    ok = by_metric.get("null_count") == 100 and by_metric.get("null_rate") == 1.0 and by_metric.get("distinct_count") == 0.0 and by_metric.get("distinct_ratio") == 0.0
    log("PRO-098", "PASS" if ok else "FAIL", str(by_metric))

pro095(); pro096(); pro097(); pro098()
