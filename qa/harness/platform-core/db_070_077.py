import sys, os, asyncio, re
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "postgresql://prama:prama@127.0.0.1:55433/prama")
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
    # DB-070: async engine kwargs -- since it cannot be *constructed* due to the
    # QueuePool/async incompatibility found in DB-066/069, test the KWARGS dict
    # directly (that part of the code does run) but flag that a real connection
    # is unreachable through the documented path.
    settings70 = pg_settings(application_name="qa-app", statement_timeout="2500ms")
    dialect70 = PostgresDialect(settings70)
    kwargs70 = dialect70.engine_kwargs(is_async=True)
    ca70 = kwargs70.get("connect_args", {}).get("server_settings", {})
    kwargs_ok = (ca70.get("application_name") == "qa-app" and ca70.get("statement_timeout") == "2500"
                 and ca70.get("search_path") == "public")
    from sqlalchemy.ext.asyncio import create_async_engine
    try:
        create_async_engine(dialect70.async_url(), **kwargs70)
        connect_ok = True
    except Exception as e:
        connect_ok = False
        connect_err = e
    R("DB-070", kwargs_ok and connect_ok,
      f"engine_kwargs(is_async=True) sets application_name={ca70.get('application_name')!r}, "
      f"statement_timeout={ca70.get('statement_timeout')!r}ms, search_path={ca70.get('search_path')!r} (correct values); "
      f"but create_async_engine() itself {'succeeded' if connect_ok else f'FAILED: {type(connect_err).__name__}: {connect_err}'} "
      f"-- confirms the same QueuePool/async-engine defect found under DB-066 blocks the whole path from ever reaching "
      f"a real connection where these settings would actually be verified server-side")

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

    # DB-072: sslmode on the async path -- since the async engine cannot even be
    # constructed (DB-066/DB-070's finding), sslmode=require can never be honoured
    # OR refused at start-up: the whole path is unreachable.
    settings72 = pg_settings(sslmode="require")
    dialect72 = PostgresDialect(settings72)
    kwargs72 = dialect72.engine_kwargs(is_async=True)
    has_sslmode_anywhere = "sslmode" in str(kwargs72)
    from sqlalchemy.ext.asyncio import create_async_engine as cae72
    try:
        cae72(dialect72.async_url(), **kwargs72)
        R("DB-072", False, "async engine construction unexpectedly succeeded")
    except Exception as e:
        R("DB-072", False,
          f"sslmode=require is silently absent from engine_kwargs(is_async=True) (has_sslmode_anywhere={has_sslmode_anywhere}, "
          f"matching the comment 'the driver negotiates TLS itself'), AND separately the async engine cannot even be "
          f"constructed due to the QueuePool bug ({type(e).__name__}: {e}) -- so today sslmode=require against Postgres "
          f"is neither honoured nor refused with an explanation on the async path; it simply cannot connect at all, "
          f"for an unrelated reason, which masks the real gap")

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
