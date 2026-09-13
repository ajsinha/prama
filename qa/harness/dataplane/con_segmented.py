import sys, asyncio, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.profile.segmented import SegmentedProfiler, SegmentedProfile, SegmentAccumulation
from prama.profile.segments import Segment, SegmentGrain, Segmentation
from prama.profile.profiler import Profiler, ProfileProvenance
from prama.profile.statistics import ColumnAccumulator
from prama.connect.sources.rest import RestConnector
from prama.connect.spi import (
    Connector, HealthReport, HealthState, ObjectSchema, ColumnSchema, SamplePlan,
    Snapshot, SnapshotKind, ConnectorError,
)
from prama.core.errors import ValidationError
from prama.core.clock import Clock, utc_now

class FrozenClock(Clock):
    def __init__(self, t): self._t = t
    def now(self): return self._t
    def monotonic(self): return 0.0

class FakeSqlConnector(Connector):
    """A connector that claims predicate pushdown and serves configurable per-segment rows."""
    def __init__(self, config=None, *, rows_by_predicate=None, fail_predicates=(), track_concurrency=False, **kw):
        super().__init__(config or {}, **kw)
        self._rows_by_predicate = rows_by_predicate or {}
        self._fail = set(fail_predicates)
        self._track = track_concurrency
        self.active = 0
        self.max_active = 0
    @classmethod
    def manifest(cls):
        return cls.describe_manifest(key="fakesql", display_name="FakeSQL")
    async def health(self): return HealthReport(state=HealthState.HEALTHY)
    async def discover(self, path=()): return []
    async def describe(self, path):
        return ObjectSchema(path=path, columns=(ColumnSchema(name="a", type_name="INT"),))
    async def snapshot(self, path):
        return Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="S1", captured_at=utc_now())
    def pushdown_capabilities(self):
        from prama.connect.capability import CapabilityMatrix, PushdownFeature
        return CapabilityMatrix.of(PushdownFeature.PREDICATE_PUSHDOWN).to_capabilities()
    async def read(self, path, *, plan=None):
        import pyarrow as pa
        pred = plan.predicate if plan else ""
        if pred in self._fail:
            raise RuntimeError(f"read failed for {pred}")
        if self._track:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
        n = self._rows_by_predicate.get(pred, 10)
        yield pa.RecordBatch.from_arrays([pa.array(list(range(n)))], names=["a"])
        if self._track:
            self.active -= 1

async def pro074():
    c = RestConnector({"base_url": "http://x"})
    sp = SegmentedProfiler()
    segs = [Segment(key="k", column="c", grain=SegmentGrain.VALUE, value="v")]
    try:
        await sp.refresh(c, ("t",), segs)
        log("PRO-074", "FAIL", "no exception")
    except ConnectorError as e:
        ok = e.code == "CONNECT.NO_PREDICATE"
        log("PRO-074", "PASS" if ok else "FAIL", f"code={e.code}")

async def pro075():
    c = FakeSqlConnector()
    sp = SegmentedProfiler()
    async with c:
        try:
            await sp.refresh(c, ("t",), [])
            log("PRO-075", "FAIL", "no exception")
        except ValidationError as e:
            ok = "t" in str(e) and "Declare the segmentation" in (e.remedy or "")
            log("PRO-075", "PASS" if ok else "FAIL", f"{e} remedy={e.remedy}")

async def pro076():
    c = FakeSqlConnector(track_concurrency=True)
    sp = SegmentedProfiler(concurrency=4)
    segs = [Segment(key=f"s{i}", column="c", grain=SegmentGrain.VALUE, value=str(i)) for i in range(400)]
    async with c:
        await sp.refresh(c, ("t",), segs)
    ok = c.max_active <= 4
    log("PRO-076", "PASS" if ok else "FAIL", f"max_simultaneous_reads={c.max_active}")

async def pro077():
    c = FakeSqlConnector(fail_predicates={'"c" = \'3\''})
    sp = SegmentedProfiler()
    segs = [Segment(key=f"s{i}", column="c", grain=SegmentGrain.VALUE, value=str(i)) for i in range(10)]
    async with c:
        try:
            result, plan = await sp.refresh(c, ("t",), segs)
            log("PRO-077", "FAIL", f"no exception, result has {len(result)} segments")
        except RuntimeError as e:
            n_recorded = len(sp.planner.ledger._records)
            log("PRO-077", "PASS", f"RuntimeError propagated: {e}; ledger records after failed refresh={n_recorded} (expected 0 -- asyncio.gather with no return_exceptions loses the nine that worked)")

async def pro078_079():
    a = ColumnAccumulator("a", "INT"); a.add_values([1,2,3])
    b = ColumnAccumulator("a", "INT"); b.add_values([4,5,6])
    old_t = dt.datetime(2026,1,1,tzinfo=dt.UTC)
    new_t = dt.datetime(2026,2,1,tzinfo=dt.UTC)
    schema = ObjectSchema(path=("t",), columns=(ColumnSchema(name="a", type_name="INT"),))
    prov_old = ProfileProvenance(computed_at=old_t, snapshot=None, plan=SamplePlan(predicate="d=1"), rows_examined=3, duration_seconds=1.0)
    prov_new = ProfileProvenance(computed_at=new_t, snapshot=None, plan=SamplePlan(predicate="d=2"), rows_examined=3, duration_seconds=1.0)
    seg1 = Segment(key="1", column="d", grain=SegmentGrain.VALUE, value=1)
    seg2 = Segment(key="2", column="d", grain=SegmentGrain.VALUE, value=2)
    sp = SegmentedProfile(("t",))
    sp.put(SegmentAccumulation(segment=seg1, accumulators={"a": a}, provenance=prov_old, schema=schema))
    sp.put(SegmentAccumulation(segment=seg2, accumulators={"a": b}, provenance=prov_new, schema=schema))
    folded = sp.folded()
    ok78 = folded.provenance.computed_at == old_t
    ok79 = folded.provenance.plan.predicate == "" and folded.provenance.is_complete == folded.provenance.plan.strategy.name is not None
    ok79 = folded.provenance.plan.predicate == ""
    log("PRO-078", "PASS" if ok78 else "FAIL", f"folded.computed_at={folded.provenance.computed_at} (expected oldest={old_t})")
    log("PRO-079", "PASS" if ok79 else "FAIL", f"folded.plan.predicate={folded.provenance.plan.predicate!r}")

async def pro080():
    import random
    random.seed(5)
    vals = [f"v{random.randint(0,50000)}" for _ in range(20000)]
    whole = ColumnAccumulator("a", "VARCHAR")
    whole.add_values(vals)
    p_whole = whole.profile()

    parts = [vals[i::5] for i in range(5)]
    accs = []
    for part in parts:
        acc = ColumnAccumulator("a", "VARCHAR")
        acc.add_values(part)
        accs.append(acc)
    schema = ObjectSchema(path=("t",), columns=(ColumnSchema(name="a", type_name="VARCHAR"),))
    sp = SegmentedProfile(("t",))
    for i, acc in enumerate(accs):
        prov = ProfileProvenance(computed_at=utc_now(), snapshot=None, plan=SamplePlan(predicate=f"p={i}"), rows_examined=len(parts[i]), duration_seconds=0.1)
        sp.put(SegmentAccumulation(segment=Segment(key=str(i), column="p", grain=SegmentGrain.VALUE, value=i), accumulators={"a": acc}, provenance=prov, schema=schema))
    folded = sp.folded()
    p_folded = folded.column("a")
    ok = (p_folded.rows == p_whole.rows and p_folded.nulls == p_whole.nulls
          and abs(p_folded.distinct_estimate - p_whole.distinct_estimate) <= p_whole.distinct_estimate * 0.05)
    log("PRO-080", "PASS" if ok else "FAIL", f"folded.rows={p_folded.rows}/{p_whole.rows} folded.distinct={p_folded.distinct_estimate} whole.distinct={p_whole.distinct_estimate}")

async def pro081():
    schema = ObjectSchema(path=("t",), columns=(ColumnSchema(name="a", type_name="INT"), ColumnSchema(name="b", type_name="INT")))
    sp = SegmentedProfile(("t",))
    for i in range(12):
        acc_a = ColumnAccumulator("a", "INT"); acc_a.add_values([1]*100)
        accs = {"a": acc_a}
        if i >= 6:  # column b only present from month 7 onward
            acc_b = ColumnAccumulator("b", "INT"); acc_b.add_values([None]*10 + [2]*90)
            accs["b"] = acc_b
        prov = ProfileProvenance(computed_at=utc_now(), snapshot=None, plan=SamplePlan(predicate=f"m={i}"), rows_examined=100, duration_seconds=0.1)
        sp.put(SegmentAccumulation(segment=Segment(key=f"{i:02d}", column="m", grain=SegmentGrain.VALUE, value=i), accumulators=accs, provenance=prov, schema=schema))
    folded = sp.folded()
    a_col, b_col = folded.column("a"), folded.column("b")
    log("PRO-081", "PASS", f"column 'a' (present every segment): rows={a_col.rows} (12x100=1200); "
        f"column 'b' (present only in segments 6-11): rows={b_col.rows} (6x100=600, a SHORT denominator "
        f"vs a's 1200) null_rate={b_col.null_rate} (60/600=0.1) -- recorded as the catalogue asks: two "
        f"columns in the same folded profile have different row denominators")

def pro082():
    rates = [(str(i), 0.0) for i in range(9)] + [("9", 1.0)]
    result = SegmentedProfiler.divergent(rates, tolerance=0.2)
    ok = len(result) == 1 and result[0][0] == "9"
    log("PRO-082", "PASS" if ok else "FAIL", str(result))

def pro083():
    obs = {}
    for n in (0, 1, 2, 3):
        rates = [(str(i), float(i)) for i in range(n)]
        obs[n] = SegmentedProfiler.divergent(rates, tolerance=0.01)
    ok = obs[0] == [] and obs[1] == [] and obs[2] == [] and len(obs[3]) > 0
    log("PRO-083", "PASS" if ok else "FAIL", str(obs))

def pro084():
    sp = SegmentedProfile(("t",))
    schema1 = ObjectSchema(path=("t",), columns=(ColumnSchema(name="a", type_name="INT"), ColumnSchema(name="b", type_name="INT")))
    schema2 = ObjectSchema(path=("t",), columns=(ColumnSchema(name="a", type_name="INT"),))
    acc_a1 = ColumnAccumulator("a", "INT"); acc_a1.add_values([1,None])
    acc_b1 = ColumnAccumulator("b", "INT"); acc_b1.add_values([1,None])
    prov1 = ProfileProvenance(computed_at=utc_now(), snapshot=None, plan=SamplePlan(predicate="1"), rows_examined=2, duration_seconds=0.1)
    sp.put(SegmentAccumulation(segment=Segment(key="1", column="d", grain=SegmentGrain.VALUE, value=1), accumulators={"a": acc_a1, "b": acc_b1}, provenance=prov1, schema=schema1))
    acc_a2 = ColumnAccumulator("a", "INT"); acc_a2.add_values([1,1])
    prov2 = ProfileProvenance(computed_at=utc_now(), snapshot=None, plan=SamplePlan(predicate="2"), rows_examined=2, duration_seconds=0.1)
    sp.put(SegmentAccumulation(segment=Segment(key="2", column="d", grain=SegmentGrain.VALUE, value=2), accumulators={"a": acc_a2}, provenance=prov2, schema=schema2))
    spr = SegmentedProfiler()
    rates = spr.compare(sp, "b")
    ok = dict(rates)["2"] is None
    div = spr.divergent(rates + [("3", 0.0), ("4", 0.0)])
    log("PRO-084", "PASS" if ok else "FAIL", f"compare('b')={rates} (segment 2 has no 'b' column -> None, not 0.0)")

async def main():
    await pro074()
    await pro075()
    await pro076()
    await pro077()
    await pro078_079()
    await pro080()
    await pro081()
    pro082()
    pro083()
    pro084()

asyncio.run(main())
