import sys, os, asyncio, tempfile
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
from datetime import datetime, UTC, timedelta
from prama.report.attestation import Attestation, Coverage

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

def mk_att(tenant_id, scope="s1", signed_at="2026-01-01T00:00:00Z", **kw):
    return Attestation(
        attester_id=kw.get("attester_id", "p1"), attester_name="Alice", statement="I attest",
        scope=scope, period_start="2026-01-01T00:00:00Z", period_end="2026-01-31T00:00:00Z",
        coverage=Coverage(controls_in_scope=10, controls_run=10, passed=9, failed=1, not_established=0, errored=0, never_ran=0),
        evidence_root="r"*64, evidence_records=10, signed_at=signed_at, tenant_id=tenant_id,
        supersedes=kw.get("supersedes", ""), supersedes_because=kw.get("supersedes_because", ""),
    )

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-att-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="at", display_name="AT")
        await uow.flush()
        tid = str(t.id)

    key = b"a"*32

    # DB-256: delete refused
    async with db.unit_of_work() as uow:
        row256 = await uow.attestations.sign(mk_att(tid), seal="s"*64)
    try:
        async with db.unit_of_work() as uow:
            r = await uow.attestations.get(str(row256.id))
            await uow.attestations.delete(r)
        R("DB-256", False, "no exception")
    except ConflictError as e:
        ok256 = "supersede" in e.remedy.lower()
        R("DB-256", ok256, f"{e}; remedy={e.remedy!r}")

    # DB-257: sign writes supersession on both rows
    async with db.unit_of_work() as uow:
        original257 = await uow.attestations.sign(mk_att(tid, scope="s257"), seal="seal1")
    async with db.unit_of_work() as uow:
        replacement257 = await uow.attestations.sign(
            mk_att(tid, scope="s257", supersedes=str(original257.id), supersedes_because="correction"),
            seal="seal2", supersedes=str(original257.id))
    async with db.unit_of_work() as uow:
        orig_after = await uow.attestations.get(str(original257.id))
    R("DB-257", replacement257.supersedes == str(original257.id) and orig_after.superseded_by == str(replacement257.id),
      f"replacement.supersedes={replacement257.supersedes}, original.superseded_by={orig_after.superseded_by}")

    # DB-258: superseding a non-existent id
    try:
        async with db.unit_of_work() as uow:
            await uow.attestations.sign(mk_att(tid, scope="s258"), seal="s3", supersedes=new_ulid())
        R("DB-258", False, "no exception")
    except NotFoundError as e:
        R("DB-258", True, f"raised as expected: {e}")
    # check the new row did NOT persist (across a fresh unit of work, since the exception's
    # own uow was rolled back on exit)
    async with db.unit_of_work() as uow:
        from sqlalchemy import select, func
        from prama.db.models.attestation import AttAttestation
        count258 = (await uow._session.execute(
            select(func.count()).select_from(AttAttestation).where(AttAttestation.scope == "s258")
        )).scalar_one()
    R("DB-258-persist", count258 == 0, f"rows with scope=s258 after the rolled-back sign(): {count258}")

    # DB-259: current excludes superseded
    async with db.unit_of_work() as uow:
        current259 = await uow.attestations.current(tid)
    scopes_current = {a.scope for a in current259}
    R("DB-259", "s257" in scopes_current, f"current scopes={scopes_current}")
    orig_in_current = any(a.id == original257.id for a in current259)
    R("DB-259b", not orig_in_current, f"superseded original present in current()={orig_in_current}")

    # DB-260: history includes superseded, oldest first
    async with db.unit_of_work() as uow:
        hist260 = await uow.attestations.history(tid, "s257")
    R("DB-260", len(hist260) == 2 and hist260[0].id == original257.id and hist260[1].id == replacement257.id,
      f"history ids in order={[h.id for h in hist260]}")

    # DB-261: in_tenant cross-tenant reports absent
    async with db.unit_of_work() as uow:
        t261 = uow.tenants.create(slug="at261", display_name="AT261")
        await uow.flush()
        tid261 = str(t261.id)
    try:
        async with db.unit_of_work() as uow:
            await uow.attestations.in_tenant(str(original257.id), tid261)
        R("DB-261", False, "no exception")
    except NotFoundError:
        R("DB-261", True, "reported as not found for the wrong tenant")

    # DB-262: verify distinguishes tampering from foreign key
    att262 = mk_att(tid, scope="s262a")
    seal262 = att262.seal(key)
    async with db.unit_of_work() as uow:
        stored262 = await uow.attestations.sign(att262, seal=seal262)
    async with db.unit_of_work() as uow:
        intact_correct, sealed_correct = await uow.attestations.verify(str(stored262.id), key)
        other_key = b"b"*32
        intact_wrongkey, sealed_wrongkey = await uow.attestations.verify(str(stored262.id), other_key)
    # tamper via a raw sqlite3 connection, bypassing the ORM session entirely, so a
    # later, genuinely fresh unit of work (no stale identity-map object) reads it back
    import sqlite3 as _sqlite3_262
    with _sqlite3_262.connect(p) as _raw_conn:
        _raw_conn.execute("UPDATE att_attestation SET statement='TAMPERED' WHERE id=?", (str(stored262.id),))
        _raw_conn.commit()
    async with db.unit_of_work() as uow:
        intact_tampered, sealed_tampered = await uow.attestations.verify(str(stored262.id), key)
    R("DB-262", (intact_correct, sealed_correct) == (True, True) and (intact_wrongkey, sealed_wrongkey) == (True, False)
      and (intact_tampered, sealed_tampered) == (False, False),
      f"correct=({intact_correct},{sealed_correct}), wrongkey=({intact_wrongkey},{sealed_wrongkey}), tampered=({intact_tampered},{sealed_tampered})")

    # DB-263: unsealed row
    async with db.unit_of_work() as uow:
        att263 = mk_att(tid, scope="s263")
        stored263 = await uow.attestations.sign(att263, seal="")
        intact263, sealed263 = await uow.attestations.verify(str(stored263.id), key)
    R("DB-263", intact263 is True and sealed263 is False, f"intact={intact263}, sealed={sealed263}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
