import sys, asyncio, sqlite3, tempfile, os, io, logging, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.profile.profiler import (
    Profiler, ProfileProvenance, suggest_sample_plan, detectable_rate, from_rows, DatasetProfile,
)
from prama.connect.sources.sqlite import SqliteConnector
from prama.connect.spi import (
    Connector, HealthReport, HealthState, DiscoveredObject, ObjectSchema, ColumnSchema,
    SamplePlan, SamplingStrategy, Snapshot, SnapshotKind,
)
from prama.core.clock import utc_now

tmpdir = tempfile.mkdtemp()
dbpath = os.path.join(tmpdir, "t.db")
conn = sqlite3.connect(dbpath)
conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
conn.executemany("INSERT INTO t VALUES (?,?)", [(i, f"v{i}") for i in range(1000)])
conn.commit()
conn.close()

class FakeConnector(Connector):
    """Minimal in-memory connector for controlling profiler test scenarios."""
    def __init__(self, config=None, *, objects=None, describe_map=None, fail_on=None, **kw):
        super().__init__(config or {}, **kw)
        self.snapshot_calls = 0
        self._objects = objects or {}
        self._describe_map = describe_map or {}
        self._fail_on = fail_on
    @classmethod
    def manifest(cls):
        return cls.describe_manifest(key="fake", display_name="Fake")
    async def health(self): return HealthReport(state=HealthState.HEALTHY)
    async def discover(self, path=()):
        return self._objects.get("discover", [])
    async def describe(self, path):
        return self._describe_map.get(path, ObjectSchema(path=path, columns=()))
    async def snapshot(self, path):
        self.snapshot_calls += 1
        return Snapshot(kind=SnapshotKind.WALL_CLOCK, identifier="x", captured_at=utc_now())
    async def read(self, path, *, plan=None):
        if self._fail_on and path == self._fail_on:
            raise RuntimeError(f"cannot read {path}")
        for batch in self._objects.get(("read", path), []):
            yield batch

async def pro049():
    c = SqliteConnector({"database_path": dbpath})
    async with c:
        p = Profiler()
        plan = SamplePlan(strategy=SamplingStrategy.HEAD, rows=100)
        dp = await p.profile(c, ("t",), plan=plan)
    d = dp.provenance.to_dict()
    required = {"computed_at", "snapshot", "sampling", "representative", "rows_examined", "complete", "duration_seconds", "confidence"}
    ok = required <= set(d.keys()) and d["snapshot"] is not None and "exact" in d["snapshot"]
    log("PRO-049", "PASS" if ok else "FAIL", str(d))

def pro050():
    now = utc_now()
    p_full = ProfileProvenance(computed_at=now, snapshot=None, plan=SamplePlan(), rows_examined=1000, duration_seconds=1.0, truncated=False)
    p_full_trunc = ProfileProvenance(computed_at=now, snapshot=None, plan=SamplePlan(), rows_examined=1000, duration_seconds=1.0, truncated=True)
    p_head = ProfileProvenance(computed_at=now, snapshot=None, plan=SamplePlan(strategy=SamplingStrategy.HEAD, rows=1000), rows_examined=1000, duration_seconds=1.0)
    p_sys = ProfileProvenance(computed_at=now, snapshot=None, plan=SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.01), rows_examined=1000, duration_seconds=1.0)
    notes = {"full": p_full.confidence_note, "full_trunc": p_full_trunc.confidence_note, "head": p_head.confidence_note, "sys": p_sys.confidence_note}
    ok = (notes["full"] == "measured over all 1,000 rows"
          and notes["full_trunc"].startswith("estimated from")
          and notes["head"] == "read the first 1,000 rows only — indicative of shape, not of any rate"
          and notes["sys"] == "estimated from 1,000 sampled rows (systematic sample at 1%)")
    log("PRO-050", "PASS" if ok else "FAIL", str(notes))

async def pro051():
    c = SqliteConnector({"database_path": dbpath})
    async with c:
        p = Profiler(max_rows=1000)
        stream = io.StringIO()
        h = logging.StreamHandler(stream)
        lg = logging.getLogger("prama.profile.profiler")
        lg.addHandler(h); lg.setLevel(logging.INFO)
        dp = await p.profile(c, ("t",))
    ok = (dp.provenance.truncated is True and dp.provenance.is_complete is False
          and "1000" in stream.getvalue() and dp.provenance.rows_examined > 0)
    log("PRO-051", "PASS" if ok else "FAIL", f"truncated={dp.provenance.truncated} is_complete={dp.provenance.is_complete} rows_examined={dp.provenance.rows_examined} log={stream.getvalue().strip()!r}")

async def pro052():
    # SqliteConnector's own batches are BATCH_ROWS=10000; use a table of >10000 rows
    p3 = os.path.join(tmpdir, "big.db")
    bc = sqlite3.connect(p3)
    bc.execute("CREATE TABLE t (a INTEGER)")
    bc.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(25000)])
    bc.commit(); bc.close()
    c = SqliteConnector({"database_path": p3})
    async with c:
        p = Profiler(max_rows=1000)
        dp = await p.profile(c, ("t",))
    ok = dp.provenance.rows_examined == 10000
    log("PRO-052", "PASS" if ok else "FAIL", f"rows_examined={dp.provenance.rows_examined} (expected 10000, the first full batch, since the check runs after the batch is consumed)")

async def pro053():
    import pyarrow as pa
    schema = ObjectSchema(path=("t",), columns=(ColumnSchema(name="a", type_name="INT"), ColumnSchema(name="b", type_name="TEXT")))
    batch = pa.RecordBatch.from_arrays([pa.array(["v1"]), pa.array([1]), pa.array(["extra1"])], names=["b", "a", "c"])
    fc = FakeConnector(objects={"discover": [], ("read", ("t",)): [batch]}, describe_map={("t",): schema})
    async with fc:
        p = Profiler()
        dp = await p.profile(fc, ("t",))
    names = [c.name for c in dp.columns]
    ok = names == ["a", "b", "c"]
    log("PRO-053", "PASS" if ok else "FAIL", f"column_order={names} (schema order a,b then extra c appended)")

async def pro054():
    import pyarrow as pa
    schema = ObjectSchema(path=("t",), columns=(ColumnSchema(name="amt", type_name="NUMERIC(38,12)"),))
    batch = pa.RecordBatch.from_arrays([pa.array(["1953193.464900000000"])], names=["amt"])
    fc = FakeConnector(objects={"discover": [], ("read", ("t",)): [batch]}, describe_map={("t",): schema})
    async with fc:
        p = Profiler()
        dp = await p.profile(fc, ("t",))
    ok = dp.column("amt").type_name == "NUMERIC(38,12)"
    log("PRO-054", "PASS" if ok else "FAIL", f"type_name={dp.column('amt').type_name}")

async def pro055():
    c = SqliteConnector({"database_path": dbpath})
    calls = []
    orig = c.snapshot
    async def counting_snapshot(path):
        calls.append(path)
        return await orig(path)
    c.snapshot = counting_snapshot
    async with c:
        p = Profiler()
        dp = await p.profile(c, ("t",), capture_snapshot=False)
    ok = len(calls) == 0 and dp.provenance.snapshot is None
    log("PRO-055", "PASS" if ok else "FAIL", f"snapshot_calls={len(calls)} provenance.snapshot={dp.provenance.snapshot}")

async def pro056():
    import pyarrow as pa
    schema = ObjectSchema(path=(), columns=(ColumnSchema(name="a", type_name="INT"),))
    objs = [DiscoveredObject(path=(f"t{i}",)) for i in range(5)]
    batch = pa.RecordBatch.from_arrays([pa.array([1, 2])], names=["a"])
    reads = {("read", (f"t{i}",)): [batch] for i in range(5) if i != 1}
    fc = FakeConnector(objects={"discover": objs, **reads}, describe_map={(f"t{i}",): schema for i in range(5)}, fail_on=("t1",))
    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    lg = logging.getLogger("prama.profile.profiler")
    lg.addHandler(h); lg.setLevel(logging.WARNING)
    async with fc:
        p = Profiler()
        profiles = await p.profile_source(fc)
    ok = len(profiles) == 4 and "t1" in stream.getvalue()
    log("PRO-056", "PASS" if ok else "FAIL", f"n_profiles={len(profiles)} log={stream.getvalue().strip()!r}")

async def pro057():
    import pyarrow as pa
    schema = ObjectSchema(path=(), columns=(ColumnSchema(name="a", type_name="INT"),))
    sizes = [100, 900, 50, 700, 10, 800, 20, 600, 5, 500]
    # A real connector's discover() already returns objects largest-first;
    # the fake has to reproduce that ordering itself for this case to test
    # what it claims (that profile_source does not re-sort) rather than just
    # handing back list-construction order, which sizes[] above is not sorted
    # by at all.
    order = sorted(range(10), key=lambda i: -sizes[i])
    objs = [DiscoveredObject(path=(f"t{i}",), estimated_bytes=sizes[i]) for i in order]
    batch = pa.RecordBatch.from_arrays([pa.array([1])], names=["a"])
    reads = {("read", (f"t{i}",)): [batch] for i in range(10)}
    fc = FakeConnector(objects={"discover": objs, **reads}, describe_map={(f"t{i}",): schema for i in range(10)})
    async with fc:
        p = Profiler()
        profiles = await p.profile_source(fc, limit=3)
    got_paths = [pr.path for pr in profiles]
    ok = got_paths == [("t1",), ("t5",), ("t3",)]  # in discover() order (already sorted by size desc), no re-sort
    log("PRO-057", "PASS" if ok else "FAIL", f"profiled={got_paths} (expected 3 largest, in discover()'s own order: t1(900) t5(800) t3(700))")

def pro058():
    obs = {}
    for n in (None, 0, 5_000_000, 5_000_001, 100_000_000):
        p = suggest_sample_plan(n)
        obs[n] = (p.strategy, p.fraction, p.seed)
    ok = (all(obs[n][0] is SamplingStrategy.FULL for n in (None, 0, 5_000_000, 5_000_001))
          and obs[100_000_000][0] is SamplingStrategy.SYSTEMATIC
          and abs(obs[100_000_000][1] - 0.01) < 1e-9)
    log("PRO-058", "PASS" if ok else "FAIL", str(obs))

def pro059():
    p = suggest_sample_plan(100_000_000)
    ok = p.seed == 1
    log("PRO-059", "PASS" if ok else "FAIL", f"seed={p.seed}")

def pro060():
    obs = {}
    for n in (0, -1, 1, 3, 10_000, 1_000_000):
        obs[n] = detectable_rate(n)
    obs["0.9conf"] = detectable_rate(10_000, confidence=0.9)
    expected = {0: 1.0, -1: 1.0, 1: 1.0, 3: 1.0, 10_000: 0.0003, 1_000_000: 0.000003}
    ok = all(abs(obs[k] - v) < 1e-9 for k, v in expected.items()) and abs(obs["0.9conf"] - 2.3/10000) < 1e-9
    log("PRO-060", "PASS" if ok else "FAIL", str(obs))

def pro061():
    try:
        from_rows(("t",), [], computed_at=utc_now())
        log("PRO-061", "FAIL", "no exception")
    except TypeError as e:
        log("PRO-061", "PASS", f"TypeError: {e}")

def pro062():
    rows = [{"a": 1, "b": 2}, {"a": 3}]
    dp = from_rows(("t",), rows, plan=SamplePlan(), computed_at=utc_now())
    a, b = dp.column("a"), dp.column("b")
    ok = a.rows == 2 and b.rows == 1 and b.nulls == 0 and b.null_rate == 0.0 and dp.provenance.rows_examined == 2
    log("PRO-062", "PASS" if ok else "FAIL", f"a.rows={a.rows} b.rows={b.rows} b.nulls={b.nulls} b.null_rate={b.null_rate} rows_examined={dp.provenance.rows_examined}")

def pro063():
    import prama.profile as pkg
    resolves = hasattr(pkg, "from_rows") or True
    try:
        from prama.profile import from_rows as fr
        resolves = True
    except ImportError:
        resolves = False
    all_list = getattr(pkg, "__all__", [])
    ok = resolves and "from_rows" not in all_list and "points_from_profile" in all_list and "detectable_rate" in all_list and "suggest_sample_plan" in all_list
    log("PRO-063", "PASS" if ok else "FAIL", f"resolves={resolves} in___all__={('from_rows' in all_list)} __all__={all_list}")

async def main():
    await pro049()
    pro050()
    await pro051()
    await pro052()
    await pro053()
    await pro054()
    await pro055()
    await pro056()
    await pro057()
    pro058()
    pro059()
    pro060()
    pro061()
    pro062()
    pro063()

asyncio.run(main())
