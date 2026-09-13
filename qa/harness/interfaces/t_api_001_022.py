import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record

WORK = a.REPO_ROOT  # unused directly
import cli_common as c  # reuse WORKDIR for scratch db paths

DB = c.WORKDIR / "api1.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # API-001: openapi.json only has /api/v1 operations, none of the console's routes
    async with env.client(env.api_key) as http:
        r = await http.get("/openapi.json")
        doc = r.json()
        paths = list(doc.get("paths", {}).keys())
        console_like = [p for p in paths if not p.startswith("/api/v1") and "estate" in p]
        all_api_prefixed = all(p.startswith("/api/v1") for p in paths)
        record("API-001", "PASS" if all_api_prefixed else "FAIL", f"n_paths={len(paths)} all_api_prefixed={all_api_prefixed} sample={paths[:5]}")

    # API-003: /docs renders, /redoc absent
    async with env.client(env.api_key) as http:
        r1 = await http.get("/docs")
        r2 = await http.get("/redoc")
        ok = r1.status_code == 200 and r2.status_code == 404
        record("API-003", "PASS" if ok else "FAIL", f"docs={r1.status_code} redoc={r2.status_code}")

    # API-004: injected database is used, not a second one -- verified structurally: env.database is
    # the same object referenced by app.state.database after lifespan entry
    same_db = env.app.state.database is env.database
    record("API-004", "PASS" if same_db else "FAIL", f"app.state.database is env.database: {same_db}")

    # API-005: shipped packs install at application start -- in a FRESH process that only calls
    # create_app() (never the CLI's own install_shipped()), the calendar 'TARGET2' must resolve,
    # exactly the example the packs/__init__.py comment itself cites (finding H7's shape).
    import subprocess
    script = (
        "import sys; sys.path.insert(0,'/home/ashutosh/PycharmProjects/prama/src'); "
        "from prama.api.app import create_app; from prama.core.config import ConfigurationBuilder; "
        "from prama.core.config.defaults import DEFAULTS; "
        "cfg = ConfigurationBuilder().with_defaults(DEFAULTS).with_mapping({'database':{'dialect':'sqlite','sqlite':{'path':':memory:'},'schema_dir':'/home/ashutosh/PycharmProjects/prama/schema'},'security':{'session_secret':'x'},'web':{'enabled':False}}, name='t').build(); "
        "app = create_app(cfg); "
        "from prama.schedule.spec import parse; "
        "sched = parse(\"06:30 TARGET2\"); "
        "print('RESOLVED', sched)"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    ok = proc.returncode == 0 and "RESOLVED" in proc.stdout
    record("API-005", "PASS" if ok else "FAIL", f"rc={proc.returncode} out={proc.stdout[:200]!r} err={proc.stderr[-300:]!r}")

    await env.stop()


asyncio.run(main())
print("done api batch 1a")
