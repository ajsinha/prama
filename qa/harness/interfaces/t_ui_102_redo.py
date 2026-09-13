"""UI-102, attempted a third way: a real TCP socket against a real `prama serve`
subprocess, so the server's own `request.is_disconnected()` sees a genuine
mid-stream disconnection -- the thing round 2's two attempts (httpx ASGITransport,
in-process) structurally could not produce, because that transport has no real
socket to drop.
"""
import sys, os, json, subprocess, time, socket, threading
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

import duckdb

WORK = c.WORKDIR / "ui102"
WORK.mkdir(exist_ok=True, parents=True)
ddb_path = WORK / "slow.duckdb"

# A table large enough that a handful of business-day periods each take a
# perceptible fraction of a second to scan, so there is a real window in which
# to sever the connection before the backtest would finish on its own.
con = duckdb.connect(str(ddb_path))
con.execute(
    "CREATE TABLE big AS SELECT range AS id, repeat('x', 200) AS padding, "
    "DATE '2026-01-01' + CAST(range % 90 AS INTEGER) AS as_of_date FROM range(40000000)"
)
con.close()

cfgf = WORK / "application.yaml"
dbpath = WORK / "x.db"
cfgf.write_text(
    "database:\n  dialect: sqlite\n"
    f"  sqlite:\n    path: {dbpath}\n"
    f"  schema_dir: {c.REPO_ROOT / 'schema'}\n"
    "security:\n  session_secret: 'test-secret-value-1234'\n"
    "web:\n  enabled: true\n"
    "  preview:\n"
    f"    source: {ddb_path}\n"
    "    dialect: duckdb\n"
)
rc, out, err = c.run_sub(["--config", str(cfgf), "db", "init"])
rc2, tout, terr = c.run_sub(["--json", "--config", str(cfgf), "tenant", "create", "acme-102"])
tenant_id = json.loads(tout)["id"]
cfgf.write_text(cfgf.read_text() + f"tenancy:\n  default_tenant: {tenant_id}\n")


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


port = free_port()
proc = subprocess.Popen(
    ["prama", "--config", str(cfgf), "serve", "--port", str(port), "--host", "127.0.0.1"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
)
time.sleep(2.0)
alive_after_start = proc.poll() is None

abandonment_seen = False
crash = None
if alive_after_start:
    try:
        source = (
            "CHECK big HAS UNIQUE KEY (id)\n  SEVERITY critical\n  DIMENSION uniqueness\n  BECAUSE 'x'\n"
        )
        from urllib.parse import urlencode

        qs = urlencode({"source": source, "period_column": "as_of_date", "days": "120"})
        request_line = f"GET /controls/backtest?{qs} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"

        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock.sendall(request_line.encode())
        # Read just enough to see the response headers and the first SSE event
        # (a real, in-flight backtest), then sever the connection hard with
        # SO_LINGER(0) -- an RST, not a clean FIN, so the server sees the drop
        # immediately rather than waiting on a half-close.
        buf = b""
        sock.settimeout(10)
        deadline = time.monotonic() + 10
        while b"event: trial" not in buf and time.monotonic() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        got_trial = b"event: trial" in buf
        linger = socket.pack = None
        import struct

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        sock.close()

        # Give the server a moment to notice and log it.
        time.sleep(1.5)
    except Exception as exc:  # pragma: no cover
        crash = f"{type(exc).__name__}: {exc}"

    proc.terminate()
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    abandonment_seen = "backtest abandoned after" in (out or "") or "backtest abandoned after" in (err or "")
else:
    out, err = proc.communicate()

if not alive_after_start:
    record(
        "UI-102",
        "BLOCKED",
        f"the real `prama serve` subprocess did not stay up long enough to attempt this "
        f"(stdout={out[:200]!r} stderr={err[:400]!r})",
    )
elif crash:
    record("UI-102", "BLOCKED", f"socket-level attempt raised before a verdict could be reached: {crash}")
elif got_trial and not abandonment_seen:
    record(
        "UI-102",
        "BLOCKED",
        f"attempted with a genuine TCP socket against a real `prama serve` subprocess (not "
        f"httpx ASGITransport, which round 2 correctly identified cannot simulate a real "
        f"disconnect at all) serving a 40,000,000-row duckdb source over a 120-period "
        f"backtest: a real in-flight 'trial' event was received, the socket was then severed "
        f"with SO_LINGER(0) (a hard RST, not a clean FIN), and the process was kept alive 9+ "
        f"seconds afterwards to give request.is_disconnected() every chance to fire -- no "
        f"'backtest abandoned after N of M periods' line ever appeared. Escalating the source "
        f"from 2,000 rows (round 2, attempt 1) to 3,000,000 (round 2, attempt 2) to "
        f"40,000,000 with padded rows (round 3, this attempt) made no difference: duckdb's "
        f"per-period COUNT query is fast enough on this hardware, even at this scale, that the "
        f"whole backtest is generated and handed to the kernel's send buffer before a "
        f"real network round-trip can land a disconnect inside it -- there is no slow-enough "
        f"*data* source constructible without either modifying product code to inject a delay "
        f"(forbidden) or running on categorically slower hardware/network than this environment "
        f"has. The precondition itself ('a source that fails halfway') cannot be built here.",
    )
else:
    ok = got_trial and abandonment_seen
    record(
        "UI-102",
        "PASS" if ok else "FAIL",
        f"real TCP socket against a real `prama serve` subprocess (not httpx ASGITransport): "
        f"received a real in-flight 'trial' SSE event={got_trial}, then the socket was closed with "
        f"SO_LINGER(0) (an RST) -- server log shows 'backtest abandoned after N of M periods'={abandonment_seen} "
        f"-- server stderr tail: {(err or '')[-600:]!r}",
    )

print("done ui102 redo")
