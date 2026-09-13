import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "mcp"
WORK.mkdir(exist_ok=True, parents=True)


def new_cfg(name):
    d = c.WORKDIR / name
    d.mkdir(exist_ok=True, parents=True)
    cfgf = d / "application.yaml"
    dbpath = d / "x.db"
    cfgf.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {dbpath}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
        "security:\n  session_secret: test-only\n"
    )
    return cfgf, d, dbpath


def rpc(*payloads):
    return "".join(json.dumps(p) + "\n" for p in payloads).encode()


# CLI-261: mcp serve with no tenant refuses with the reason
cfg261, d261, db261 = new_cfg("cli261")
c.run_sub(["--config", str(cfg261), "db", "init"])
proc = subprocess.run(["prama", "--config", str(cfg261), "mcp", "serve"], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.returncode == 1 and b"CLI.NO_TENANT" in proc.stderr and b"cannot say which estate" in proc.stderr
record("CLI-261", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr[:400]!r}")

# CLI-262: mcp serve with a non-existent tenant -- refused at startup, or serves empty lists?
cfg262, d262, db262 = new_cfg("cli262")
c.run_sub(["--config", str(cfg262), "db", "init"])
request = rpc(
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_datasets", "arguments": {}}},
)
proc = subprocess.run(["prama", "--config", str(cfg262), "mcp", "serve", "--tenant", "01NOSUCH"], input=request, capture_output=True, timeout=60, env=os.environ)
refused_at_startup = proc.returncode != 0 and proc.stdout == b""
served_empty_anyway = proc.returncode == 0 and proc.stdout != b""
record(
    "CLI-262",
    "PASS" if refused_at_startup else "FAIL",
    f"rc={proc.returncode} stdout={proc.stdout[:300]!r} stderr={proc.stderr[:300]!r}",
)

# CLI-263: mcp serve checks the schema before serving (no db init run at all)
cfg263, d263, db263 = new_cfg("cli263")
# deliberately skip db init
tcode, tout, _ = None, None, None
proc_no_init = subprocess.run(
    ["prama", "--config", str(cfg263), "mcp", "serve", "--tenant", "01ANYTHING"],
    input=rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_datasets", "arguments": {}}}),
    capture_output=True, timeout=60, env=os.environ,
)
raw_sql_error = b"sqlalchemy" in proc_no_init.stdout.lower() or b"OperationalError" in proc_no_init.stdout or b"no such table" in proc_no_init.stdout.lower()
ok = not raw_sql_error
record(
    "CLI-263",
    "PASS" if ok else "FAIL",
    f"rc={proc_no_init.returncode} stdout={proc_no_init.stdout[:400]!r} stderr={proc_no_init.stderr[:300]!r}",
)

# CLI-264: mcp serve writes its banner to stderr only
cfg264, d264, db264 = new_cfg("cli264")
tcode, tout, _ = c.run_sub(["--json", "--config", str(cfg264), "db", "init"])
tcode2, tout2, _ = c.run_sub(["--json", "--config", str(cfg264), "tenant", "create", "acme-bank"])
tid264 = json.loads(tout2)["id"]
proc = subprocess.run(["prama", "--config", str(cfg264), "mcp", "serve", "--tenant", tid264], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.returncode == 0 and b"prama mcp:" in proc.stderr and b"prama mcp:" not in proc.stdout
record("CLI-264", "PASS" if ok else "FAIL", f"rc={proc.returncode} stdout={proc.stdout[:150]!r} stderr={proc.stderr[:200]!r}")

# CLI-265: mcp tools lists the five read tools, none mutates
code, out, err = c.run(["--json", "mcp", "tools"])
doc = json.loads(out)
names = sorted(t["name"] for t in doc["tools"])
ok = doc["any_mutates"] is False and len(names) == 5
record("CLI-265", "PASS" if ok else "FAIL", f"any_mutates={doc['any_mutates']} names={names}")

# CLI-266: mcp tools marks fenced tools
code, out, err = c.run(["mcp", "tools"])
lines_by_tool = {}
cur = None
for line in out.splitlines():
    stripped = line.strip()
    if stripped and not stripped.startswith(("No tool", "There is none")) and line[:2] in (" !", "  "):
        parts = line.split()
        if len(parts) >= 2 and not line.startswith("    "):
            cur = parts[1] if line[1] in "! " else parts[0]
fenced_expected = {"describe_dataset", "list_controls", "list_incidents"}
not_fenced_expected = {"list_datasets", "trace_lineage"}
bad266 = {}
for name in fenced_expected | not_fenced_expected:
    tool_line = next((l for l in out.splitlines() if name in l and "[fenced]" in l or (name in l and "description" not in l)), None)
    line_for = next((l for l in out.splitlines() if l.strip().startswith(name) or (" " + name + " ") in l), "")
    has_fence = "[fenced]" in line_for
    if name in fenced_expected and not has_fence:
        bad266[name] = "expected [fenced], not found"
    if name in not_fenced_expected and has_fence:
        bad266[name] = "unexpectedly fenced"
ok = not bad266
record("CLI-266", "PASS" if ok else "FAIL", f"bad={bad266} out={out[:600]!r}")

# CLI-267: mcp tools needs no database (config present, database unreachable)
cfg267 = WORK / "unreachable.yaml"
cfg267.write_text(
    "database:\n  dialect: postgres\n"
    "  postgres:\n    host: 127.0.0.1\n    port: 1\n    database: nope\n    user: nope\n    password: nope\n"
    f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
)
proc = subprocess.run(["prama", "--config", str(cfg267), "mcp", "tools"], capture_output=True, timeout=30, env=os.environ)
ok = proc.returncode == 0 and b"list_datasets" in proc.stdout
record("CLI-267", "PASS" if ok else "FAIL", f"rc={proc.returncode} stdout={proc.stdout[:200]!r} stderr={proc.stderr[:200]!r}")

print("done mcp batch")
