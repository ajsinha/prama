import sys, asyncio, logging, io
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.claim import WorkUnit, Claim, FencedWriter, WorkQueue
from prama.execute.worker import Worker, WorkOutcome, _as_triples, FleetReport, run_fleet
from prama.core.concurrency.leases import MemoryLeaseProvider
from prama.core.errors import LeaseLostError
from prama.evidence.recorder import Recorder
from prama.backend.execute import ControlResult
from prama.ir.model import Verdict
from prama.pql import parse_control
from prama.ir.resolve import resolved

CLEAN = "CHECK positions_eod.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'x'"
PLAN = resolved(parse_control(CLEAN))

def unit(resource="r1", zone=""):
    return WorkUnit(resource=resource, dataset="positions_eod", zone=zone)

def good_result():
    return ControlResult(plan_id=PLAN.plan_id, verdict=Verdict.PASS, metrics={"scanned_rows": 10.0, "violating_rows": 0.0})

class FakeHolder:
    """A lease holder under full test control -- no real timing needed."""
    def __init__(self, token=1, lost_after_run=False):
        self.fencing_token = token
        self._lost = False
        self.lost_after_run = lost_after_run
        self.released = False
    async def acquire(self, **kw):
        return True
    def raise_if_lost(self):
        if self._lost:
            raise LeaseLostError("lease lost", remedy="abandon the work")
    async def release(self):
        self.released = True

class FakeProvider:
    def __init__(self, holder):
        self._holder = holder
    def hold(self, resource, *, holder=None, settings=None, clock=None):
        return self._holder

async def exe040():
    q = WorkQueue()
    u = unit()
    q.offer(u)
    holder = FakeHolder(token=1)
    provider = FakeProvider(holder)

    def runner(_unit):
        holder._lost = True  # simulate lease lost while the runner "ran"
        return [(PLAN, good_result(), None)]

    recorder = Recorder()
    stream = io.StringIO()
    lg = logging.getLogger("prama.execute.worker")
    hnd = logging.StreamHandler(stream); lg.addHandler(hnd); lg.setLevel(logging.ERROR)
    w = Worker(q, recorder, lease_provider=provider, runner=runner)
    outcome = await w.take_one()
    ok = outcome.status == "lost" and len(recorder.ledger) == 0 and "discarded" in stream.getvalue()
    log("EXE-040", "PASS" if ok else "FAIL", f"status={outcome.status} records_written={len(recorder.ledger)} log={stream.getvalue().strip()!r}")

def exe041():
    obs = {}
    for status in ("done", "skipped", "lost", "failed", "stranded"):
        o = WorkOutcome(unit=unit(), status=status)
        obs[status] = o.should_requeue
    ok = obs == {"done": False, "skipped": False, "lost": True, "failed": False, "stranded": True}
    log("EXE-041", "PASS" if ok else "FAIL", str(obs))

async def exe042():
    q = WorkQueue()
    u = unit()
    q.offer(u)
    holder = FakeHolder(token=1)
    provider = FakeProvider(holder)

    def runner(_unit):
        return [(PLAN, good_result(), None)]

    class ExplodingRecorder:
        ledger = type("L", (), {"__len__": lambda self: 0})()
        def record(self, *a, **kw):
            raise RuntimeError("ledger unreachable")

    w = Worker(q, ExplodingRecorder(), lease_provider=provider, runner=runner)
    outcome = await w.take_one()
    ok = (outcome.status == "stranded"
          and u in q.pending()
          and u.resource not in q._claimed
          and holder.released is True)
    log("EXE-042", "PASS" if ok else "FAIL", f"status={outcome.status} unit_back_in_pending={u in q.pending()} resource_unclaimed={u.resource not in q._claimed} lease_released={holder.released}")

async def exe043():
    q = WorkQueue()
    u = unit()
    q.offer(u)
    holder = FakeHolder(token=1)
    provider = FakeProvider(holder)

    def runner(_unit):
        return [(PLAN, good_result(), None)]

    class AlwaysExplodingRecorder:
        def record(self, *a, **kw):
            raise RuntimeError("ledger permanently unreachable")

    w = Worker(q, AlwaysExplodingRecorder(), lease_provider=provider, runner=runner)
    # A direct call to drain(limit=0) cannot be interrupted by asyncio.wait_for here: every
    # await in this fake stack resolves synchronously (no real I/O suspension point), so the
    # `while True` loop runs as one unbreakable Task step and never yields back to the event
    # loop for the timeout callback to fire. So the hot loop is demonstrated by bounded
    # repetition instead: take_one() called directly N times, confirming it NEVER returns None
    # (which is the only thing that would make drain()'s `while limit <= 0` loop stop) and
    # keeps re-stranding the identical unit -- which is exactly what would spin forever.
    statuses = []
    for _ in range(200):
        outcome = await w.take_one()
        statuses.append(outcome.status if outcome else None)
    all_stranded_same_unit = all(s == "stranded" for s in statuses) and len(q.pending()) == 1
    log("EXE-043", "FAIL",
        f"take_one() called 200 times directly against a permanently-failing recorder: "
        f"{statuses.count('stranded')}/200 returned 'stranded', {statuses.count(None)}/200 "
        f"returned None; unit still in queue afterward={u in q.pending()}. Since take_one() never "
        f"returns None (confirmed: {statuses.count(None)} times), drain()'s `while limit <= 0: "
        f"outcome = await self.take_one()` -- which only stops on `outcome is None` -- would never "
        f"terminate; confirmed as a hot loop rather than literally hanging the harness process")

def exe044():
    async def run():
        q = WorkQueue()
        for i in range(10):
            q.offer(unit(f"r{i}"))
        provider = MemoryLeaseProvider()
        def runner(_unit):
            return [(PLAN, good_result(), None)]
        recorder = Recorder()
        w = Worker(q, recorder, lease_provider=provider, runner=runner)
        first = await w.drain(limit=3)
        second = await w.drain(limit=0)
        return len(first), len(second)
    n1, n2 = asyncio.run(run())
    ok = n1 == 3 and n2 == 7
    log("EXE-044", "PASS" if ok else "FAIL", f"first_drain(limit=3)={n1} second_drain(limit=0)={n2}")

def exe045():
    async def run():
        q = WorkQueue()
        q.offer(unit("r-none", zone=""))
        q.offer(unit("r-eu", zone="eu"))
        q.offer(unit("r-us", zone="us"))
        provider = MemoryLeaseProvider()
        def runner(_unit):
            return [(PLAN, good_result(), None)]
        recorder1, recorder2 = Recorder(), Recorder()
        w_zoneless = Worker(WorkQueue(), recorder1, lease_provider=MemoryLeaseProvider(), runner=runner)
        w_zoneless._queue.offer(unit("r-none", zone=""))
        w_zoneless._queue.offer(unit("r-eu", zone="eu"))
        w_zoneless._queue.offer(unit("r-us", zone="us"))
        taken_zoneless = await w_zoneless.drain()

        w_eu = Worker(WorkQueue(), recorder2, lease_provider=MemoryLeaseProvider(), zone="eu", runner=runner)
        w_eu._queue.offer(unit("r-none", zone=""))
        w_eu._queue.offer(unit("r-eu", zone="eu"))
        w_eu._queue.offer(unit("r-us", zone="us"))
        taken_eu = await w_eu.drain()
        return taken_zoneless, taken_eu
    tz, teu = asyncio.run(run())
    resources_z = sorted(o.unit.resource for o in tz)
    resources_eu = sorted(o.unit.resource for o in teu)
    ok = resources_z == ["r-eu", "r-none", "r-us"] and resources_eu == ["r-eu"]
    log("EXE-045", "PASS" if ok else "FAIL", f"zoneless_worker_took={resources_z} eu_worker_took={resources_eu}")

def exe049():
    good2 = (PLAN, good_result())
    good3 = (PLAN, good_result(), "snap1")
    bad4 = (PLAN, good_result(), "snap-extra", "fourth-element")
    r2 = _as_triples([good2])
    r3 = _as_triples([good3])
    r4 = _as_triples([bad4])
    ok = (r2[0] == (PLAN, good2[1], None) and r3[0] == (PLAN, good3[1], "snap1")
          and r4[0] == (PLAN, bad4[1], None))  # len==4 not ==3 -> treated as 2-tuple-like, extras dropped
    log("EXE-049", "PASS" if ok else "FAIL", f"2-tuple->{r2[0][2]}; 3-tuple->{r3[0][2]}; 4-tuple->{r4[0]} (snapshot from index 2 'snap-extra' silently dropped, fourth element 'fourth-element' also dropped)")

async def exe050():
    q = WorkQueue()
    q.offer(unit("r1"))
    holder = FakeHolder(token=1)
    provider = FakeProvider(holder)
    class AlwaysExplodingRecorder:
        def record(self, *a, **kw):
            raise RuntimeError("ledger unreachable")
    def runner(_unit):
        return [(PLAN, good_result(), None)]
    w = Worker(q, AlwaysExplodingRecorder(), lease_provider=provider, runner=runner)
    outcome = await w.take_one()  # status=stranded
    report = FleetReport(outcomes=(outcome,), remaining=0)
    rendered = report.render()
    d = report.to_dict()
    has_stranded_attr = hasattr(report, "stranded")
    mentioned = "stranded" in rendered.lower() or "stranded" in str(d).lower()
    log("EXE-050", "FAIL" if not mentioned else "PASS",
        f"outcome.status={outcome.status}; FleetReport has a 'stranded' property={has_stranded_attr}; "
        f"render()={rendered!r}; to_dict()={d}; stranded unit mentioned anywhere={mentioned}")

def exe051():
    async def run():
        provider = MemoryLeaseProvider()
        # Two resources held by a permanent outside holder
        held = []
        async def hog(resource):
            lease = await provider.acquire(resource, "outsider", ttl_seconds=3600)
            held.append(lease)
        asyncio.get_event_loop()
        import asyncio as _a
        await _a.gather(hog("r0"), hog("r1"))
        q = WorkQueue()
        for i in range(20):
            q.offer(unit(f"r{i}"))
        def runner(_unit):
            return [(PLAN, good_result(), None)]
        workers = [Worker(q, Recorder(), lease_provider=provider, runner=runner) for _ in range(4)]
        report = await run_fleet(workers, q)
        return report
    report = asyncio.run(run())
    ok = report.done == 18 and report.remaining == 2
    log("EXE-051", "PASS" if ok else "FAIL", f"done={report.done} remaining={report.remaining} (2 resources held by an outside holder)")

def exe052():
    async def run():
        provider = MemoryLeaseProvider()
        q = WorkQueue()
        for i in range(100):
            q.offer(unit(f"r{i}"))
        def runner(_unit):
            return [(PLAN, good_result(), None)]
        workers = [Worker(q, Recorder(), lease_provider=provider, runner=runner) for _ in range(8)]
        report = await run_fleet(workers, q)
        return report
    report = asyncio.run(run())
    done_outcomes = [o for o in report.outcomes if o.status == "done"]
    resources = [o.unit.resource for o in done_outcomes]
    ok = len(done_outcomes) == 100 and len(set(resources)) == 100
    log("EXE-052", "PASS" if ok else "FAIL", f"n_done={len(done_outcomes)} n_distinct_resources={len(set(resources))}")

def exe053():
    async def run():
        q = WorkQueue()
        for i in range(10):
            q.offer(unit(f"r{i}"))
        provider = MemoryLeaseProvider()
        def runner(_unit):
            return [(PLAN, good_result(), None)]
        w = Worker(q, Recorder(), lease_provider=provider, runner=runner)
        await w.drain()
        return w
    w = asyncio.run(run())
    attrs = {k: v for k, v in vars(w).items()}
    non_config_mutable = [k for k in attrs if k not in ("worker_id", "zone", "_queue", "_recorder", "_leases", "_runner", "_writer", "_lease_seconds", "_clock")]
    ok = non_config_mutable == []
    log("EXE-053", "PASS" if ok else "FAIL", f"instance attributes after draining 10 units: {sorted(attrs.keys())} (all are fixed config/the shared FencedWriter, no per-unit state accumulated)")

def exe054():
    async def run():
        q1, q2 = WorkQueue(), WorkQueue()
        q1.offer(unit("r1")); q2.offer(unit("r1"))
        provider = MemoryLeaseProvider()
        def runner(_unit):
            return [(PLAN, good_result(), None)]
        # shared writer
        shared = FencedWriter()
        h1 = FakeHolder(token=8)
        h2 = FakeHolder(token=7)
        w1_shared = Worker(WorkQueue(), Recorder(), lease_provider=FakeProvider(h1), runner=runner, writer=shared)
        w1_shared._queue.offer(unit("r1"))
        await w1_shared.take_one()  # writes token 8 via shared writer
        w2_shared = Worker(WorkQueue(), Recorder(), lease_provider=FakeProvider(h2), runner=runner, writer=shared)
        w2_shared._queue.offer(unit("r1"))
        outcome_shared = await w2_shared.take_one()  # should be refused (lost) -- stale token 7

        # separate writers
        h1b = FakeHolder(token=8)
        h2b = FakeHolder(token=7)
        w1_sep = Worker(WorkQueue(), Recorder(), lease_provider=FakeProvider(h1b), runner=runner)
        w1_sep._queue.offer(unit("r1"))
        await w1_sep.take_one()
        w2_sep = Worker(WorkQueue(), Recorder(), lease_provider=FakeProvider(h2b), runner=runner)
        w2_sep._queue.offer(unit("r1"))
        outcome_sep = await w2_sep.take_one()  # accepted, separate writer knows nothing of token 8
        return outcome_shared, outcome_sep
    outcome_shared, outcome_sep = asyncio.run(run())
    ok = outcome_shared.status == "lost" and outcome_sep.status == "done"
    log("EXE-054", "PASS" if ok else "FAIL", f"shared_writer: second_worker_token7_after_token8={outcome_shared.status} (expect lost/refused); separate_writers: second_worker_token7={outcome_sep.status} (expect done/accepted)")

async def main():
    await exe040()
    exe041()
    await exe042()
    await exe043()
    exe044()
    exe045()
    exe049()
    await exe050()
    exe051()
    exe052()
    exe053()
    exe054()

asyncio.run(main())
