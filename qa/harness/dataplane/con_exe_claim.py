import sys, asyncio, logging, io
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.claim import (
    WorkUnit, Claim, FencedWriter, WorkQueue, claim_unit, release_claim, StaleWriteError,
)
from prama.core.concurrency.leases import MemoryLeaseProvider, LeaseSettings, LeaseHolder
from prama.core.errors import LeaseLostError

def unit(resource="r1"):
    return WorkUnit(resource=resource, dataset="d")

async def exe030():
    provider = MemoryLeaseProvider()
    u = unit()
    results = await asyncio.gather(*(claim_unit(provider, u, worker_id=f"w{i}") for i in range(10)))
    non_none = [r for r in results if r is not None]
    ok = len(non_none) == 1 and sum(1 for r in results if r is None) == 9
    log("EXE-030", "PASS" if ok else "FAIL", f"non_none={len(non_none)} none={sum(1 for r in results if r is None)}")

async def exe031():
    provider = MemoryLeaseProvider()
    u = unit()
    c1 = await claim_unit(provider, u, worker_id="w1")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger("prama.execute.claim").addHandler(handler)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.WARNING)
    c2 = await claim_unit(provider, u, worker_id="w2")
    ok = c2 is None and stream.getvalue() == ""
    log("EXE-031", "PASS" if ok else "FAIL", f"c2={c2} logged_at_warning_or_above={stream.getvalue()!r}")

async def exe032():
    obs = {}
    for t in (0.5, 1.0, 1.5, 3.0, 60.0):
        provider = MemoryLeaseProvider()
        u = unit(f"r-{t}")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        lg = logging.getLogger("prama.core.concurrency.leases")
        lg.addHandler(handler); lg.setLevel(logging.WARNING)
        try:
            claim = await claim_unit(provider, u, worker_id="w", ttl_seconds=t)
            obs[t] = ("OK", stream.getvalue())
            if claim:
                await release_claim(claim)
        except ValueError as e:
            obs[t] = ("ValueError", str(e))
        lg.removeHandler(handler)
    ok = (obs[0.5][0] == "ValueError" and obs[1.0][0] == "ValueError"
          and obs[1.5][0] == "OK" and "renew_interval" in obs[1.5][1]
          and obs[3.0][0] == "OK" and obs[3.0][1] == ""
          and obs[60.0][0] == "OK" and obs[60.0][1] == "")
    log("EXE-032", "PASS" if ok else "FAIL", str(obs))

async def exe033():
    provider = MemoryLeaseProvider()
    u = unit()
    tokens = []
    for _ in range(5):
        c = await claim_unit(provider, u, worker_id="w")
        tokens.append(c.fencing_token)
        await release_claim(c)
    ok = tokens == sorted(tokens) and len(set(tokens)) == 5
    log("EXE-033", "PASS" if ok else "FAIL", f"tokens={tokens}")

def exe034():
    w = FencedWriter()
    c7 = Claim(unit=unit(), worker_id="w1", fencing_token=7)
    w.accept(c7)
    c6 = Claim(unit=unit(), worker_id="w2", fencing_token=6)
    try:
        w.accept(c6)
        log("EXE-034", "FAIL", "no exception")
    except StaleWriteError as e:
        ok = e.code == "CONCURRENCY.STALE_WRITE" and "7" in str(e) and "6" in str(e) and "w2" in str(e) and "Discard the result" in (e.remedy or "")
        log("EXE-034", "PASS" if ok else "FAIL", f"code={e.code} msg={e} remedy={e.remedy}")

def exe035():
    w = FencedWriter()
    c7 = Claim(unit=unit(), worker_id="w1", fencing_token=7)
    w.accept(c7)
    try:
        w.accept(c7)
        log("EXE-035", "PASS", "second accept() of the same token 7 succeeded (comparison is <, not <=; permits a legitimate retry by the current holder, and equally a duplicated record)")
    except StaleWriteError as e:
        log("EXE-035", "FAIL", f"raised: {e}")

def exe036():
    w = FencedWriter()
    h0 = w.highest("r1")
    c0 = Claim(unit=unit(), worker_id="w1", fencing_token=0)
    try:
        w.accept(c0)
        ok = h0 == 0
        log("EXE-036", "PASS" if ok else "FAIL", f"highest_before={h0} accept(token=0)=accepted")
    except StaleWriteError as e:
        log("EXE-036", "FAIL", f"highest_before={h0}, raised: {e}")

def exe037():
    w = FencedWriter()
    c7 = Claim(unit=unit(), worker_id="w1", fencing_token=7)
    w.accept(c7)
    obs = {}
    for t in (6, 7, 8):
        claim = Claim(unit=unit(), worker_id="w", fencing_token=t)
        predicted = w.would_accept(claim)
        try:
            w2 = FencedWriter()
            w2._highest["r1"] = 7
            w2.accept(claim)
            actual = True
        except StaleWriteError:
            actual = False
        obs[t] = (predicted, actual)
    ok = all(p == a for p, a in obs.values()) and obs[6] == (False, False) and obs[7] == (True, True) and obs[8] == (True, True)
    log("EXE-037", "PASS" if ok else "FAIL", str(obs))

def exe038():
    class FakeLostHolder:
        def raise_if_lost(self):
            raise LeaseLostError("lease lost", remedy="x")
    c = Claim(unit=unit(), worker_id="w", fencing_token=1, holder=FakeLostHolder())
    try:
        c.check()
        log("EXE-038", "FAIL", "no exception")
    except LeaseLostError as e:
        log("EXE-038", "PASS", f"LeaseLostError: {e}")

def exe039():
    c = Claim(unit=unit(), worker_id="w", fencing_token=1, holder=None)
    r = c.check()
    ok = r is None
    log("EXE-039", "PASS" if ok else "FAIL", f"check()={r}")

def exe046():
    q = WorkQueue()
    u = unit()
    c7 = Claim(unit=u, worker_id="w1", fencing_token=7)
    q.take(u, c7)
    c8 = Claim(unit=u, worker_id="w2", fencing_token=8)
    q.take(u, c8)  # re-claim
    q.release(c7)  # release the SUPERSEDED (stale) claim
    current = q._claimed.get(u.resource)
    ok = current is not None and current.fencing_token == 8
    log("EXE-046", "PASS" if ok else "FAIL", f"current_claim_after_releasing_stale_token7={current}")

def exe047():
    q = WorkQueue()
    u = unit()
    q.offer(u)
    c = Claim(unit=u, worker_id="w", fencing_token=1)
    q.take(u, c)
    q.release(c, requeue=False)
    absent = u not in q.pending()
    q2 = WorkQueue()
    q2.offer(u)
    c2 = Claim(unit=u, worker_id="w", fencing_token=1)
    q2.take(u, c2)
    q2.release(c2, requeue=True)
    present = u in q2.pending()
    ok = absent and present
    log("EXE-047", "PASS" if ok else "FAIL", f"requeue=False -> absent={absent}; requeue=True -> present={present}")

def exe048():
    q = WorkQueue()
    u = unit()
    q.offer(u)
    lengths = []
    for i in range(3):
        c = Claim(unit=u, worker_id="w", fencing_token=i + 1)
        q.take(u, c)
        q.release(c, requeue=True)
        lengths.append(len(q))
    ok = lengths == [1, 1, 1]
    log("EXE-048", "PASS" if ok else "FAIL", f"lengths={lengths}")

async def main():
    await exe030()
    await exe031()
    await exe032()
    await exe033()
    exe034()
    exe035()
    exe036()
    exe037()
    exe038()
    exe039()
    exe046()
    exe047()
    exe048()

asyncio.run(main())
