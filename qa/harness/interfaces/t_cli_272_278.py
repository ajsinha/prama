import sys, os, json, subprocess, time, socket
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "serve2"
WORK.mkdir(exist_ok=True, parents=True)


def new_cfg(name, secret="test-secret-value-1234", web_enabled=True, default_tenant=None, drift=False):
    d = c.WORKDIR / name
    d.mkdir(exist_ok=True, parents=True)
    cfgf = d / "application.yaml"
    dbpath = d / "x.db"
    text = (
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {dbpath}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
        f"security:\n  session_secret: {secret!r}\n"
        f"web:\n  enabled: {'true' if web_enabled else 'false'}\n"
    )
    if default_tenant:
        text += f"tenancy:\n  default_tenant: {default_tenant}\n"
    cfgf.write_text(text)
    c.run_sub(["--config", str(cfgf), "db", "init"])
    if drift:
        import sqlite3
        conn = sqlite3.connect(dbpath)
        conn.execute("ALTER TABLE tenant ADD COLUMN zz_drift TEXT")
        conn.execute("UPDATE schema_state SET file_digest = 'deadbeefdeadbeefdeadbeefdeadbeef' WHERE id=1")
        conn.commit()
        conn.close()
    return cfgf, d, dbpath


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_serve_capture(cfg, extra_args=None, wait_s=2.0, use_pipe_stdout=True):
    port = free_port()
    argv = ["prama", "--config", str(cfg), "serve", "--port", str(port)] + (extra_args or [])
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE | 0 if False else subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL if not use_pipe_stdout else None,
        env=os.environ,
        text=True,
    )
    time.sleep(wait_s)
    alive = proc.poll() is None
    if alive:
        proc.terminate()
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate(timeout=5)
    else:
        out, err = proc.communicate(timeout=5)
    return alive, proc.returncode, out, err, port


# CLI-272: --host with an unroutable address
cfg272, d272, db272 = new_cfg("cli272", web_enabled=False)
alive, rc, out, err, port = run_serve_capture(cfg272, ["--host", "10.255.255.1"], wait_s=3)
banner_claims_url = f"10.255.255.1:{port}" in out
res_a = (alive, rc, banner_claims_url, out[:150], err[-300:])
alive2, rc2, out2, err2, port2 = run_serve_capture(cfg272, ["--host", "not-a-host"], wait_s=2)
banner_claims_url2 = "not-a-host" in out2
res_b = (alive2, rc2, banner_claims_url2, out2[:150], err2[-300:])
ok = (not banner_claims_url or rc != 0) and (not alive2 and rc2 != 0)
record("CLI-272", "PASS" if ok else "FAIL", f"unroutable_ip={res_a} bad_hostname={res_b}")

# CLI-273: prints Console, then API, then Docs when web is enabled
cfg273, d273, db273 = new_cfg("cli273", web_enabled=True, default_tenant=None)
tcode, tout, _ = c.run_sub(["--json", "--config", str(cfg273), "tenant", "create", "acme-bank"])
tid273 = json.loads(tout)["id"]
cfg273.write_text(cfg273.read_text() + f"tenancy:\n  default_tenant: {tid273}\n")
alive, rc, out, err, port = run_serve_capture(cfg273, wait_s=2)
order_ok = ("Console" in out) and ("API" in out) and ("Docs" in out) and (out.index("Console") < out.index("API") < out.index("Docs"))
record("CLI-273", "PASS" if order_ok else "FAIL", f"order_ok={order_ok} out={out[:300]!r}")

# CLI-274: web.enabled false -> no console URL, no secret needed
cfg274, d274, db274 = new_cfg("cli274", secret="", web_enabled=False)
alive, rc, out, err, port = run_serve_capture(cfg274, wait_s=2)
ok = alive and "Console" not in out and "SecretMissingError" not in err and "CONFIG.SECRET_MISSING" not in err
record("CLI-274", "PASS" if ok else "FAIL", f"alive={alive} rc={rc} out={out[:200]!r} err={err[-300:]!r}")

# CLI-275: warns at startup when no tenant configured
cfg275, d275, db275 = new_cfg("cli275", web_enabled=True, default_tenant=None)
alive, rc, out, err, port = run_serve_capture(cfg275, wait_s=2)
ok = "No tenant is configured" in out and "prama tenant create" in out
record("CLI-275", "PASS" if ok else "FAIL", f"out={out[:500]!r}")

# CLI-276: banner and warning survive a non-TTY stdout (subprocess.PIPE is already non-tty)
cfg276, d276, db276 = new_cfg("cli276", web_enabled=True, default_tenant=None)
alive, rc, out, err, port = run_serve_capture(cfg276, wait_s=2)
ok = "Prama" in out and "API" in out and "No tenant is configured" in out
record("CLI-276", "PASS" if ok else "FAIL", f"(stdout captured via PIPE, i.e. non-tty) out={out[:300]!r}")

# CLI-277: --reload honoured or removed
import inspect
src = inspect.getsource(__import__("prama.cli.commands", fromlist=["ServeCommand"]).ServeCommand.run)
reload_passed = "reload=" in src or "reload =" in src
record(
    "CLI-277",
    "FAIL" if not reload_passed else "PASS",
    f"reload_passed_to_uvicorn.run={reload_passed} -- the flag is declared (argparse '--reload') but "
    f"cli/commands.py::ServeCommand.run never passes reload=ctx.args.reload to uvicorn.run(...); "
    f"a declared flag silently discarded",
)

# CLI-278: serve verifies the schema at start-up (drifted database) -- round 2 found that an
# EXTRA column plus a digest mismatch (the shared drift=True helper above) is exactly the
# non-blocking/invisible drift CLI-032/033 already document, so it never made 'serve' refuse;
# a genuinely BLOCKING drift needs a MISSING column instead (CLI-034's family).
cfg278, d278, db278 = new_cfg("cli278", web_enabled=False, drift=False)
import sqlite3 as _sqlite3_278

_conn278 = _sqlite3_278.connect(db278)
_conn278.execute("ALTER TABLE tenant DROP COLUMN display_name")
_conn278.commit()
_conn278.close()
alive, rc, out, err, port = run_serve_capture(cfg278, wait_s=2)
ok = (not alive) and rc != 0 and ("drift" in err.lower() or "drift" in out.lower() or "SchemaDrift" in err)
record("CLI-278", "PASS" if ok else "FAIL", f"alive={alive} rc={rc} out={out[:200]!r} err={err[-400:]!r}")

print("done serve batch part2")
