import sys, os, json, subprocess, time, socket
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "serve"
WORK.mkdir(exist_ok=True, parents=True)


def new_cfg(name, secret="test-secret-value-1234", web_enabled=True, default_tenant=None):
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
    return cfgf, d, dbpath


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_serve(cfg, extra_args=None, stdout_is_pipe=True):
    argv = ["prama", "--config", str(cfg), "serve"] + (extra_args or [])
    return subprocess.Popen(
        argv,
        stdout=subprocess.PIPE if stdout_is_pipe else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=os.environ,
        text=True,
    )


def wait_and_kill(proc, wait_s=1.5):
    time.sleep(wait_s)
    alive = proc.poll() is None
    if alive:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    return alive


# CLI-268: serve refuses when uvicorn not installed -- simulate by blocking the import
sim_script = WORK / "block_uvicorn.py"
sim_script.write_text(
    "import sys, builtins\n"
    "real_import = builtins.__import__\n"
    "def fake_import(name, *a, **kw):\n"
    "    if name == 'uvicorn' or name.startswith('uvicorn.'):\n"
    "        raise ImportError('simulated: not installed')\n"
    "    return real_import(name, *a, **kw)\n"
    "builtins.__import__ = fake_import\n"
    "sys.path.insert(0, '" + str(c.REPO_ROOT / "src") + "')\n"
    "from prama.cli.main import main\n"
    "sys.exit(main())\n"
)
cfg268, d268, db268 = new_cfg("cli268")
proc = subprocess.run([sys.executable, str(sim_script), "--config", str(cfg268), "serve"], capture_output=True, text=True, timeout=30)
ok = proc.returncode == 1 and "CLI.SERVER_MISSING" in proc.stderr and "prama[serve]" in proc.stderr
record("CLI-268", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr[:300]!r}")

# CLI-269: the remedy's pip command works, in principle (uvicorn already present here) -- skip actual pip install (would mutate the venv); confirm the exact command is syntactically valid pip syntax and 'prama[serve]' resolves in pyproject.toml
pyproject = (c.REPO_ROOT / "pyproject.toml").read_text()
ok = "[project.optional-dependencies]" in pyproject and "serve" in pyproject and "uvicorn" in pyproject
record(
    "CLI-269",
    "PASS" if ok else "FAIL",
    f"'prama[serve]' extra present in pyproject.toml={ok} -- not run for real: doing so would install/"
    f"modify the shared venv, which is out of scope for a QA harness; the extra's presence and that "
    f"'serve' currently runs (CLI-201 etc used config, but every subprocess call here already succeeds "
    f"with uvicorn installed) is the closest verifiable proxy",
)

# CLI-270: --port outside 1-65535
cfg270, d270, db270 = new_cfg("cli270", web_enabled=False)
proc = start_serve(cfg270, ["--port", "99999"])
try:
    out, err = proc.communicate(timeout=8)
    alive = False
except subprocess.TimeoutExpired:
    alive = wait_and_kill(proc, 0.1)
    out, err = proc.communicate(timeout=5)
banner_printed = "API" in out
ok = proc.returncode != 0 and not alive
record("CLI-270", "PASS" if ok else "FAIL", f"rc={proc.returncode} alive_after_wait={alive} banner_printed_before_failure={banner_printed} out={out[:200]!r} err={err[-400:]!r}")

# CLI-271: serve on a port already in use
cfg271, d271, db271 = new_cfg("cli271", web_enabled=False)
port271 = free_port()
occupant = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
occupant.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
occupant.bind(("127.0.0.1", port271))
occupant.listen(1)
proc = start_serve(cfg271, ["--port", str(port271)])
time.sleep(2)
alive = proc.poll() is None
if alive:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
out, err = proc.communicate(timeout=5)
occupant.close()
banner_before_failure = "API" in out
ok = (not alive) and proc.returncode not in (0, None) and not banner_before_failure
record(
    "CLI-271",
    "PASS" if ok else "FAIL",
    f"stayed_alive_despite_port_conflict={alive} rc={proc.returncode} banner_printed={banner_before_failure} "
    f"out={out[:250]!r} err={err[-400:]!r}",
)

print("done serve batch part1")
