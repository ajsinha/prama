"""The case studies still run — against a real Prama server, through the SDK.

A study is a client of *your* running Prama: it reads the server's address from
an ``application.yaml``, signs in, creates an estate of its own, and does
everything through `prama.sdk`. So the only faithful test is the one a person
would do: start a server, and run each study against it with ``--config``.

History worth keeping. QA once found all four studies dead on committed code
(a harness nobody had updated, and a console started inside a running event
loop), because **nothing under `tests/` exercised `case-studies/`**. Later the
studies started a second server of their own even when one was already
running, which made no sense to the person running them. Both are what these
tests exist to prevent.

These are slow — each study builds its data and the server runs its estate —
so they are marked and excluded from the default run. ``pytest -m casestudy``
is the gate that matters before a release.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
STUDIES = ROOT / "case-studies"

pytestmark = pytest.mark.casestudy

#: What a study may not do to reach Prama: open its database, run controls
#: in-process, or start a server. It is a client, through the SDK.
FORBIDDEN_IMPORTS = ("prama.db", "prama.execute", "prama.api", "uvicorn", "prama.derive")


def study_directories() -> list[Path]:
    return sorted(p for p in STUDIES.glob("0*") if (p / "run.py").is_file())


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A real Prama server, as a separate process, and the configuration naming it.

    Its database is a scratch file, so running this never touches the
    developer's own; it may read the studies' workspaces (``runs.roots``) and
    nothing else; the bootstrap admin exists because the estate starts empty.
    """
    root = tmp_path_factory.mktemp("server")
    port = _free_port()
    config = root / "application.yaml"
    config.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {root / 'prama.db'}\n"
        f"  schema_dir: {ROOT / 'schema'}\n"
        "security:\n"
        "  session_secret: case-study-test-secret-not-a-real-one-0123456789\n"
        "  cookies_https_only: false\n"
        f"server:\n  host: 127.0.0.1\n  port: {port}\n"
        f"runs:\n  roots: [{STUDIES}]\n"
        "logging:\n  level: WARNING\n",
        encoding="utf-8",
    )
    # The installed command beside this interpreter: what a person runs.
    executable = Path(sys.executable).with_name("prama")
    if not executable.exists():
        pytest.skip(f"no prama command beside {sys.executable}; install the package first")
    prama = [str(executable), "--config", str(config)]
    subprocess.run([*prama, "db", "init"], check=True, capture_output=True, timeout=120)
    log = (root / "server.log").open("w")
    process = subprocess.Popen([*prama, "serve"], stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/livez", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(
                    "the Prama server did not start:\n" + (root / "server.log").read_text()
                )
            time.sleep(0.25)
        yield config
    finally:
        process.terminate()
        process.wait(timeout=20)
        log.close()


def test_there_are_studies_to_run() -> None:
    """Anti-vacuity: a glob matching nothing would pass every test below by absence."""
    assert len(study_directories()) >= 8


@pytest.mark.parametrize("study", study_directories(), ids=lambda p: p.name)
def test_it_runs_against_the_server(study: Path, server: Path) -> None:
    """Run it the way the README says, against a running server, and require exit 0.

    Twice: each run makes an estate of its own, so a rerun must start clean
    without deleting the first run's evidence.
    """
    for attempt in (1, 2):
        result = subprocess.run(
            [sys.executable, "run.py", "--config", str(server)],
            cwd=study,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        assert result.returncode == 0, (
            f"{study.name} (run {attempt}) exited {result.returncode}\n"
            f"--- stdout (tail) ---\n{result.stdout[-2500:]}\n"
            f"--- stderr (tail) ---\n{result.stderr[-2500:]}"
        )
        assert "Evidence chain:" in result.stdout and "verified" in result.stdout


@pytest.mark.parametrize("study", study_directories(), ids=lambda p: p.name)
def test_a_study_reaches_prama_only_through_the_sdk(study: Path) -> None:
    """No study, and nothing it shares, opens Prama's database or starts a server.

    Read rather than run: an import of the database layer or of uvicorn is the
    shape of both old defects, and it is visible without executing anything.
    """
    files = [study / "run.py", *sorted((STUDIES / "_common").glob("*.py"))]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(FORBIDDEN_IMPORTS), (
                    f"{path.relative_to(ROOT)} imports {name}: a study reaches Prama "
                    "only through prama.sdk, against the running server"
                )


def test_the_import_rule_can_fail(tmp_path: Path) -> None:
    """The counterfactual: the rule above catches the old harness's shape."""
    offender = tmp_path / "run.py"
    offender.write_text("from prama.db import Database\n", encoding="utf-8")
    tree = ast.parse(offender.read_text(encoding="utf-8"))
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert any(str(m).startswith(FORBIDDEN_IMPORTS) for m in modules)
