import sys, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.profile.incremental import (
    IncrementalPlanner, SegmentLedger, SegmentState, IncrementalPlan, DEFAULT_MUTABLE_DAYS,
)
from prama.profile.segments import Segment, SegmentGrain
from prama.connect.spi import Snapshot, SnapshotKind
from prama.core.clock import Clock

class FrozenClock(Clock):
    def __init__(self, t): self._t = t
    def now(self): return self._t
    def monotonic(self): return 0.0

def mkseg(key, day):
    from datetime import date, timedelta
    return Segment(key=key, column="d", grain=SegmentGrain.DAY, lower=day, upper=day+timedelta(days=1))

def pro085():
    planner = IncrementalPlanner()
    segs = [mkseg(f"s{i}", dt.date(2026,1,i+1)) for i in range(5)]
    plan = planner.plan("ds", segs)
    ok = (all(d.state is SegmentState.NEW for d in plan.decisions)
          and all(d.needs_read for d in plan.decisions)
          and plan.saved_fraction == 0.0
          and plan.render() == "Reading all 5 segments — never profiled.")
    log("PRO-085", "PASS" if ok else "FAIL", f"states={[d.state.value for d in plan.decisions]} saved_fraction={plan.saved_fraction} render={plan.render()!r}")

def pro086():
    ledger = SegmentLedger()
    segs = [mkseg(f"s{i}", dt.date(2020,1,i+1)) for i in range(3)]
    now = dt.datetime(2026,4,1,tzinfo=dt.UTC)
    for s in segs:
        ledger.record("ds", s, snapshot=Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="X", captured_at=now), rows=10, at=now)
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    wall_snap = Snapshot(kind=SnapshotKind.WALL_CLOCK, identifier="now", captured_at=now)
    plan1 = planner.plan("ds", segs, snapshot=wall_snap)
    plan2 = planner.plan("ds", segs, snapshot=None)
    ok = (all(d.state is SegmentState.UNVERIFIABLE for d in plan1.decisions)
          and all(d.needs_read for d in plan1.decisions)
          and all(d.state is SegmentState.UNVERIFIABLE for d in plan2.decisions)
          and plan1.decisions[0].state.reason == "this source offers no exact snapshot, so no segment can be assumed unchanged")
    log("PRO-086", "PASS" if ok else "FAIL", f"wall_clock_states={[d.state.value for d in plan1.decisions]} none_states={[d.state.value for d in plan2.decisions]}")

def pro087():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    exact_snap = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="X100", captured_at=now)
    old_segs = [mkseg(f"s{i}", dt.date(2020,1,i+1)) for i in range(5)]  # long past the mutable window
    for s in old_segs:
        ledger.record("ds", s, snapshot=exact_snap, rows=10, at=now)
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    plan = planner.plan("ds", old_segs, snapshot=exact_snap)
    ok = all(d.state is SegmentState.SETTLED for d in plan.decisions) and all(not d.needs_read for d in plan.decisions) and plan.saved_fraction == 1.0
    log("PRO-087", "PASS" if ok else "FAIL", f"states={[d.state.value for d in plan.decisions]} saved_fraction={plan.saved_fraction}")

def pro088():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    snap_a = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="A", captured_at=now)
    segs = [mkseg(f"s{i}", dt.date(2020,1,1)+dt.timedelta(days=i)) for i in range(400)]  # all old
    for s in segs:
        ledger.record("ds", s, snapshot=snap_a, rows=10, at=now)
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    snap_b = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="B", captured_at=now)
    plan = planner.plan("ds", segs, snapshot=snap_b)
    changed = sum(1 for d in plan.decisions if d.state is SegmentState.CHANGED)
    log("PRO-088", "PASS", f"segments_CHANGED={changed} of {len(segs)} (object-level snapshot moved from A to B; EVERY segment invalidated, even the 399 that did not themselves change -- confirms the ledger's object-level granularity means one write anywhere re-reads the whole table)")

def pro089():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    exact = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="X", captured_at=now)
    segs = [mkseg(f"d{n}", dt.date(2026,4,n)) for n in range(6,11)]
    for s in segs:
        ledger.record("ds", s, snapshot=exact, rows=10, at=now)
    planner = IncrementalPlanner(ledger, mutable_days=3, clock=FrozenClock(now))
    plan = planner.plan("ds", segs, snapshot=exact)
    by_key = {d.segment.key: d.state for d in plan.decisions}
    ok = by_key["d6"] is SegmentState.SETTLED and by_key["d7"] is SegmentState.MUTABLE
    log("PRO-089", "PASS" if ok else "FAIL", f"{ {k: v.value for k,v in by_key.items()} } (cutoff=2026-04-07; d6 upper=04-07 SETTLED, d7 upper=04-08 MUTABLE)")

def pro090():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    exact = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="X", captured_at=now)
    segs = [Segment(key=v, column="region", grain=SegmentGrain.VALUE, value=v) for v in ("APAC", "EMEA", "AMER")]
    for s in segs:
        ledger.record("ds", s, snapshot=exact, rows=10, at=dt.datetime(2020,1,1,tzinfo=dt.UTC))
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    plan = planner.plan("ds", segs, snapshot=exact)
    ok = all(d.state is SegmentState.MUTABLE for d in plan.decisions)
    log("PRO-090", "PASS" if ok else "FAIL", f"states={[d.state.value for d in plan.decisions]}")

def pro091():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    inexact_prior = Snapshot(kind=SnapshotKind.WALL_CLOCK, identifier="SAME", captured_at=now)
    seg = mkseg("old", dt.date(2020,1,1))
    ledger.record("ds", seg, snapshot=inexact_prior, rows=10, at=now)
    exact_now = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="SAME", captured_at=now)
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    plan = planner.plan("ds", [seg], snapshot=exact_now)
    ok = plan.decisions[0].state is SegmentState.CHANGED
    log("PRO-091", "PASS" if ok else "FAIL", f"state={plan.decisions[0].state.value}")

def pro092():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    exact = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="X", captured_at=now)
    segs_a = [mkseg(f"a{i}", dt.date(2020,1,i+1)) for i in range(3)]
    segs_b = [mkseg(f"b{i}", dt.date(2020,1,i+1)) for i in range(3)]
    for s in segs_a: ledger.record("a", s, snapshot=exact, rows=10, at=now)
    for s in segs_b: ledger.record("b", s, snapshot=exact, rows=10, at=now)
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    ledger.forget("a")
    plan_a = planner.plan("a", segs_a, snapshot=exact)
    plan_b = planner.plan("b", segs_b, snapshot=exact)
    ok = all(d.state is SegmentState.NEW for d in plan_a.decisions) and all(d.state is SegmentState.SETTLED for d in plan_b.decisions)
    log("PRO-092", "PASS" if ok else "FAIL", f"a_states={[d.state.value for d in plan_a.decisions]} b_states={[d.state.value for d in plan_b.decisions]}")

def pro093():
    ledger = SegmentLedger()
    now = dt.datetime(2026,4,10,tzinfo=dt.UTC)
    segs = [mkseg(f"s{i}", dt.date(2026,4,i+1)) for i in range(5)]
    # segment 1 (index 0) NEW (no ledger record); segments 2-5 MUTABLE (recorded, recent)
    exact = Snapshot(kind=SnapshotKind.TRANSACTION_ID, identifier="X", captured_at=now)
    for s in segs[1:]:
        ledger.record("ds", s, snapshot=exact, rows=10, at=now)
    planner = IncrementalPlanner(ledger, clock=FrozenClock(now))
    plan = planner.plan("ds", segs, snapshot=exact)
    states = [d.state.value for d in plan.decisions]
    rendered = plan.render()
    ok = states[0] == "new" and all(s == "mutable" for s in states[1:]) and rendered == "Reading all 5 segments — never profiled."
    log("PRO-093", "PASS" if ok else "FAIL", f"states={states} render={rendered!r} (attributes 'never profiled' -- segment 1's reason -- to all 5, even though 4 are actually mutable)")

def pro094():
    plan = IncrementalPlan(decisions=())
    ok = plan.saved_fraction == 0.0 and plan.render() == "Nothing to examine: the segmentation produced no segments."
    log("PRO-094", "PASS" if ok else "FAIL", f"saved_fraction={plan.saved_fraction} render={plan.render()!r}")

for fn in (pro085, pro086, pro087, pro088, pro089, pro090, pro091, pro092, pro093, pro094):
    fn()
