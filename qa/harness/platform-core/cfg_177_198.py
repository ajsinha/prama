import sys, os, asyncio, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.concurrency.bounded_queue import BoundedQueue, default_sizer, ITEM_OVERHEAD_BYTES, QueueStats
from prama.core.errors import BackPressureError

async def main():
    # CFG-177
    for bad in (0, -1):
        try:
            BoundedQueue(max_bytes=bad)
            R("CFG-177", False, f"no exception for max_bytes={bad}")
        except ValueError as e:
            R("CFG-177", "unbounded" in str(e), str(e))

    # CFG-178
    q178 = BoundedQueue(max_bytes=3000, max_items=0, offer_timeout=0.2, name="q178")
    big = b"x" * 900
    for i in range(3):
        await q178.put(big)
    try:
        await q178.put(big)
        R("CFG-178", False, "4th item accepted, expected BackPressureError")
    except BackPressureError as e:
        R("CFG-178", True, str(e)[:150])

    # CFG-179
    q179 = BoundedQueue(max_bytes=10_000_000, max_items=2, offer_timeout=0.2, name="q179")
    await q179.put(b"a")
    await q179.put(b"b")
    try:
        await q179.put(b"c")
        R("CFG-179", False, "3rd tiny item accepted despite max_items=2")
    except BackPressureError as e:
        R("CFG-179", True, str(e)[:150])

    # CFG-180
    q180 = BoundedQueue(max_bytes=1024, name="q180")
    huge = b"x" * 4096
    await q180.put(huge)
    R("CFG-180", q180.stats().bytes > 1024, f"stats().bytes={q180.stats().bytes} > max_bytes=1024")

    # CFG-181
    q181 = BoundedQueue(max_bytes=1024, offer_timeout=0.2, name="q181")
    await q181.put(b"small")
    try:
        await q181.put(b"x" * 4096)
        R("CFG-181", False, "oversized item accepted into non-empty queue")
    except BackPressureError:
        R("CFG-181", True, "refused as expected")

    # CFG-182
    q182 = BoundedQueue(max_bytes=100, offer_timeout=0.1, name="q182")
    await q182.put(b"x" * 50)
    try:
        await q182.put(b"x" * 80)
        R("CFG-182", False, "no BackPressureError")
    except BackPressureError as e:
        ctx_ok = all(k in e.context for k in ("queue", "bytes", "max_bytes", "items"))
        remedy_ok = "postpones the same problem" in e.remedy
        R("CFG-182", ctx_ok and remedy_ok, f"context={e.context}; remedy_ok={remedy_ok}")

    # CFG-183
    q183 = BoundedQueue(max_bytes=100, offer_timeout=3.0, name="q183")
    await q183.put(b"x" * 90)
    async def producer():
        t0 = time.monotonic()
        await q183.put(b"x" * 50, timeout=3.0)
        return time.monotonic() - t0
    task = asyncio.create_task(producer())
    await asyncio.sleep(0.1)
    got = await q183.get()
    dt = await asyncio.wait_for(task, timeout=2.0)
    R("CFG-183", dt < 1.0, f"producer completed after {dt:.3f}s (well inside 3s timeout)")

    # CFG-184
    q184 = BoundedQueue(max_bytes=1000, name="q184")
    async def consumer184():
        return await q184.get(timeout=None)
    ctask = asyncio.create_task(consumer184())
    await asyncio.sleep(0.05)
    ok = await q184.try_put("item184")
    got184 = await asyncio.wait_for(ctask, timeout=2.0)
    R("CFG-184", ok and got184 == "item184", f"try_put={ok}, consumer received {got184!r}")

    # CFG-185
    q185 = BoundedQueue(max_bytes=1000, name="q185")
    async def drainer():
        return await q185.drain()
    dtask = asyncio.create_task(drainer())
    await asyncio.sleep(0.05)
    await q185.try_put("item185")
    drained = await asyncio.wait_for(dtask, timeout=2.0)
    R("CFG-185", drained == ["item185"], f"drain() returned {drained}")

    # CFG-186
    q186 = BoundedQueue(max_bytes=100, name="q186")
    await q186.put(b"x" * 90)
    before = q186.stats()
    ok186 = await q186.try_put(b"x" * 90)
    after = q186.stats()
    R("CFG-186", ok186 is False and after.rejected == before.rejected + 1 and after.offered == before.offered + 1,
      f"try_put={ok186}, rejected {before.rejected}->{after.rejected}, offered {before.offered}->{after.offered}")

    # CFG-187
    q187 = BoundedQueue(max_bytes=100, offer_timeout=5.0, name="q187")
    await q187.put(b"x" * 90)
    async def producer187(n):
        t0 = time.monotonic()
        await q187.put(f"item{n}".encode() * 5, timeout=5.0)
        return time.monotonic() - t0
    tasks187 = [asyncio.create_task(producer187(i)) for i in range(3)]
    await asyncio.sleep(0.1)
    await q187.resize(max_bytes=10_000)
    dts = await asyncio.gather(*tasks187)
    R("CFG-187", all(dt < 1.0 for dt in dts), f"producer completion times={[round(d,3) for d in dts]}")

    # CFG-188
    q188 = BoundedQueue(max_bytes=10_000, name="q188")
    for i in range(4):
        await q188.put(f"i{i}")
    await q188.resize(max_bytes=1)
    still4 = len(q188) == 4
    try:
        await q188.put("i5", timeout=0.1)
        newput_ok = False
    except BackPressureError:
        newput_ok = True
    R("CFG-188", still4 and newput_ok, f"len after shrink={len(q188)}, new put refused={newput_ok}")

    # CFG-189
    q189 = BoundedQueue(max_bytes=5000, name="q189")
    try:
        await q189.resize(max_bytes=0)
        R("CFG-189", False, "no exception")
    except ValueError:
        R("CFG-189", q189._max_bytes == 5000, f"refused; budget unchanged={q189._max_bytes}")

    # CFG-190: one producer parked on full, one consumer parked on empty --
    # need two independent queues since one queue can't be both full and empty.
    qP = BoundedQueue(max_bytes=100, offer_timeout=3.0, name="qP")
    await qP.put(b"x" * 90)  # fills it
    qC = BoundedQueue(max_bytes=100, offer_timeout=3.0, name="qC")  # stays empty

    async def prod190():
        try:
            await qP.put(b"x" * 90, timeout=3.0)
            return "no-error"
        except BackPressureError as e:
            return str(e)

    async def cons190():
        try:
            await qC.get(timeout=3.0)
            return "no-error"
        except BackPressureError as e:
            return str(e)

    pt = asyncio.create_task(prod190())
    ct = asyncio.create_task(cons190())
    await asyncio.sleep(0.1)
    t0 = time.monotonic()
    await qP.close()
    await qC.close()
    presult = await asyncio.wait_for(pt, timeout=2.0)
    cresult = await asyncio.wait_for(ct, timeout=2.0)
    dt190 = time.monotonic() - t0
    R("CFG-190", "closed" in presult and "is closed" in presult and "closed and drained" in cresult and dt190 < 1.0,
      f"producer raised: {presult!r}; consumer raised: {cresult!r}; both resolved in {dt190:.3f}s")

    # CFG-191
    q191 = BoundedQueue(max_bytes=10_000, name="q191")
    await q191.put("i1")
    await q191.put("i2")
    await q191.close()
    g1 = await q191.get(timeout=1.0)
    g2 = await q191.get(timeout=1.0)
    try:
        await q191.get(timeout=1.0)
        R("CFG-191", False, "third get() did not raise after close+drain")
    except BackPressureError as e:
        R("CFG-191", g1 == "i1" and g2 == "i2" and "closed and drained" in str(e), f"g1={g1!r} g2={g2!r} then: {e}")

    # CFG-192
    q192 = BoundedQueue(max_bytes=100_000, name="q192")
    for i in range(10):
        await q192.put(f"i{i}")
    before_bytes = q192.byte_size
    taken = await q192.drain(max_items=3)
    R("CFG-192", len(taken) == 3 and q192.byte_size == before_bytes - sum(default_sizer(t) for t in taken),
      f"took {len(taken)} items; byte_size {before_bytes}->{q192.byte_size}")

    # CFG-193
    q193 = BoundedQueue(max_bytes=10_000_000, name="q193")
    for i in range(1000):
        await q193.put(i)
    all_items = await q193.drain()
    R("CFG-193", len(all_items) == 1000 and q193.byte_size == 0, f"drained {len(all_items)}; byte_size={q193.byte_size}")

    # CFG-194
    s_empty_tuple = default_sizer(())
    s_small_dict = default_sizer({"a": 1})
    s_1mb = default_sizer(b"x" * (1024 * 1024))
    R("CFG-194", s_empty_tuple >= ITEM_OVERHEAD_BYTES and s_small_dict >= ITEM_OVERHEAD_BYTES and s_1mb >= 1024*1024,
      f"empty-tuple={s_empty_tuple}, small-dict={s_small_dict}, 1mb-bytes={s_1mb}, OVERHEAD={ITEM_OVERHEAD_BYTES}")

    # CFG-195
    class NoSizeof:
        def __sizeof__(self):
            raise TypeError("cannot measure")
    s195 = default_sizer(NoSizeof())
    R("CFG-195", s195 == ITEM_OVERHEAD_BYTES, f"default_sizer(NoSizeof())={s195}")

    # CFG-196
    q196 = BoundedQueue(max_bytes=1024, name="q196")
    await q196.put(b"x" * 4096)
    util = q196.stats().utilisation
    R("CFG-196", util == 1.0, repr(util))

    # CFG-197
    q197 = BoundedQueue(max_bytes=100_000, name="q197")
    for i in range(5):
        await q197.put(b"x" * 1000)
    peak_items = q197.stats().high_water_items
    peak_bytes = q197.stats().high_water_bytes
    await q197.drain()
    after_items = q197.stats().high_water_items
    after_bytes = q197.stats().high_water_bytes
    R("CFG-197", after_items == peak_items == 5 and after_bytes == peak_bytes,
      f"peak items={peak_items} bytes={peak_bytes}; after drain items={after_items} bytes={after_bytes}")

    # CFG-198
    q198 = BoundedQueue(max_bytes=100_000, name="q198")
    await q198.put("x")
    snap = q198.stats()
    snap_items_before = snap.items
    await q198.drain()
    R("CFG-198", snap.items == snap_items_before and snap.items == 1, f"snapshot.items after later drain={snap.items} (should stay 1)")

asyncio.run(main())
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
