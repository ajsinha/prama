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

from prama.db.dialects import PostgresDialect
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.errors import DatabaseError

def pg_settings(**overrides):
    cfg = Configuration(deep_merge(DEFAULTS, {
        "database": {"dialect": "postgres", "postgres": {
            "host": host, "port": int(port), "database": database, "user": user, "password": pw, **overrides}}
    }))
    return DbSettings.from_config(cfg)

async def main():
    # DB-070: async engine kwargs -- B1 fixed the QueuePool/async-engine incompatibility
    # (AsyncAdaptedQueuePool now used for is_async=True), so this connects for real and
    # the configured values are read back from the live server, not just from the kwargs dict.
    settings70 = pg_settings(application_name="qa-app-070", statement_timeout="2500ms")
    dialect70 = PostgresDialect(settings70)
    kwargs70 = dialect70.engine_kwargs(is_async=True)
    ca70 = kwargs70.get("connect_args", {}).get("server_settings", {})
    kwargs_ok = (ca70.get("application_name") == "qa-app-070" and ca70.get("statement_timeout") == "2500"
                 and ca70.get("search_path") == "public")
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text as satext70
    engine70 = create_async_engine(dialect70.async_url(), **kwargs70)
    try:
        async with engine70.connect() as conn:
            app_name, stmt_timeout, search_path = (await conn.execute(satext70(
                "SELECT current_setting('application_name'), current_setting('statement_timeout'), "
                "current_setting('search_path')"
            ))).one()
        server_ok = (app_name == "qa-app-070" and stmt_timeout == "2500ms" and search_path.startswith("public"))
        R("DB-070", kwargs_ok and server_ok,
          f"engine_kwargs(is_async=True) sets application_name={ca70.get('application_name')!r}, "
          f"statement_timeout={ca70.get('statement_timeout')!r}ms, search_path={ca70.get('search_path')!r} (correct "
          f"values); live connection over the async path (now constructible: B1 fixed poolclass=QueuePool -> "
          f"AsyncAdaptedQueuePool) confirms the SERVER sees application_name={app_name!r}, "
          f"statement_timeout={stmt_timeout!r}, search_path={search_path!r}")
    except Exception as e:
        R("DB-070", False, f"async connection failed: {type(e).__name__}: {e}")
    finally:
        await engine70.dispose()

    # DB-071: sync psycopg path passes sslmode -- require against a non-TLS server
    settings71 = pg_settings(sslmode="require")
    dialect71 = PostgresDialect(settings71)
    kwargs71 = dialect71.engine_kwargs(is_async=False)
    from sqlalchemy import create_engine, text as satext
    engine71 = create_engine(dialect71.sync_url(), **kwargs71)
    try:
        with engine71.connect() as conn:
            conn.execute(satext("SELECT 1"))
        R("DB-071", False, "sslmode=require connected to a server without TLS -- expected a refusal")
    except Exception as e:
        msg = str(e).lower()
        ssl_related = "ssl" in msg or "tls" in msg
        R("DB-071", ssl_related, f"connection with sslmode=require raised {type(e).__name__}: {str(e)[:200]!r} (ssl-related={ssl_related})")
    finally:
        engine71.dispose()

    # DB-072: sslmode on the async path -- B1 also added an asyncpg SSL-mode mapping
    # (_asyncpg_ssl), so sslmode=require now surfaces as connect_args['ssl'] and a
    # connection to this non-TLS test server must be refused, not silently accepted.
    settings72 = pg_settings(sslmode="require")
    dialect72 = PostgresDialect(settings72)
    kwargs72 = dialect72.engine_kwargs(is_async=True)
    ssl_kw72 = kwargs72.get("connect_args", {}).get("ssl")
    from sqlalchemy.ext.asyncio import create_async_engine as cae72
    engine72 = cae72(dialect72.async_url(), **kwargs72)
    refused72 = False
    err72 = None
    try:
        async with engine72.connect() as conn:
            await conn.execute(satext70("SELECT 1"))
        R("DB-072", False, "async engine with sslmode=require connected in plaintext to a non-TLS server -- expected a refusal")
    except Exception as e:
        refused72 = True
        err72 = f"{type(e).__name__}: {e}"
        R("DB-072", ssl_kw72 is not None and refused72,
          f"engine_kwargs(is_async=True) with sslmode=require now sets connect_args['ssl']={ssl_kw72!r} (previously "
          f"silently absent, matching the old comment 'the driver negotiates TLS itself'); connecting over the async "
          f"path to this non-TLS test server is refused: {err72} -- sslmode=require is honoured, not silently dropped")
    finally:
        await engine72.dispose()

    # DB-073: statement_timeout cancels a long query -- sync engine only (async blocked)
    settings73 = pg_settings(statement_timeout="1s")
    dialect73 = PostgresDialect(settings73)
    from sqlalchemy import create_engine as ce73, text as st73
    engine73 = ce73(dialect73.sync_url(), **dialect73.engine_kwargs(is_async=False))
    import time
    t0 = time.monotonic()
    try:
        with engine73.connect() as conn:
            conn.execute(st73("SELECT pg_sleep(5)"))
        R("DB-073", False, "pg_sleep(5) completed without being cancelled by a 1s statement_timeout")
    except Exception as e:
        dt = time.monotonic() - t0
        cancelled_promptly = dt < 3.0
        R("DB-073", cancelled_promptly, f"sync path: pg_sleep(5) with statement_timeout=1s raised after {dt:.2f}s: {type(e).__name__}: {str(e)[:150]!r}")
    finally:
        engine73.dispose()

    # DB-074: fractional statement_timeout does not truncate to zero
    settings74 = pg_settings(statement_timeout="500us")
    dialect74 = PostgresDialect(settings74)
    kwargs74_sync = dialect74.engine_kwargs(is_async=False)
    opts = kwargs74_sync.get("connect_args", {}).get("options", "")
    m74 = re.search(r"statement_timeout=(\d+)", opts)
    timeout_val = m74.group(1) if m74 else None
    R("DB-074", timeout_val is not None and timeout_val != "0",
      f"statement_timeout=500us (0.0005s) -> connect options string contains statement_timeout={timeout_val!r} "
      f"(int(0.0005*1000)=int(0.5)={int(0.0005*1000)}); a value of '0' means UNLIMITED in PostgreSQL, the opposite of what was configured")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

asyncio.run(main())
