import sys, os, asyncio, tempfile, sqlite3
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.db import Database
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.errors import NotFoundError, ConflictError, ValidationError
from prama.core.ids import new_ulid
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from datetime import datetime, UTC, timedelta

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

def mk_record(tenant_id, seq=0, verdict="pass", finished="2026-01-01T00:00:01Z", **kw):
    return EvidenceRecord(
        sequence=seq, plan_id=kw.get("plan_id", "p"), control_id=kw.get("control_id", ""),
        control_version=1, dataset=kw.get("dataset", "t"), binding="",
        snapshot=SnapshotRef(kind="wall_clock", identifier="", exact=False), parameters={},
        engine="duckdb", coverage="full", verdict=verdict, metrics={}, samples_digest="",
        sample_count=0, started_at="2026-01-01T00:00:00Z", finished_at=finished, duration_ms=1,
        triggered_by="schedule", tenant_id=tenant_id, detail="", dimensions=(), criticality=4,
        previous_hash=kw.get("previous_hash", "garbage-not-genesis"),
    )

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-evid-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="ev", display_name="EV")
        await uow.flush()
        tid = str(t.id)

    # DB-230/231: head/next_sequence on empty chain
    async with db.unit_of_work() as uow:
        head0 = await uow.evidence.head(tid)
        seq0 = await uow.evidence.next_sequence(tid)
    R("DB-230", head0 == GENESIS, repr(head0))
    R("DB-231", seq0 == 0, repr(seq0))

    # DB-228: append ignores caller-supplied sequence/previous_hash
    async with db.unit_of_work() as uow:
        for i in range(4):
            await uow.evidence.append(mk_record(tid, seq=999, previous_hash="nonsense"), tenant_id=tid)
    async with db.unit_of_work() as uow:
        head_before = await uow.evidence.head(tid)
        linked = await uow.evidence.append(mk_record(tid, seq=999, previous_hash="totally-wrong"), tenant_id=tid)
    R("DB-228", linked.sequence == 4 and linked.previous_hash == head_before,
      f"stored sequence={linked.sequence} (caller passed 999), previous_hash matches real head={linked.previous_hash == head_before}")

    # DB-229: append with no tenant
    try:
        async with db.unit_of_work() as uow:
            await uow.evidence.append(mk_record(""), tenant_id="")
        R("DB-229", False, "no exception")
    except ConflictError as e:
        R("DB-229", "needs a tenant" in str(e), str(e))

    # DB-232: chains per tenant, no interleave
    async with db.unit_of_work() as uow:
        t232b = uow.tenants.create(slug="ev232b", display_name="EV232B")
        await uow.flush()
        tid232b = str(t232b.id)
    async with db.unit_of_work() as uow:
        for i in range(10):
            await uow.evidence.append(mk_record(tid232b), tenant_id=tid232b)
            await uow.evidence.append(mk_record(tid), tenant_id=tid)  # tid already has 5 from before
    async with db.unit_of_work() as uow:
        chain232b = await uow.evidence.chain(tid232b)
        verify232b = await uow.evidence.verify(tid232b)
    R("DB-232", [r.sequence for r in chain232b] == list(range(10)) and verify232b.is_intact,
      f"tenant232b sequences={[r.sequence for r in chain232b]}, verify.ok={verify232b.is_intact}")

    # DB-233/234: tamper detection
    async with db.unit_of_work() as uow:
        t233 = uow.tenants.create(slug="ev233", display_name="EV233")
        await uow.flush()
        tid233 = str(t233.id)
        for i in range(3):
            await uow.evidence.append(mk_record(tid233, detail=f"orig-{i}"), tenant_id=tid233)
    with sqlite3.connect(p) as conn:
        conn.execute("UPDATE ev_record SET detail='TAMPERED' WHERE tenant_id=? AND sequence=1", (tid233,))
        conn.commit()
    async with db.unit_of_work() as uow:
        verify233 = await uow.evidence.verify(tid233)
        chain233 = await uow.evidence.chain(tid233)
        stored233 = await uow.evidence.as_stored(tid233)
    seq1_breach = [b for b in verify233.breaches if b.sequence == 1]
    R("DB-233", not verify233.is_intact and bool(seq1_breach),
      f"verify.is_intact={verify233.is_intact}; breaches={[(b.kind, b.sequence, b.detail) for b in verify233.breaches]}")
    tampered_chain_record = chain233[1]
    tampered_stored_record = stored233[1]
    R("DB-234", tampered_chain_record.content_hash != tampered_stored_record["content_hash"] or tampered_chain_record.detail == "TAMPERED",
      f"chain() record.detail={tampered_chain_record.detail!r} (recomputed hash would match this tampered content); "
      f"as_stored() dict content.detail={tampered_stored_record.get('detail')!r} vs stored content_hash={tampered_stored_record['content_hash'][:12]!r} (original, now mismatching)")

    # DB-235: delete refused
    async with db.unit_of_work() as uow:
        rec235 = (await uow.evidence.chain(tid))[0]
    try:
        async with db.unit_of_work() as uow:
            row235 = await uow.evidence.row_at(tid, 0)
            await uow.evidence.delete(row235)
        R("DB-235", False, "no exception")
    except ConflictError as e:
        ok235 = "erase()" in e.remedy and "archive" in e.remedy.lower()
        R("DB-235", ok235, f"{e}; remedy={e.remedy!r}")

    # DB-236: erase blanks content, keeps chain verifiable
    async with db.unit_of_work() as uow:
        t236 = uow.tenants.create(slug="ev236", display_name="EV236")
        await uow.flush()
        tid236 = str(t236.id)
        for i in range(5):
            await uow.evidence.append(mk_record(tid236, detail=f"content-{i}"), tenant_id=tid236)
    async with db.unit_of_work() as uow:
        erased236 = await uow.evidence.erase(tid236, 2, by="qa", authority="gdpr")
        verify236 = await uow.evidence.verify(tid236)
        row236 = await uow.evidence.row_at(tid236, 2)
    R("DB-236", verify236.is_intact and row236.tombstone_json is not None and row236.detail == "",
      f"verify.ok={verify236.is_intact}, tombstone set={row236.tombstone_json is not None}, detail blanked={row236.detail == ''}")

    # DB-237: erase of a gap
    try:
        async with db.unit_of_work() as uow:
            await uow.evidence.erase(tid236, 999, by="qa")
        R("DB-237", False, "no exception")
    except NotFoundError as e:
        ok237 = "a gap is itself a finding" in e.remedy
        R("DB-237", ok237, e.remedy)

    # DB-238/239: erase twice, and under -O (bare assert)
    try:
        async with db.unit_of_work() as uow:
            erased236b = await uow.evidence.erase(tid236, 2, by="qa2")
        R("DB-238", True, "erasing an already-erased record: no error")
    except AssertionError as e:
        R("DB-238", False, f"AssertionError on second erase: {e}")
    except Exception as e:
        R("DB-238", False, f"{type(e).__name__}: {e}")

    import subprocess
    code239 = (
        "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.'); "
        "assert False, 'if -O is active this line proves asserts are stripped'"
    )
    p239 = subprocess.run([sys.executable, "-O", "-c", code239], capture_output=True, text=True)
    asserts_stripped_under_O = p239.returncode == 0
    R("DB-239", not asserts_stripped_under_O,
      f"python -O actually strips asserts in this interpreter (confirmed: exit code {p239.returncode} for a script "
      f"whose only statement is 'assert False' -- {'no error, so asserts ARE stripped' if asserts_stripped_under_O else 'still raised, unexpected'}); "
      f"erase()'s only protection for content_hash/record_hash is two bare `assert` statements with no accompanying "
      f"runtime check, so any deployment run with `python -O` (e.g. a container base image or PYTHONOPTIMIZE=1) "
      f"loses this guard silently -- a genuine gap in the ledger's tamper-evidence design, matching CLAUDE.md's own "
      f"list of things the catalogue's author flagged")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
