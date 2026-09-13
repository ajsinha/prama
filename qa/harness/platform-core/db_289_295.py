import sys, os, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from datetime import datetime, UTC, timedelta
from prama.db.metrics.model import MetricPoint, CORE_METRICS
from prama.db.metrics.store import MemoryMetricStore, ParquetMetricStore

def mk_point(tenant_id="t1", dataset_id="d1", metric="row_count", value=1.0, computed_at=None, **kw):
    return MetricPoint(
        tenant_id=tenant_id, dataset_id=dataset_id, metric=metric, value=value,
        computed_at=computed_at or datetime(2026,1,1,tzinfo=UTC),
        attribute=kw.get("attribute"), segment=kw.get("segment"),
        snapshot_id=kw.get("snapshot_id"), snapshot_exact=kw.get("snapshot_exact", True),
        sampling=kw.get("sampling", "full"), representative=kw.get("representative", True),
        rows_examined=kw.get("rows_examined", 0),
    )

tmp = tempfile.mkdtemp(prefix="dbqa-metrics-")
mem = MemoryMetricStore()
parq = ParquetMetricStore(os.path.join(tmp, "parquet"), flush_threshold=1)  # flush immediately for determinism

# DB-289: record never updates -- two points, same key and time
p1 = mk_point(value=10.0)
p2 = mk_point(value=20.0)  # same tenant/dataset/metric/attribute/segment/computed_at
mem.record([p1, p2])
parq.record([p1, p2])
series_mem = mem.series("t1", "d1", "row_count")
series_parq = parq.series("t1", "d1", "row_count")
R("DB-289", len(series_mem) == 2 and len(series_parq) == 2, f"mem series len={len(series_mem)}, parquet series len={len(series_parq)}")

# DB-290: series reads back oldest first, even if recorded out of order
mem2 = MemoryMetricStore()
parq2 = ParquetMetricStore(os.path.join(tmp, "parquet2"), flush_threshold=1)
t_mid = datetime(2026,1,15,tzinfo=UTC)
t_early = datetime(2026,1,1,tzinfo=UTC)
t_late = datetime(2026,1,30,tzinfo=UTC)
pts290 = [mk_point(metric="m290", computed_at=t_mid), mk_point(metric="m290", computed_at=t_early), mk_point(metric="m290", computed_at=t_late)]
mem2.record(pts290)
parq2.record(pts290)
sm = mem2.series("t1","d1","m290")
sp = parq2.series("t1","d1","m290")
R("DB-290", [p.computed_at for p in sm.points] == [t_early, t_mid, t_late] and [p.computed_at for p in sp.points] == [t_early, t_mid, t_late],
  f"mem order={[p.computed_at for p in sm.points]}; parquet order={[p.computed_at for p in sp.points]}")

# DB-291: memory and parquet agree on series/latest/count
mem3 = MemoryMetricStore()
parq3 = ParquetMetricStore(os.path.join(tmp, "parquet3"), flush_threshold=1)
pts291 = [
    mk_point(metric="row_count", value=100.0, computed_at=datetime(2026,1,1,tzinfo=UTC)),
    mk_point(metric="row_count", value=110.0, computed_at=datetime(2026,1,2,tzinfo=UTC)),
    mk_point(metric="null_rate", value=0.02, computed_at=datetime(2026,1,1,tzinfo=UTC)),
]
mem3.record(pts291)
parq3.record(pts291)
sm3 = mem3.series("t1","d1","row_count").values
sp3 = parq3.series("t1","d1","row_count").values
lm3 = sorted((p.metric, p.value) for p in mem3.latest("t1","d1"))
lp3 = sorted((p.metric, p.value) for p in parq3.latest("t1","d1"))
cm3 = mem3.count("t1")
cp3 = parq3.count("t1")
R("DB-291", sm3 == sp3 and lm3 == lp3 and cm3 == cp3, f"series values mem={sm3} parquet={sp3}; latest mem={lm3} parquet={lp3}; count mem={cm3} parquet={cp3}")

# DB-292: sampling provenance round-trips
mem4 = MemoryMetricStore()
parq4 = ParquetMetricStore(os.path.join(tmp, "parquet4"), flush_threshold=1)
p292 = mk_point(metric="m292", sampling="1pct", representative=False, rows_examined=1000, snapshot_exact=False)
mem4.record([p292])
parq4.record([p292])
back_mem = mem4.series("t1","d1","m292").points[0]
back_parq = parq4.series("t1","d1","m292").points[0]
R("DB-292", (back_mem.sampling, back_mem.representative, back_mem.rows_examined, back_mem.snapshot_exact) == ("1pct", False, 1000, False)
  and (back_parq.sampling, back_parq.representative, back_parq.rows_examined, back_parq.snapshot_exact) == ("1pct", False, 1000, False),
  f"mem back={(back_mem.sampling, back_mem.representative, back_mem.rows_examined, back_mem.snapshot_exact)}; "
  f"parquet back={(back_parq.sampling, back_parq.representative, back_parq.rows_examined, back_parq.snapshot_exact)}")

# DB-293: purge_before drops whole day partitions only
parq5 = ParquetMetricStore(os.path.join(tmp, "parquet5"), flush_threshold=1)
day1 = datetime(2026,1,1,10,0,0,tzinfo=UTC)
day2 = datetime(2026,1,2,10,0,0,tzinfo=UTC)
day3 = datetime(2026,1,3,10,0,0,tzinfo=UTC)
parq5.record([mk_point(metric="m293", computed_at=day1), mk_point(metric="m293", computed_at=day2), mk_point(metric="m293", computed_at=day3)])
cutoff293 = datetime(2026,1,2,12,0,0,tzinfo=UTC)  # mid-day on day 2
removed293 = parq5.purge_before("t1", cutoff293)
remaining293 = parq5.series("t1","d1","m293")
remaining_days = sorted({p.computed_at.date() for p in remaining293.points})
R("DB-293", day1.date() not in remaining_days and day3.date() in remaining_days,
  f"removed count(partitions)={removed293}; remaining days={remaining_days} -- day1 (before cutoff) gone={day1.date() not in remaining_days}, "
  f"day2 (the cutoff's OWN day, only mid-day passed) {'gone' if day2.date() not in remaining_days else 'survives'}, day3 (after cutoff) survives={day3.date() in remaining_days}")

# DB-294: a metric name outside CORE_METRICS is still recordable
mem6 = MemoryMetricStore()
custom_metric = "tenant_defined_weird_metric_xyz"
R294_not_core = custom_metric not in CORE_METRICS
mem6.record([mk_point(metric=custom_metric, value=42.0)])
back294 = mem6.series("t1","d1",custom_metric)
R("DB-294", R294_not_core and len(back294) == 1 and back294.points[0].value == 42.0,
  f"'{custom_metric}' not in CORE_METRICS={R294_not_core}; recorded and read back={len(back294)==1}")

# DB-295: MetricPoint.key distinguishes segments
p_none_seg = mk_point(metric="m295", segment=None, value=1.0)
p_gb_seg = mk_point(metric="m295", segment="GB", value=2.0)
mem7 = MemoryMetricStore()
mem7.record([p_none_seg, p_gb_seg])
series_none = mem7.series("t1","d1","m295", segment=None)
series_gb = mem7.series("t1","d1","m295", segment="GB")
R("DB-295", p_none_seg.key != p_gb_seg.key and len(series_none) == 1 and len(series_gb) == 1
  and series_none.points[0].value == 1.0 and series_gb.points[0].value == 2.0,
  f"keys differ={p_none_seg.key != p_gb_seg.key}; series(segment=None)={[p.value for p in series_none.points]}; series(segment=GB)={[p.value for p in series_gb.points]}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
