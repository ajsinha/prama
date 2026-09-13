import sys, asyncio, time
sys.path.insert(0, ".")
from qa_common import log
from prama.core.concurrency.bounded_queue import BoundedQueue, default_sizer, ITEM_OVERHEAD_BYTES
from prama.core.errors import BackPressureError

def exe055():
    obs = {}
    for mb in (0, -1):
        try:
            BoundedQueue(max_bytes=mb)
            obs[mb] = "NO ERROR"
        except ValueError as e:
            obs[mb] = str(e)
    ok = all("unbounded queue is not permitted" in v for v in obs.values())
    log("EXE-055", "PASS" if ok else "FAIL", str(obs))

async def exe056():
    q = BoundedQueue(max_bytes=10_000, max_items=3, offer_timeout=0.05)
    for i in range(3):
        await q.put(f"x{i}")
    try:
        await q.put("x3")
        ok1 = False
        detail1 = "no error"
    except BackPressureError as e:
        ok1 = "3 items" in str(e) or "items" in str(e)
        detail1 = str(e)

    q2 = BoundedQueue(max_bytes=10_000, max_items=100, offer_timeout=0.05)
    big = "x" * 9000
    await q2.put(big)
    try:
        await q2.put("y" * 900)
        ok2 = False
        detail2 = "no error"
    except BackPressureError as e:
        ok2 = True
        detail2 = str(e)
    ok = ok1 and ok2
    log("EXE-056", "PASS" if ok else "FAIL", f"item_guard: {detail1}; byte_guard: {detail2}")

async def exe057():
    q = BoundedQueue(max_bytes=100, offer_timeout=0.05)
    big = "x" * 10_000
    await q.put(big)  # accepted onto empty queue despite exceeding max_bytes
    try:
        await q.put("y")
        log("EXE-057", "FAIL", "second put succeeded, should have blocked and raised")
    except BackPressureError as e:
        log("EXE-057", "PASS", f"first oversized item accepted (len={len(q)}, byte_size={q.byte_size}); second put(): {e}")

async def exe058():
    q = BoundedQueue(max_bytes=100, max_items=1, offer_timeout=0.05)
    await q.put("a")
    r = q._would_fit(q._sizer("b" * 10_000))
    ok = r is False
    log("EXE-058", "PASS" if ok else "FAIL", f"_would_fit(oversized) on a 1-item-full queue = {r}")

async def exe059():
    q = BoundedQueue(max_bytes=100, offer_timeout=0.05, name="myq")
    await q.put("x" * 90)
    start = time.monotonic()
    try:
        await q.put("y" * 90)
        log("EXE-059", "FAIL", "no exception")
    except BackPressureError as e:
        elapsed = time.monotonic() - start
        ok = (0.03 < elapsed < 2.0 and "bytes" in str(e) and "items" in str(e)
              and set(e.context) >= {"queue", "bytes", "max_bytes", "items"}
              and "more memory" in (e.remedy or "") and q.stats().rejected == 1)
        log("EXE-059", "PASS" if ok else "FAIL", f"elapsed={elapsed:.3f}s msg={e} context={e.context} remedy={e.remedy} rejected={q.stats().rejected}")

async def exe060():
    q = BoundedQueue(max_bytes=10_000)
    got = []
    async def consumer():
        item = await q.get()
        got.append(item)
    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)  # let it park in get()
    ok_put = await q.try_put("hello")
    try:
        await asyncio.wait_for(task, timeout=1.0)
        ok = got == ["hello"]
        log("EXE-060", "PASS" if ok else "FAIL", f"consumer received={got} promptly")
    except asyncio.TimeoutError:
        task.cancel()
        log("EXE-060", "FAIL", "consumer did not wake up within 1s after try_put")

async def exe061():
    q = BoundedQueue(max_bytes=100, offer_timeout=30.0)
    await q.put("x" * 90)  # fill it
    results = []
    async def producer(name):
        started = time.monotonic()
        await q.put("y" * 10, timeout=30.0)
        results.append((name, time.monotonic() - started))
    t1 = asyncio.create_task(producer("p1"))
    t2 = asyncio.create_task(producer("p2"))
    await asyncio.sleep(0.1)
    await q.resize(max_bytes=10_000)
    try:
        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)
        ok = all(elapsed < 1.0 for _, elapsed in results)
        log("EXE-061", "PASS" if ok else "FAIL", f"producers completed: {results}")
    except asyncio.TimeoutError:
        log("EXE-061", "FAIL", "producers did not complete within 2s of resize()")

async def exe062():
    q = BoundedQueue(max_bytes=100_000)
    item = "x" * 9936  # sizer adds overhead; aim for ~10000 bytes total with one item
    await q.put(item)
    before_bytes = q.byte_size
    await q.resize(max_bytes=1000)
    ok = len(q) == 1 and q.byte_size == before_bytes and q.stats().utilisation == 1.0
    log("EXE-062", "PASS" if ok else "FAIL", f"len={len(q)} byte_size={q.byte_size} (before_resize={before_bytes}) utilisation={q.stats().utilisation}")

async def exe063():
    q = BoundedQueue(max_bytes=1000)
    try:
        await q.resize(max_bytes=0)
        ok1 = False
    except ValueError:
        ok1 = True
    await q.resize(max_items=0)
    ok2 = q._max_items == 0
    log("EXE-063", "PASS" if (ok1 and ok2) else "FAIL", f"resize(max_bytes=0) refused={ok1}; resize(max_items=0) accepted, means no ceiling={ok2}")

async def exe064():
    q = BoundedQueue(max_bytes=100, offer_timeout=30.0)
    await q.put("x" * 90)
    results = {}
    async def producer():
        try:
            await q.put("y" * 90, timeout=30.0)
            results["producer"] = "no error"
        except BackPressureError as e:
            results["producer"] = str(e)
    async def consumer():
        # drain the queue first so get() would otherwise wait
        pass
    q2 = BoundedQueue(max_bytes=1000, offer_timeout=30.0)
    async def consumer2():
        try:
            await q2.get(timeout=30.0)
            results["consumer"] = "no error"
        except BackPressureError as e:
            results["consumer"] = str(e)
    tp = asyncio.create_task(producer())
    tc = asyncio.create_task(consumer2())
    await asyncio.sleep(0.1)
    await q.close()
    await q2.close()
    try:
        await asyncio.wait_for(asyncio.gather(tp, tc), timeout=2.0)
        ok = "closed" in results["producer"] and "closed and drained" in results["consumer"]
        log("EXE-064", "PASS" if ok else "FAIL", str(results))
    except asyncio.TimeoutError:
        log("EXE-064", "FAIL", f"did not wake within 2s: {results}")

async def exe065():
    q = BoundedQueue(max_bytes=10_000)
    for i in range(3):
        await q.put(f"i{i}")
    await q.close()
    got = []
    for _ in range(3):
        got.append(await q.get())
    fourth_raised = False
    try:
        await q.get(timeout=1.0)
    except BackPressureError:
        fourth_raised = True
    q2 = BoundedQueue(max_bytes=10_000)
    for i in range(3):
        await q2.put(f"j{i}")
    await q2.close()
    d1 = await q2.drain()
    d2 = await q2.drain()
    ok = got == ["i0", "i1", "i2"] and fourth_raised and len(d1) == 3 and d2 == []
    log("EXE-065", "PASS" if ok else "FAIL", f"got={got} 4th_raised={fourth_raised} drain1={d1} drain2={d2}")

async def exe066():
    q = BoundedQueue(max_bytes=10_000)
    try:
        await asyncio.wait_for(q.drain(), timeout=1.0)
        log("EXE-066", "FAIL", "drain() returned within 1s on an empty open queue with no timeout param available")
    except asyncio.TimeoutError:
        log("EXE-066", "PASS", "drain() on an empty open queue waited indefinitely (no timeout parameter exists on drain(), confirmed it blocked past 1s)")

async def exe067():
    q = BoundedQueue(max_bytes=100_000)
    for i in range(10):
        await q.put(f"item{i}")
    before = q.byte_size
    d1 = await q.drain(max_items=3)
    mid = q.byte_size
    d2 = await q.drain(max_items=0)
    after = q.byte_size
    ok = len(d1) == 3 and len(d2) == 7 and after == 0 and (before - mid) > 0 and (mid - after) > 0
    log("EXE-067", "PASS" if ok else "FAIL", f"d1_len={len(d1)} d2_len={len(d2)} byte_size before={before} mid={mid} after={after}")

def exe068():
    obs = {}
    obs["bytes"] = default_sizer(b"")
    obs["str1000"] = default_sizer("x" * 1000)
    obs["dict"] = default_sizer({"a": "x" * 1000})
    obs["list"] = default_sizer([1, 2, 3])
    nested = {"a": {"b": {"c": "x" * 100_000}}}
    obs["nested"] = default_sizer(nested)
    class Raises:
        def __sizeof__(self):
            raise TypeError("no size for you")
    obs["raises"] = default_sizer(Raises())
    ok = (all(v >= ITEM_OVERHEAD_BYTES for v in obs.values())
          and obs["dict"] > 1000
          and obs["nested"] < 100_000  # not walked past one level
          and obs["raises"] == ITEM_OVERHEAD_BYTES)
    log("EXE-068", "PASS" if ok else "FAIL", str(obs))

async def exe069():
    q = BoundedQueue(max_bytes=10_000)
    await q.put("a")
    snap1 = q.stats()
    items_before = snap1.items
    await q.put("b")
    await q.put("c")
    items_after_snap = snap1.items
    ok = items_before == items_after_snap == 1
    snap2 = q.stats()
    ok = ok and snap2.high_water_items >= snap1.high_water_items
    log("EXE-069", "PASS" if ok else "FAIL", f"snap1.items stayed={items_after_snap} (captured at 1); snap2.high_water_items={snap2.high_water_items} >= snap1's {snap1.high_water_items}")

async def main():
    exe055()
    await exe056()
    await exe057()
    await exe058()
    await exe059()
    await exe060()
    await exe061()
    await exe062()
    await exe063()
    await exe064()
    await exe065()
    await exe066()
    await exe067()
    exe068()
    await exe069()

asyncio.run(main())
