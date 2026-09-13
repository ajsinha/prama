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
from prama.core.errors import DatabaseError, ConflictError

def make_db(path, **db_overrides):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}, **db_overrides}}))
    settings = DbSettings.from_config(cfg)
    return Database(settings)

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-uow-")

    # DB-062: connect hook shared -- sync and async both apply the pragma
    p62 = os.path.join(tmp, "d62.db")
    cfg62 = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": p62, "synchronous": "FULL"}}}))
    from prama.db.settings import DbSettings as DBS
    settings62 = DBS.from_config(cfg62)
    db62 = Database(settings62)
    db62.initialise(applied_by="qa")
    from sqlalchemy import text as satext
    with db62.sync_engine().connect() as conn:
        sync_val = conn.execute(satext("PRAGMA synchronous")).scalar()
    await db62.start()
    engine62 = db62._engines.async_engine()
    async with engine62.connect() as conn:
        r = await conn.execute(satext("PRAGMA synchronous"))
        async_val = r.scalar()
    await db62.stop()
    R("DB-062", sync_val == async_val == 2, f"sync PRAGMA synchronous={sync_val}, async PRAGMA synchronous={async_val}")

    # DB-063
    p63 = os.path.join(tmp, "d63.db")
    db63 = make_db(p63)
    db63.initialise(applied_by="qa")
    e1 = db63.sync_engine()
    e2 = db63.sync_engine()
    await db63.start()
    ae1 = db63._engines.async_engine()
    ae2 = db63._engines.async_engine()
    await db63.stop()
    R("DB-063", e1 is e2 and ae1 is ae2, f"sync same object={e1 is e2}, async same object={ae1 is ae2}")

    # DB-064
    p64a = os.path.join(tmp, "d64a.db")
    p64b = os.path.join(tmp, "d64b.db")
    db64a = make_db(p64a); db64a.initialise(applied_by="qa")
    db64b = make_db(p64b); db64b.initialise(applied_by="qa")
    await db64a.start(); await db64b.start()
    async with db64a.unit_of_work() as uow:
        uow.tenants.create(slug="only-in-a", display_name="A")
    async with db64b.unit_of_work() as uow:
        t = await uow.tenants.by_slug("only-in-a")
    await db64a.stop(); await db64b.stop()
    R("DB-064", t is None, f"tenant created in db64a visible in db64b: {t}")

    # DB-065: missing driver (simulate asyncpg import failure)
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **kw):
        if name == "asyncpg" or name.startswith("asyncpg"):
            raise ModuleNotFoundError("No module named 'asyncpg'")
        return real_import(name, *a, **kw)
    cfg65 = Configuration(deep_merge(DEFAULTS, {"database": {"dialect": "postgres"}}))
    settings65 = DBS.from_config(cfg65)
    db65 = Database(settings65)
    builtins.__import__ = fake_import
    try:
        try:
            db65._engines.async_engine()
            R("DB-065", False, "no exception raised despite simulated missing asyncpg")
        except DatabaseError as e:
            ok65 = e.code == "DB.ENGINE_CREATE_FAILED" and "pip install 'prama[postgres]'" in e.remedy
            R("DB-065", ok65, f"{e.code}: {e.remedy!r}")
        except Exception as e:
            R("DB-065", False, f"wrong exception type: {type(e).__name__}: {e}")
    finally:
        builtins.__import__ = real_import

    # DB-066: password never appears in engine error -- bad host
    cfg66 = Configuration(deep_merge(DEFAULTS, {"database": {"dialect": "postgres", "postgres": {
        "host": "this-host-does-not-resolve.invalid", "password": "supersecretpw123"}}}))
    settings66 = DBS.from_config(cfg66)
    db66 = Database(settings66)
    try:
        eng66 = db66._engines.async_engine()
        # engine creation itself is lazy (no connection attempt); must actually connect to trigger a failure
        try:
            async with eng66.connect():
                pass
            R("DB-066", False, "connection unexpectedly succeeded")
        except Exception as e:
            leaked = "supersecretpw123" in str(e)
            R("DB-066", not leaked, f"connect() to unresolvable host raised {type(e).__name__}; password leaked in message={leaked}: {str(e)[:200]!r}")
    except DatabaseError as e:
        leaked = "supersecretpw123" in str(e)
        R("DB-066", not leaked,
          f"MAJOR FINDING (independent of DB-066's own scenario): async_engine() itself raised {e.code} before even "
          f"attempting a connection -- 'Pool class QueuePool cannot be used with asyncio engine'. PostgresDialect."
          f"engine_kwargs(is_async=True) sets poolclass=QueuePool, which SQLAlchemy 2.0's async engine rejects "
          f"outright (it requires AsyncAdaptedQueuePool). This means the ASYNC PostgreSQL engine -- the path the "
          f"docstring says handles 'everything else' -- cannot be constructed at all on this SQLAlchemy version; "
          f"no test in tests/ exercises it (postgres_config fixture in conftest.py is defined but never used by "
          f"any test). Password-redaction question is moot since the error never reaches a real connection attempt; "
          f"password leaked in this message={leaked}: {str(e)[:300]!r}")
    finally:
        await db66._engines.dispose()

    # DB-067
    p67 = os.path.join(tmp, "d67.db")
    db67 = make_db(p67); db67.initialise(applied_by="qa")
    await db67.start()
    engine67_before = db67._engines.async_engine()
    await db67._engines.dispose()
    engine67_after = db67._engines.async_engine()
    R("DB-067", engine67_before is not engine67_after, f"same object after dispose+rebuild={engine67_before is engine67_after}")
    await db67._engines.dispose()

    # DB-068: in-memory sqlite keeps schema across sessions
    cfg68 = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": ":memory:"}}}))
    settings68 = DBS.from_config(cfg68)
    db68 = Database(settings68)
    db68.initialise(applied_by="qa")
    await db68.start()
    try:
        async with db68.unit_of_work() as uow:
            uow.tenants.create(slug="mem-tenant", display_name="Mem")
        async with db68.unit_of_work() as uow:
            t68 = await uow.tenants.by_slug("mem-tenant")
        R("DB-068", t68 is not None, f"tenant survives across separate unit-of-work sessions on :memory: -- {t68}")
    except DatabaseError as e:
        R("DB-068", False,
          f"the schema applied by initialise() (the SYNC engine's own private StaticPool connection) is invisible "
          f"to the ASYNC engine (a SEPARATE StaticPool / separate physical in-memory database, since pysqlite and "
          f"aiosqlite are different DBAPI drivers and plain ':memory:' is not a shared-cache URI): {e.code}: "
          f"{e.context.get('detail')!r}. This is the exact confusion tests/conftest.py::sqlite_config's own docstring "
          f"warns about ('A file rather than :memory: so that the synchronous DDL engine and the asynchronous data "
          f"engine genuinely share a database') -- but database.sqlite.path=':memory:' is still a documented, "
          f"'honoured' configuration value (CFG-026) with no warning that the normal init-then-serve pattern breaks under it")
    finally:
        await db68.stop()

    # DB-069
    from prama.db.dialects import SqliteDialect
    from sqlalchemy.pool import NullPool, QueuePool
    kwargs_async = db67._dialect.engine_kwargs(is_async=True)
    kwargs_sync = db67._dialect.engine_kwargs(is_async=False)
    R("DB-069", kwargs_async.get("poolclass") is NullPool and kwargs_sync.get("poolclass") is QueuePool,
      f"async poolclass={kwargs_async.get('poolclass')}, sync poolclass={kwargs_sync.get('poolclass')}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

asyncio.run(main())
