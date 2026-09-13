import sys, os, asyncio, re
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "postgresql://prama:prama@127.0.0.1:55432/prama")
m = re.match(r"postgresql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(\w+)", DSN)
user, pw, host, port, database = m.group(1), m.group(2), m.group(3), m.group(4) or "5432", m.group(5)

from prama.db import Database
from prama.db.dialects import PostgresDialect
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.ids import new_ulid

def pg_config(**overrides):
    return Configuration(deep_merge(DEFAULTS, {
        "database": {"dialect": "postgres", "postgres": {
            "host": host, "port": int(port), "database": database, "user": user, "password": pw, **overrides}}
    }))

def make_db(**overrides):
    return Database(DbSettings.from_config(pg_config(**overrides)))

async def main():
    # bootstrap schema once (idempotent)
    db0 = make_db()
    db0.initialise(applied_by="qa-r3")

    # -- DB-070: asyncpg path actually connects and the server sees the configured settings
    settings70 = DbSettings.from_config(pg_config(application_name="qa-app-070", statement_timeout="2500ms"))
    dialect70 = PostgresDialect(settings70)
    kwargs70 = dialect70.engine_kwargs(is_async=True)
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text as satext
    engine70 = create_async_engine(dialect70.async_url(), **kwargs70)
    try:
        async with engine70.connect() as conn:
            row = (await conn.execute(satext(
                "SELECT current_setting('application_name'), current_setting('statement_timeout'), current_setting('search_path')"
            ))).one()
        app_name, stmt_timeout, search_path = row
        R("DB-070", app_name == "qa-app-070" and stmt_timeout == "2500ms" and search_path.startswith("public"),
          f"live asyncpg connection: application_name={app_name!r}, statement_timeout={stmt_timeout!r}, "
          f"search_path={search_path!r} -- server confirms all three configured values took effect over the async path")
    except Exception as e:
        R("DB-070", False, f"asyncpg connection failed: {type(e).__name__}: {e}")
    finally:
        await engine70.dispose()

    # -- DB-072: sslmode=require on the async path against a non-TLS server -- must refuse, not connect plaintext
    settings72 = DbSettings.from_config(pg_config(sslmode="require"))
    dialect72 = PostgresDialect(settings72)
    kwargs72 = dialect72.engine_kwargs(is_async=True)
    ssl_kw = kwargs72.get("connect_args", {}).get("ssl")
    engine72 = create_async_engine(dialect72.async_url(), **kwargs72)
    refused72 = False
    err72 = None
    try:
        async with engine72.connect() as conn:
            await conn.execute(satext("SELECT 1"))
    except Exception as e:
        refused72 = True
        err72 = f"{type(e).__name__}: {e}"
    finally:
        await engine72.dispose()
    R("DB-072", ssl_kw is not None and refused72,
      f"engine_kwargs(is_async=True) with sslmode=require now sets connect_args['ssl']={ssl_kw!r} (previously silently "
      f"absent); connecting to this non-TLS test server over the async path is refused={refused72} ({err72}) -- "
      f"sslmode=require is honoured, not silently dropped, on the async path")

    # -- DB-148: grant/re-grant works on the async (real application) path against live PostgreSQL
    db148 = make_db()
    await db148.start()
    async with db148.unit_of_work() as uow:
        t148 = uow.tenants.create(slug=f"pg148-{new_ulid()[-8:].lower()}", display_name="PG148")
        await uow.flush()
        tid148 = str(t148.id)
        p148 = uow.principals.create(tenant_id=tid148, username="grantee148", display_name="G148")
        role148 = uow.roles.create(tenant_id=tid148, name="role148", permissions=["read"])
        await uow.flush()
        pid148, rid148 = str(p148.id), str(role148.id)
    grant_ok = True
    grant_err = None
    try:
        async with db148.unit_of_work() as uow:
            await uow.roles.grant(pid148, rid148, granted_by="qa-r3")
        async with db148.unit_of_work() as uow:
            await uow.roles.grant(pid148, rid148, granted_by="qa-r3")  # re-grant, must be idempotent
        async with db148.unit_of_work() as uow:
            roles_after = await uow.principals.roles_of(pid148)
    except Exception as e:
        grant_ok = False
        grant_err = f"{type(e).__name__}: {e}"
        roles_after = []
    R("DB-148", grant_ok and len(roles_after) == 1,
      f"live PostgreSQL, async path: grant then re-grant of role 'read' -- "
      f"{'succeeded, idempotent (1 row): ' + str([r.name for r in roles_after]) if grant_ok else 'FAILED: ' + str(grant_err)}")
    await db148.stop()

    # -- DB-279: the conditional upsert lease provider works on PostgreSQL too (async engine + AsyncAdaptedQueuePool)
    settings279 = DbSettings.from_config(pg_config())
    db279 = make_db()
    await db279.start()
    lease_ok = True
    lease_err = None
    detail279 = {}
    try:
        provider = db279.lease_provider()
        resource = f"qa-lease-279-{new_ulid()[-8:].lower()}"
        holderA = f"holder-A-{new_ulid()[-6:]}"
        holderB = f"holder-B-{new_ulid()[-6:]}"
        leaseA = await provider.acquire(resource, holder=holderA, ttl_seconds=2)
        detail279["acquireA"] = leaseA is not None
        # contend: B tries while A holds -- should fail/return None
        try:
            leaseB_contend = await provider.acquire(resource, holder=holderB, ttl_seconds=2)
        except Exception:
            leaseB_contend = None
        detail279["contendB_blocked"] = leaseB_contend is None
        await asyncio.sleep(2.2)  # let A's lease expire
        leaseB_takeover = await provider.acquire(resource, holder=holderB, ttl_seconds=2)
        detail279["takeoverB"] = leaseB_takeover is not None
        lease_ok = detail279["acquireA"] and detail279["contendB_blocked"] and detail279["takeoverB"]
    except Exception as e:
        lease_ok = False
        lease_err = f"{type(e).__name__}: {e}"
    finally:
        await db279.stop()
    R("DB-279", lease_ok,
      f"live PostgreSQL, DatabaseLeaseProvider via async engine: {detail279}"
      + (f" -- error: {lease_err}" if lease_err else "")
      + " -- acquire/contend/take-over-expired all exercised against a real PostgreSQL server over the async path")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

asyncio.run(main())
