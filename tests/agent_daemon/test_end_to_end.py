"""A real server, the real ``prama-agent`` command, and a finding in the ledger.

Three processes, as in production: the server; an administrator scripting it
with the SDK; and the agent daemon, installed as its own package, enrolling
with a one-time token and running against a SQLite file only it reads. What is
asserted is the outcome a person would check: the planted defect is a ``fail``
in the server's evidence, the chain verifies, and a revoked agent stops for good.

Slow (a server starts), so it runs with the case studies: ``pytest -m casestudy``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import prama_sdk as prama
import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(sys.executable).parent
ZONE = "eu-frankfurt"
PASSWORD = "end-to-end-password-1"

pytestmark = pytest.mark.casestudy


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _command(name: str) -> str:
    executable = BIN / name
    if not executable.exists():
        pytest.skip(f"no {name} command beside {sys.executable}; install the packages first")
    return str(executable)


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("server")
    port = _free_port()
    config = root / "application.yaml"
    config.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {root / 'prama.db'}\n  schema_dir: {ROOT / 'schema'}\n"
        "security:\n  session_secret: end-to-end-secret-not-a-real-one-0123456789\n"
        "  cookies_https_only: false\n"
        f"server:\n  host: 127.0.0.1\n  port: {port}\n"
        "logging:\n  level: WARNING\n",
        encoding="utf-8",
    )
    command = [_command("prama"), "--config", str(config)]
    subprocess.run([*command, "db", "init"], check=True, capture_output=True, timeout=120)
    log = (root / "server.log").open("w")
    process = subprocess.Popen([*command, "serve"], stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(url + "/livez", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(
                    "the server did not start:\n" + (root / "server.log").read_text()
                )
            time.sleep(0.25)
        yield url
    finally:
        process.terminate()
        process.wait(timeout=20)
        log.close()


def _book(path: Path) -> None:
    """The customer's data, which only the agent reads: one currency is not in the list."""
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE trades (trade_id TEXT, ccy TEXT)")
        rows = [(f"T{i}", "USD" if i % 2 else "EUR") for i in range(1, 20)] + [("T20", "XXX")]
        db.executemany("INSERT INTO trades VALUES (?, ?)", rows)


def test_an_agent_daemon_finds_a_defect_the_server_cannot_see(server: str, tmp_path: Path) -> None:
    admin = prama.connect(server, username="admin", password="prama-dev-admin", tenant="default")
    trades = admin.datasets.declare(
        "Trades",
        description="Executed trades.",
        criticality=3,
        grain={"attributes": ["trade_id"], "statement": "one row per trade"},
    )
    admin.datasets.add_attribute(trades["id"], "trade_id", optionality="mandatory")
    admin.datasets.add_attribute(trades["id"], "ccy", codelist=["USD", "EUR", "GBP"])
    admin.derive.dataset(trades["id"], declare=True, accept=True, reason="reviewed")

    token = admin.fleet.issue_token(ZONE, name="frankfurt-01")["token"]
    state = tmp_path / "state"
    enrolled = subprocess.run(
        [
            _command("prama-agent"),
            "enrol",
            "--server",
            server,
            "--token",
            token,
            "--name",
            "frankfurt-01",
            "--state",
            str(state),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert enrolled.returncode == 0, enrolled.stdout + enrolled.stderr
    (agent,) = [a for a in admin.fleet.agents() if a["name"] == "frankfurt-01"]
    assert agent["zone"] == ZONE and agent["state"] == "active"

    book = tmp_path / "book.db"
    _book(book)
    config = tmp_path / "agent.yaml"
    config.write_text(
        f"server:\n  url: {server}\n"
        f"state_dir: {state}\n"
        f"sources:\n  trades:\n    engine: sqlite\n    path: {book}\n"
        "residency:\n  samples: withhold\n"
        "poll:\n  min_seconds: 1\n  max_seconds: 5\n"
        "logging:\n  level: WARNING\n",
        encoding="utf-8",
    )
    dispatched = admin.fleet.dispatch(ZONE, engine="sqlite", datasets=["trades"])
    assert len(dispatched["queued"]) >= 1, dispatched

    ran = subprocess.run(
        [_command("prama-agent"), "run", "--config", str(config), "--once"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr

    records = admin.evidence.latest()
    latest = list(records.values()) if isinstance(records, dict) else list(records)
    failing = [r for r in latest if r.get("verdict") == "fail" and r.get("dataset") == "trades"]
    assert failing, [
        (r.get("dataset"), r.get("verdict"), r.get("metrics"), r.get("detail")) for r in latest
    ]  # the XXX currency, found beside the data
    assert any((r.get("metrics") or {}).get("violating_rows") == 1 for r in failing), failing
    assert admin.evidence.verify()["intact"]

    # Revoked: the next run is refused for good, and the daemon says so (exit 3).
    admin.fleet.revoke(agent["id"])
    refused = subprocess.run(
        [_command("prama-agent"), "run", "--config", str(config), "--once"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert refused.returncode == 3, refused.stdout + refused.stderr
    admin.close()
