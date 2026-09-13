import sys, os, asyncio, time, threading, random, statistics
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.concurrency.supervisor import TaskSupervisor, RestartPolicy
from prama.core.concurrency.leases import (
    MemoryLeaseProvider, LeaseSettings, LeaseHolder, LeaseProvider, Lease,
)
from prama.core.concurrency.limits import ConcurrencyLimiter, RateLimiter
from prama.core.concurrency.affinity import DedicatedThread
from prama.core.clock import ManualClock
from prama.core.errors import ConcurrencyError, LeaseLostError, BackPressureError, PramaError
from datetime import datetime, timezone, timedelta

async def main():
    # CFG-199
    sup199 = TaskSupervisor(shutdown_grace=2.0)
    async def long_task():
        await asyncio.sleep(60)
    async with sup199 as s:
        h1 = s.spawn("a", long_task)
        h2 = s.spawn("b", long_task)
        await asyncio.sleep(0.05)
    R("CFG-199", h1.task.done() and h2.task.done() and h1.stopped and h2.stopped,
      f"a.done={h1.task.done()} a.stopped={h1.stopped}; b.done={h2.task.done()} b.stopped={h2.stopped}")

    # CFG-200
    sup200 = TaskSupervisor()
    async def loopforever():
        await asyncio.sleep(30)
    sup200.spawn("dispatch", loopforever)
    await asyncio.sleep(0.02)
    try:
        sup200.spawn("dispatch", loopforever)
        R("CFG-200", False, "no exception on duplicate running name")
    except ConcurrencyError as e:
        R("CFG-200", e.code == "CONCURRENCY.INVARIANT" and "dispatch" in str(e), str(e))
    await sup200.shutdown()

    # CFG-201
    sup201 = TaskSupervisor()
    async def quick():
        return None
    h201 = sup201.spawn("oneshot", quick, policy=RestartPolicy.NEVER)
    await asyncio.sleep(0.05)
    try:
        h201b = sup201.spawn("oneshot", quick, policy=RestartPolicy.NEVER)
        R("CFG-201", True, "re-spawn of stopped name accepted")
    except ConcurrencyError as e:
        R("CFG-201", False, f"unexpectedly refused: {e}")
    await sup201.shutdown()

    # CFG-202
    sup202 = TaskSupervisor()
    async def raiser():
        raise ValueError("boom202")
    h202 = sup202.spawn("oneshot202", raiser, policy=RestartPolicy.NEVER)
    await asyncio.sleep(0.1)
    R("CFG-202", len(sup202._failures) == 1 and h202.restarts == 0,
      f"failures={len(sup202._failures)} restarts={h202.restarts}")
    await sup202.shutdown()

    # CFG-203
    mc203 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    attempts = 0
    async def always_raises():
        nonlocal attempts
        attempts += 1
        raise ValueError("fail203")
    sup203 = TaskSupervisor(clock=mc203, max_restarts=3, restart_window=60, base_backoff=0.001, max_backoff=0.01)
    h203 = sup203.spawn("bad", always_raises, policy=RestartPolicy.ON_FAILURE)
    # let it run to completion (bounded number of fast retries)
    for _ in range(200):
        if not h203.running:
            break
        await asyncio.sleep(0.01)
    R("CFG-203", attempts == 4 and len(sup203._failures) == 1 and "crash loop is a defect" in str(sup203._failures[0]),
      f"attempts={attempts}, failures={len(sup203._failures)}, msg={str(sup203._failures[0]) if sup203._failures else None}")
    await sup203.shutdown()

    # CFG-204
    mc204 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    count204 = 0
    sup204 = TaskSupervisor(clock=mc204, max_restarts=2, restart_window=10, base_backoff=0.001, max_backoff=0.001)
    async def spaced_fail():
        nonlocal count204
        count204 += 1
        mc204.advance(20)  # beyond restart_window each time
        raise ValueError("spaced")
    h204 = sup204.spawn("spaced", spaced_fail, policy=RestartPolicy.ON_FAILURE)
    for _ in range(50):
        await asyncio.sleep(0.02)
        if count204 >= 10:
            break
    gave_up = len(sup204._failures) > 0
    R("CFG-204", not gave_up and count204 >= 5, f"count={count204}, gave_up={gave_up}")
    await sup204.shutdown()

    # CFG-205
    sup205 = TaskSupervisor()
    async def poller():
        return None
    h205 = sup205.spawn("poll", poller, policy=RestartPolicy.ALWAYS)
    await asyncio.sleep(0.2)
    R("CFG-205", h205.restarts > 2, f"restarts after 0.2s of an instantly-returning ALWAYS task={h205.restarts}")
    await sup205.shutdown()

    # CFG-206
    sup206 = TaskSupervisor(base_backoff=0.2, max_backoff=30)
    samples = {}
    for n in [1, 5, 10, 16, 20]:
        vals = [sup206._backoff(n) for _ in range(200)]
        ceiling = min(30, 0.2 * (2 ** min(n, 16)))
        samples[n] = (min(vals), max(vals), ceiling, len(set(round(v,6) for v in vals)) > 50)
    ok206 = all(0 <= mn and mx <= ceil + 1e-9 for mn, mx, ceil, varies in samples.values()) and all(varies for *_, varies in samples.values())
    R("CFG-206", ok206, str(samples))

    # CFG-207
    sup207 = TaskSupervisor(shutdown_grace=1.0)
    async def cooperative():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
    h207 = sup207.spawn("coop", cooperative, policy=RestartPolicy.ON_FAILURE)
    await asyncio.sleep(0.05)
    await sup207.shutdown()
    R("CFG-207", len(sup207._failures) == 0, f"failures after cancellation-based shutdown={len(sup207._failures)}")

    # CFG-208
    sup208 = TaskSupervisor()
    async def raiser208():
        raise ValueError("x208")
    sup208.spawn("r208", raiser208, policy=RestartPolicy.NEVER)
    await asyncio.sleep(0.05)
    healthy = not sup208._failures
    R("CFG-208", healthy is False, f"failures={len(sup208._failures)} (healthy() == not failures)")
    await sup208.shutdown()

    # CFG-209
    sup209 = TaskSupervisor()
    async def raiser209a():
        raise ValueError("first209")
    async def raiser209b():
        raise RuntimeError("second209")
    sup209.spawn("a209", raiser209a, policy=RestartPolicy.NEVER)
    sup209.spawn("b209", raiser209b, policy=RestartPolicy.NEVER)
    await asyncio.sleep(0.05)
    has_raise_for_failures = hasattr(sup209, "raise_for_failures")
    if has_raise_for_failures:
        try:
            sup209.raise_for_failures()
            R("CFG-209", False, "raise_for_failures did not raise")
        except Exception as e:
            R("CFG-209", "first209" in str(e), f"raised {type(e).__name__}: {e}")
    else:
        R("CFG-209", None, "BLOCKED: TaskSupervisor has no raise_for_failures / healthy method -- checking module attrs")
    await sup209.shutdown()

    # CFG-210
    sup210 = TaskSupervisor(shutdown_grace=0.2)
    async def t210():
        await asyncio.sleep(30)
    sup210.spawn("t210", t210)
    await sup210.shutdown()
    nfail_before = len(sup210._failures)
    try:
        await sup210.shutdown()
        R("CFG-210", len(sup210._failures) == nfail_before, f"second shutdown() OK, failures unchanged={len(sup210._failures)}")
    except Exception as e:
        R("CFG-210", False, f"{type(e).__name__}: {e}")

    # CFG-211/212/213 -- run_sync
    try:
        from prama.core.concurrency.supervisor import run_sync
    except ImportError:
        run_sync = None
    if run_sync is None:
        R("CFG-211", None, "BLOCKED: run_sync not found in supervisor module")
        R("CFG-212", None, "BLOCKED: run_sync not found")
        R("CFG-213", None, "BLOCKED: run_sync not found")
    else:
        R("CFG-211", None, "deferred to sync harness below")

    # CFG-214
    p214 = MemoryLeaseProvider()
    la = await p214.acquire("res214", "A", 30)
    lb = await p214.acquire("res214", "B", 30)
    R("CFG-214", la is not None and lb is None, f"A got={la is not None}, B got={lb}")

    # CFG-215
    p215 = MemoryLeaseProvider()
    l1 = await p215.acquire("res215", "A", 30)
    l2 = await p215.acquire("res215", "A", 30)
    R("CFG-215", l2 is not None and l2.fencing_token == l1.fencing_token + 1, f"first={l1.fencing_token}, second={l2.fencing_token}")

    # CFG-216
    mc216 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    p216 = MemoryLeaseProvider(clock=mc216)
    la216 = await p216.acquire("res216", "A", 5)
    mc216.advance(10)  # expire it
    lb216 = await p216.acquire("res216", "B", 30)
    R("CFG-216", lb216 is not None and lb216.fencing_token > la216.fencing_token, f"B got={lb216 is not None}, token {la216.fencing_token}->{lb216.fencing_token if lb216 else None}")

    # CFG-217
    p217 = MemoryLeaseProvider()
    la217 = await p217.acquire("res217", "A", 5)
    # B takes over: to do that we need A's lease to be expired or A releases
    await p217.release(la217)
    lb217 = await p217.acquire("res217", "B", 30)
    renew_result = await p217.renew(la217, 30)
    R("CFG-217", renew_result is None, f"A renew after B took over -> {renew_result}")

    # CFG-218
    p218 = MemoryLeaseProvider()
    la218 = await p218.acquire("res218", "A", 5)
    await p218.release(la218)
    lb218 = await p218.acquire("res218", "B", 30)
    release_result = await p218.release(la218)
    inspect218 = await p218.inspect("res218")
    R("CFG-218", release_result is False and inspect218 is not None and inspect218.holder == "B",
      f"A release-after-lost={release_result}, current holder={inspect218.holder if inspect218 else None}")

    # CFG-219
    mc219 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    p219 = MemoryLeaseProvider(clock=mc219)
    await p219.acquire("res219", "A", 5)
    mc219.advance(10)
    ins219 = await p219.inspect("res219")
    R("CFG-219", ins219 is None, repr(ins219))

    # CFG-220
    mc220 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    p220 = MemoryLeaseProvider(clock=mc220)
    settings220 = LeaseSettings(ttl_seconds=0.3, renew_interval_seconds=0.1)
    holder220 = LeaseHolder(p220, "res220", holder="H220", settings=settings220, clock=mc220)
    await holder220.acquire()
    lost_at_any_point = False
    for _ in range(10):
        await asyncio.sleep(0.1)
        mc220.advance(0.1)
        if not holder220.valid:
            lost_at_any_point = True
    await holder220.release()
    R("CFG-220", not lost_at_any_point, f"lost_at_any_point={lost_at_any_point}")

    # CFG-221
    class DenyingProvider(LeaseProvider):
        def __init__(self, real): self._real = real
        async def acquire(self, resource, holder, ttl): return await self._real.acquire(resource, holder, ttl)
        async def renew(self, lease, ttl): return None
        async def release(self, lease): return await self._real.release(lease)
        async def inspect(self, resource): return await self._real.inspect(resource)
    real221 = MemoryLeaseProvider()
    deny221 = DenyingProvider(real221)
    settings221 = LeaseSettings(ttl_seconds=1.0, renew_interval_seconds=0.1)
    holder221 = LeaseHolder(deny221, "res221", holder="H221", settings=settings221)
    await holder221.acquire()
    await asyncio.sleep(0.25)
    R("CFG-221", not holder221.valid, f"valid after renew denied={holder221.valid}")
    await holder221.release()

    # CFG-222
    mc222 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    p222 = MemoryLeaseProvider(clock=mc222)
    settings222 = LeaseSettings(ttl_seconds=5.0, renew_interval_seconds=100.0)  # effectively suppress renewer within test window... but 100>=5*... validate() will warn/allow? renew_interval>=ttl raises! use huge ttl instead
    # redo with renew disabled by cancelling the renewer task after acquire
    settings222 = LeaseSettings(ttl_seconds=5.0, renew_interval_seconds=2.0)
    holder222 = LeaseHolder(p222, "res222", holder="H222", settings=settings222, clock=mc222)
    await holder222.acquire()
    if holder222._renewer:
        holder222._renewer.cancel()
    mc222.advance(10)  # past expiry
    try:
        holder222.raise_if_lost()
        R("CFG-222", False, "no LeaseLostError past expiry")
    except LeaseLostError as e:
        R("CFG-222", "abandon the work" in e.remedy.lower(), str(e))

    # CFG-223
    holder223 = LeaseHolder(MemoryLeaseProvider(), "res223", holder="H223")
    try:
        _ = holder223.fencing_token
        R("CFG-223", False, "no exception; got a fencing_token with no lease held")
    except LeaseLostError:
        R("CFG-223", True, "raised as expected")

    # CFG-224
    p224 = MemoryLeaseProvider()
    holderA224 = LeaseHolder(p224, "res224", holder="A224")
    await holderA224.acquire()
    holderB224 = LeaseHolder(p224, "res224", holder="B224")
    try:
        async with holderB224:
            pass
        R("CFG-224", False, "no exception entering context on a held lease")
    except LeaseLostError as e:
        ok224 = "normal in a fleet" in e.remedy and "acquire(wait=True)" in e.remedy
        R("CFG-224", ok224, str(e))
    await holderA224.release()

    # CFG-225
    p225 = MemoryLeaseProvider()
    holderA225 = LeaseHolder(p225, "res225", holder="A225", settings=LeaseSettings(ttl_seconds=30, renew_interval_seconds=10))
    await holderA225.acquire()
    await holderA225.release()
    holderB225 = LeaseHolder(p225, "res225", holder="B225")
    t0 = time.monotonic()
    got225 = await holderB225.acquire()
    dt225 = time.monotonic() - t0
    R("CFG-225", got225 and dt225 < 1.0, f"B acquired={got225} after {dt225*1000:.1f}ms")
    await holderB225.release()

    # CFG-226
    p226 = MemoryLeaseProvider()
    holder226 = LeaseHolder(p226, "res226", holder="H226")
    await holder226.acquire()
    renewer_before = holder226._renewer
    await holder226.release()
    await holder226.release()  # idempotent
    R("CFG-226", holder226._renewer is None and (renewer_before.cancelled() or renewer_before.done()),
      f"renewer after release: {holder226._renewer}; original renewer done/cancelled={renewer_before.done()}")

    # CFG-227
    p227 = MemoryLeaseProvider()
    holderA227 = LeaseHolder(p227, "res227", holder="A227", settings=LeaseSettings(ttl_seconds=30, renew_interval_seconds=10))
    await holderA227.acquire()
    async def release_later():
        await asyncio.sleep(0.15)
        await holderA227.release()
    asyncio.create_task(release_later())
    holderB227 = LeaseHolder(p227, "res227", holder="B227")
    t0 = time.monotonic()
    got227 = await holderB227.acquire(wait=True, poll_interval=0.05)
    dt227 = time.monotonic() - t0
    R("CFG-227", got227 and 0.1 < dt227 < 2.0, f"B acquired={got227} after {dt227:.3f}s")
    await holderB227.release()

    # CFG-228
    lim228 = ConcurrencyLimiter(3)
    in_flight_samples = []
    async def holder228():
        async with lim228.acquire(timeout=5):
            in_flight_samples.append(lim228.in_flight)
            await asyncio.sleep(0.1)
    await asyncio.gather(*(holder228() for _ in range(10)))
    R("CFG-228", max(in_flight_samples) <= 3 and lim228.high_water == 3, f"max observed in_flight={max(in_flight_samples)}, high_water={lim228.high_water}")

    # CFG-229
    try:
        ConcurrencyLimiter(0)
        R("CFG-229", False, "no exception")
    except ValueError:
        R("CFG-229", True, "refused")

    # CFG-230
    lim230 = ConcurrencyLimiter(1, name="lim230")
    async def hold230():
        async with lim230.acquire(timeout=5):
            await asyncio.sleep(1.0)
    t230 = asyncio.create_task(hold230())
    await asyncio.sleep(0.05)
    try:
        async with lim230.acquire(timeout=0.05):
            pass
        R("CFG-230", False, "no BackPressureError")
    except BackPressureError as e:
        R("CFG-230", "limiter" in e.context and "limit" in e.context, str(e.context))
    await t230

    # CFG-231
    lim231 = ConcurrencyLimiter(1)
    try:
        async with lim231.acquire(timeout=1):
            raise RuntimeError("boom231")
    except RuntimeError:
        pass
    t0 = time.monotonic()
    async with lim231.acquire(timeout=1):
        pass
    dt231 = time.monotonic() - t0
    R("CFG-231", dt231 < 0.5, f"second acquire after exception took {dt231*1000:.1f}ms")

    # CFG-232
    lim232 = ConcurrencyLimiter(2)
    for _ in range(5):
        try:
            async with lim232.acquire(timeout=1):
                if random.random() < 0.5:
                    raise RuntimeError("x")
        except RuntimeError:
            pass
    R("CFG-232", lim232.in_flight == 0, f"in_flight after cycles={lim232.in_flight}")

    # CFG-233
    mc233 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    rl233 = RateLimiter(10, capacity=10, clock=mc233)
    t0 = time.monotonic()
    for _ in range(10):
        await rl233.acquire(1, timeout=1)
    dt_burst = time.monotonic() - t0
    # 11th over real clock this time (need real time passing) -- use real SystemClock-driven limiter instead
    rl233b = RateLimiter(10, capacity=10)
    for _ in range(10):
        await rl233b.acquire(1, timeout=1)
    t0b = time.monotonic()
    await rl233b.acquire(1, timeout=1)
    dt11 = time.monotonic() - t0b
    R("CFG-233", dt_burst < 0.05 and 0.05 < dt11 < 0.5, f"burst-of-10 took {dt_burst*1000:.1f}ms; 11th waited {dt11*1000:.1f}ms")

    # CFG-234
    rl234 = RateLimiter(10, capacity=10)
    try:
        await rl234.acquire(11)
        R("CFG-234", False, "no exception")
    except ValueError as e:
        R("CFG-234", "11" in str(e) and "10" in str(e), str(e))

    # CFG-235
    rl235 = RateLimiter(1, capacity=1)
    await rl235.acquire(1)  # drain the bucket
    try:
        await rl235.acquire(1, timeout=0.1)
        R("CFG-235", False, "no BackPressureError")
    except BackPressureError as e:
        R("CFG-235", "budget" in str(e).lower(), str(e))

    # CFG-236
    rl236 = RateLimiter(1, capacity=1)
    await rl236.acquire(1)
    before236 = rl236.available
    t0 = time.monotonic()
    ok236 = rl236.try_acquire(1)
    dt236 = time.monotonic() - t0
    R("CFG-236", ok236 is False and dt236 < 0.02, f"try_acquire={ok236}, took {dt236*1000:.2f}ms")

    # CFG-237
    mc237 = ManualClock(datetime(2026,1,1,tzinfo=timezone.utc))
    rl237 = RateLimiter(5, capacity=5, clock=mc237)
    mc237.advance(3600)
    R("CFG-237", rl237.available == 5, repr(rl237.available))

    # CFG-238
    class BackwardsClock:
        def __init__(self):
            self._t = 100.0
        def now(self):
            from datetime import datetime, UTC
            return datetime.now(UTC)
        def monotonic(self):
            self._t -= 1  # goes backwards each call
            return self._t
    rl238 = RateLimiter(5, capacity=5, clock=BackwardsClock())
    before238 = rl238.available
    rl238._refill()
    after238 = rl238.available
    R("CFG-238", after238 == before238, f"before={before238}, after backwards-clock refill={after238}")

    # CFG-239
    w239 = DedicatedThread(name="w239")
    ids = []
    for _ in range(20):
        ids.append(await w239.call(threading.get_ident))
    caller_id = threading.get_ident()
    R("CFG-239", len(set(ids)) == 1 and ids[0] != caller_id, f"unique thread ids seen={set(ids)}, caller={caller_id}")
    await w239.close()

    # CFG-240
    w240 = DedicatedThread(name="w240")
    def fn240(account=None):
        return account
    got240 = await w240.call(fn240, account="x")
    R("CFG-240", got240 == "x", repr(got240))
    await w240.close()

    # CFG-241
    w241 = DedicatedThread(name="w241")
    recorded = {}
    def teardown241():
        recorded["id"] = threading.get_ident()
    worker_id = await w241.call(threading.get_ident)
    await w241.close(teardown=teardown241)
    R("CFG-241", recorded.get("id") == worker_id, f"teardown ran on {recorded.get('id')}, worker thread was {worker_id}")

    # CFG-242
    w242 = DedicatedThread(name="w242")
    await w242.close()
    calls = []
    await w242.close(teardown=lambda: calls.append(1))
    R("CFG-242", calls == [], f"teardown call count on already-closed worker={len(calls)}")

    # CFG-243
    w243 = DedicatedThread(name="w243")
    await w243.close()
    try:
        await w243.call(lambda: None)
        R("CFG-243", False, "no exception on closed worker")
    except PramaError as e:
        R("CFG-243", e.code == "CONCURRENCY.WORKER_CLOSED" and "cannot be reopened" in e.remedy, f"{e.code}: {e.remedy}")

    # CFG-244
    w244 = DedicatedThread(name="jdbc")
    names = []
    def get_name():
        return threading.current_thread().name
    names.append(await w244.call(get_name))
    await w244.close()
    R("CFG-244", "jdbc" in names[0], repr(names[0]))

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

asyncio.run(main())
