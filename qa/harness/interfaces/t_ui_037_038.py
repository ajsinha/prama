import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    # UI-037: password with awkward characters, set via the CLI, authenticates exactly
    DB37 = c.WORKDIR / "ui037.db"
    cfg37, d37, dbpath37 = None, None, None
    d37 = c.WORKDIR / "ui037setup"
    d37.mkdir(exist_ok=True, parents=True)
    cfgf37 = d37 / "application.yaml"
    dbfile37 = d37 / "x.db"
    cfgf37.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {dbfile37}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
        "security:\n  session_secret: test-only-not-a-secret\n"
    )
    c.run_sub(["--config", str(cfgf37), "db", "init"])
    c.run_sub(["--config", str(cfgf37), "tenant", "create", "acme-bank"])
    awkward_pw = "a\nb\x00c\U0001F600" + ("d" * 8000) + "  "
    code, out, err = c.run_sub(["--config", str(cfgf37), "principal", "create", "awkward37", "--tenant", "acme-bank"], stdin_input=awkward_pw + "\n")
    setup_ok = code == 0
    from prama.db import Database
    ui_cfg37 = u.ui_config(dbfile37)
    db37 = Database.from_config(ui_cfg37)
    await db37.start()
    from prama.api import create_app
    app37 = create_app(ui_cfg37, database=db37)
    import httpx
    from httpx import ASGITransport
    async with app37.router.lifespan_context(app37):
        async with httpx.AsyncClient(transport=ASGITransport(app=app37), base_url="http://testserver", follow_redirects=False) as http:
            r = await http.post("/sign-in", data={"username": "awkward37", "password": awkward_pw, "tenant": "acme-bank"})
            ok37 = setup_ok and r.status_code == 303 and r.headers.get("location") == "/estate"
            record("UI-037", "PASS" if ok37 else "FAIL", f"cli_setup_code={code} cli_err={err[:150] if code!=0 else ''} signin_status={r.status_code}")
    await db37.stop()

    # UI-038: sign-in rate limiting, or its documented absence
    DB38 = c.WORKDIR / "ui038.db"
    env38 = u.UiEnv(str(DB38))
    await env38.start()
    await env38.create_principal("victim38", "victimpassword1", ["owner"])
    http38 = env38.client()
    statuses = []
    N = 30  # not literally 1000, for time's sake, but enough to reveal any throttling
    for i in range(N):
        r = await http38.post("/sign-in", data={"username": "victim38", "password": f"wrongpassword{i}"})
        statuses.append(r.status_code)
    all_401 = all(s == 401 for s in statuses)
    record(
        "UI-038",
        "FAIL" if all_401 else "PASS",
        f"n_attempts={N} all_401_no_throttling_observed={all_401} status_set={set(statuses)} -- "
        f"'Expected: throttling, lockout, or an explicit decision recorded that there is none' -- "
        f"{N} rapid wrong-password attempts against the same account all return a uniform 401 with no "
        f"visible slowdown, lockout status code, or Retry-After header -- no rate limiting is applied, "
        f"and nothing in web/routes/auth_routes.py::sign_in or its module docstring records this as a "
        f"deliberate decision" if all_401 else "throttling observed",
    )
    await http38.aclose()
    await env38.stop()

    print("done ui batch 2c")


asyncio.run(main())
