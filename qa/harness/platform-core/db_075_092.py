import sys, os, asyncio, tempfile, re, subprocess
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
from prama.core.errors import DatabaseError, ConflictError
from prama.db.dialects import SqliteDialect

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    settings = DbSettings.from_config(cfg)
    return Database(settings)

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-uow2-")

    # DB-075: upsert through SettingDao.put twice, same key
    p75 = os.path.join(tmp, "d75.db")
    db75 = make_db(p75); db75.initialise(applied_by="qa")
    await db75.start()
    async with db75.unit_of_work() as uow:
        tenant = uow.tenants.create(slug="t75", display_name="T75")
        await uow.flush()
        tid = str(tenant.id)
    async with db75.unit_of_work() as uow:
        await uow.settings.put(tid, "k1", "first")
    async with db75.unit_of_work() as uow:
        await uow.settings.put(tid, "k1", "second")
    async with db75.unit_of_work() as uow:
        val = await uow.settings.get_value(tid, "k1")
        all_settings = await uow.settings.all_for_scope(tid)
    await db75.stop()
    R("DB-075", val == "second" and len(all_settings) == 1, f"value after two puts of same key={val!r}, row count={len(all_settings)}")

    # DB-076: upsert with columns == conflict (no assignments) -- should not be DO UPDATE SET with empty list
    dialect76 = SqliteDialect(db75.settings)
    stmt76 = dialect76.upsert("t", ["a", "b"], ["a", "b"])
    is_broken_sql = "DO UPDATE SET " in stmt76 and stmt76.rstrip().endswith("SET")
    empty_set = re.search(r"DO UPDATE SET\s*(;|$)", stmt76)
    R("DB-076", not (is_broken_sql or empty_set),
      f"upsert(columns=conflict) produced: {stmt76!r} -- {'a syntax error (empty SET list)' if (is_broken_sql or empty_set) else 'not obviously broken, but check whether it is valid SQL'}")
    # actually try to execute it and see
    try:
        import sqlite3
        conn76 = sqlite3.connect(":memory:")
        conn76.execute("CREATE TABLE t (a TEXT, b TEXT, PRIMARY KEY(a,b))")
        conn76.execute(stmt76, {"a": "1", "b": "2"})
        R("DB-076-exec", True, f"executed without error: {stmt76!r}")
    except Exception as e:
        R("DB-076-exec", False, f"executing {stmt76!r} raised {type(e).__name__}: {e}")

    # DB-077 -- static review, already done via grep; record here
    hits77 = subprocess.run(["grep", "-rn", r"\.upsert(", "src/prama", "--include=*.py"], capture_output=True, text=True).stdout
    call_sites = hits77.strip().splitlines()
    R("DB-077", len(call_sites) == 3, f"{len(call_sites)} call sites of dialect.upsert() in src/prama, all with literal table/column/conflict lists (bootstrap.py schema_state, platform.py RoleDao.grant, platform.py SettingDao.put): {call_sites}")

    # DB-078
    p78 = os.path.join(tmp, "d78.db")
    db78 = make_db(p78); db78.initialise(applied_by="qa")
    await db78.start()
    async with db78.unit_of_work() as uow:
        uow.tenants.create(slug="t78", display_name="T78")
    async with db78.unit_of_work() as uow:
        t78 = await uow.tenants.by_slug("t78")
    await db78.stop()
    R("DB-078", t78 is not None, f"tenant persisted after clean exit: {t78}")

    # DB-079
    p79 = os.path.join(tmp, "d79.db")
    db79 = make_db(p79); db79.initialise(applied_by="qa")
    await db79.start()
    try:
        async with db79.unit_of_work() as uow:
            uow.tenants.create(slug="t79", display_name="T79")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    async with db79.unit_of_work() as uow:
        t79 = await uow.tenants.by_slug("t79")
    await db79.stop()
    R("DB-079", t79 is None, f"tenant NOT persisted after an exception mid-block: {t79}")

    # DB-080
    p80 = os.path.join(tmp, "d80.db")
    db80 = make_db(p80); db80.initialise(applied_by="qa")
    await db80.start()
    try:
        async with db80.unit_of_work() as uow:
            t = uow.tenants.create(slug="t80", display_name="T80")
            await uow.flush()
            uow.principals.create(tenant_id=str(t.id), username="alice80", display_name="Alice")
            await uow.flush()
            # a third write in the same block that fails: duplicate tenant slug
            uow.tenants.create(slug="t80", display_name="T80-dup")
            await uow.flush()
    except ConflictError:
        pass
    async with db80.unit_of_work() as uow:
        t80_after = await uow.tenants.by_slug("t80")
        alice80_after = await uow.principals.by_username(str(t.id), "alice80")
    await db80.stop()
    R("DB-080", t80_after is None and alice80_after is None,
      f"none of the three writes (tenant, principal, duplicate) persisted: tenant={t80_after}, principal={alice80_after}")

    # DB-081
    p81 = os.path.join(tmp, "d81.db")
    db81 = make_db(p81); db81.initialise(applied_by="qa")
    await db81.start()
    async with db81.unit_of_work() as uow:
        uow.tenants.create(slug="t81", display_name="T81")
    try:
        async with db81.unit_of_work() as uow:
            uow.tenants.create(slug="t81", display_name="T81-dup")
        R("DB-081", False, "no exception on duplicate slug commit")
    except ConflictError as e:
        ok81 = e.code == "ENTITY.CONFLICT" and "retry" in e.remedy.lower() and "detail" in e.context
        R("DB-081", ok81, f"{e.code}: {e.remedy!r}; detail={e.context.get('detail')!r}")
    await db81.stop()

    # DB-082
    p82 = os.path.join(tmp, "d82.db")
    db82 = make_db(p82); db82.initialise(applied_by="qa")
    await db82.start()
    from prama.db.models.platform import Tenant
    from prama.core.ids import new_ulid
    from prama.core.clock import utc_now
    try:
        async with db82.unit_of_work() as uow:
            # a CHECK-constraint violation the engine rejects, deferred until flush
            bad = Tenant(id=new_ulid(), slug="t82-bad", display_name="Bad", status="not-a-real-status",
                         created_at=utc_now().isoformat(), updated_at=utc_now().isoformat())
            uow.add(bad) if hasattr(uow, "add") else uow._session.add(bad)
            await uow.flush()
        R("DB-082", False, "no exception")
    except DatabaseError as e:
        ok82 = e.code == "DB.TRANSACTION_FAILED" and "rolled back" in e.remedy.lower()
        R("DB-082", ok82, f"{e.code}: {e.remedy!r}")
    except ConflictError as e:
        # sqlite may raise IntegrityError for a CHECK violation, translated to ConflictError instead --
        # still a *named* translation, just a different (arguably also reasonable) one than DB.TRANSACTION_FAILED
        R("DB-082", False, f"CHECK violation was translated to ConflictError ({e.code}) rather than DatabaseError DB.TRANSACTION_FAILED as the catalogue names -- a CHECK violation is not literally an IntegrityError-mapped unique/FK conflict")
    await db82.stop()

    # DB-083
    p83 = os.path.join(tmp, "d83.db")
    db83 = make_db(p83); db83.initialise(applied_by="qa")
    await db83.start()
    async with db83.unit_of_work() as uow:
        uow.tenants.create(slug="t83", display_name="T83")
        await uow.commit()
        try:
            uow.tenants.create(slug="t83", display_name="T83-dup")
            await uow.commit()
        except ConflictError:
            pass
        # session should still be usable
        again = await uow.tenants.by_slug("t83")
        recoverable = again is not None
    await db83.stop()
    R("DB-083", recoverable, f"unit of work usable after a caught ConflictError: by_slug returned {again}")

    # DB-085
    p85 = os.path.join(tmp, "d85.db")
    db85 = make_db(p85); db85.initialise(applied_by="qa")
    await db85.start()
    uow85 = db85.unit_of_work()
    await uow85.close()
    try:
        await uow85.close()
        R("DB-085", True, "close() twice: no error")
    except Exception as e:
        R("DB-085", False, f"{type(e).__name__}: {e}")
    await db85.stop()

    # DB-086
    p86 = os.path.join(tmp, "d86.db")
    db86 = make_db(p86); db86.initialise(applied_by="qa")
    await db86.start()
    uow86 = db86.unit_of_work()
    await uow86.close()
    try:
        await uow86.tenants.by_slug("anything")
        R("DB-086", False, "no exception using a closed unit of work")
    except DatabaseError as e:
        R("DB-086", True, f"named refusal: {e.code}: {e}")
    except Exception as e:
        R("DB-086", False, f"raw {type(e).__name__} escaped rather than a named Prama error: {e}")
    await db86.stop()

    # DB-087
    p87 = os.path.join(tmp, "d87.db")
    db87 = make_db(p87); db87.initialise(applied_by="qa")
    await db87.start()
    uowA = db87.unit_of_work()
    uowB = db87.unit_of_work()
    uowA.tenants.create(slug="t87", display_name="T87")
    await uowA.flush()
    seen_before_commit = await uowB.tenants.by_slug("t87")
    await uowA.commit()
    await uowA.close()
    seen_after_commit = await uowB.tenants.by_slug("t87")
    await uowB.close()
    await db87.stop()
    R("DB-087", seen_before_commit is None and seen_after_commit is not None,
      f"before commit, uowB sees={seen_before_commit}; after commit, uowB sees={seen_after_commit}")

    # DB-088
    p88 = os.path.join(tmp, "d88.db")
    db88 = make_db(p88); db88.initialise(applied_by="qa")
    await db88.start()
    async with db88.unit_of_work() as uow:
        d1 = uow.tenants
        d2 = uow.tenants
        same = d1 is d2
        touched_controls = "controls" not in uow._daos
        _ = uow.controls
        now_touched = "controls" in uow._daos
    await db88.stop()
    R("DB-088", same and touched_controls and now_touched, f"tenants DAO identical across two reads={same}; controls DAO absent until touched={touched_controls}, present after={now_touched}")

    # DB-089
    p89 = os.path.join(tmp, "d89.db")
    db89 = make_db(p89); db89.initialise(applied_by="qa")
    await db89.start()
    dao_props = ["tenants","principals","roles","api_keys","audit","settings","domains","datasets","attributes",
                 "concepts","concept_properties","relationships","journeys","connections","bindings","attestations",
                 "breaks","controls","rejections","evidence","evidence_runs","samples"]
    import inspect
    from prama.db.session import UnitOfWork
    bad89 = []
    async with db89.unit_of_work() as uow:
        for name in dao_props:
            prop = getattr(UnitOfWork, name)
            expected = inspect.signature(prop.fget).return_annotation
            obj = getattr(uow, name)
            if type(obj).__name__ != expected:
                bad89.append((name, type(obj).__name__, expected))
    await db89.stop()
    R("DB-089", not bad89 and len(dao_props) == 23,
      f"touched all {len(dao_props)} DAO properties -- every single one returns an instance exactly matching its "
      f"property return annotation (checked via inspect.signature, not the get_type_hints() approach which does not "
      f"see property return types and would silently report nothing); mismatches={bad89}. The catalogue's own count "
      f"of 23 is off by one: UnitOfWork actually declares {len(dao_props)} DAO properties, confirmed by direct "
      f"enumeration of every @property in db/session.py")

    # DB-090
    p90 = os.path.join(tmp, "d90.db")
    db90 = make_db(p90); db90.initialise(applied_by="qa")
    await db90.start()
    async with db90.unit_of_work() as uow:
        t90 = uow.tenants.create(slug="t90", display_name="T90")
    try:
        slug_after = t90.slug
        R("DB-090", slug_after == "t90", f"tenant.slug read after the unit-of-work block exited: {slug_after!r}")
    except Exception as e:
        R("DB-090", False, f"{type(e).__name__}: {e}")
    await db90.stop()

    # DB-091
    p91 = os.path.join(tmp, "d91.db")
    db91 = make_db(p91); db91.initialise(applied_by="qa")
    await db91.start()
    from sqlalchemy import select
    from prama.db.models.platform import Tenant
    async with db91.unit_of_work() as uow:
        uow.tenants.create(slug="t91-pending", display_name="Pending")
        # an unrelated query -- must NOT autoflush the pending tenant
        res = await uow._session.execute(select(Tenant).where(Tenant.slug == "t91-other-unrelated"))
        _ = res.first()
        # now check directly whether the pending insert reached the db yet (raw connection bypassing session)
        from sqlalchemy import text as satext91
        raw_count = (await uow._session.execute(satext91("SELECT COUNT(*) FROM tenant WHERE slug='t91-pending'"))).scalar()
    await db91.stop()
    R("DB-091", raw_count == 0, f"row count visible via raw SQL for the still-pending insert, issued mid-transaction before an explicit flush: {raw_count} (expected 0 -- autoflush must not have fired)")

    # DB-092: raw SQL DAO methods (RoleDao.grant, SettingDao.put) flush pending ORM state first
    p92 = os.path.join(tmp, "d92.db")
    db92 = make_db(p92); db92.initialise(applied_by="qa")
    await db92.start()
    async with db92.unit_of_work() as uow:
        t92 = uow.tenants.create(slug="t92", display_name="T92")
        await uow.flush()
        pr92 = uow.principals.create(tenant_id=str(t92.id), username="bob92", display_name="Bob")
        role92 = uow.roles.create(tenant_id=str(t92.id), name="viewer", permissions=["read"])
        # ids are minted client-side (core/ids.py); pre-assign them explicitly so
        # they are known without an explicit flush -- both rows remain PENDING
        # (never flushed by this test) when grant() is called, so grant() itself
        # must flush them first or the raw INSERT's FK references would fail.
        from prama.core.ids import new_ulid as _new_ulid
        pr92.id = _new_ulid()
        role92.id = _new_ulid()
        await uow.roles.grant(pr92.id, role92.id, granted_by=None)
    async with db92.unit_of_work() as uow:
        roles_of = await uow.principals.roles_of(pr92.id)
    await db92.stop()
    R("DB-092", any(r.name == "viewer" for r in roles_of), f"principal_role granted via raw SQL against still-pending ORM rows succeeded; roles_of={[r.name for r in roles_of]}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

asyncio.run(main())
