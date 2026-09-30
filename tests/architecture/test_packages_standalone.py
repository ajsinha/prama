"""The SDK, the kernel and the agent are their own packages, and never reach into the server.

**The kernel** (``kernel/``, ``prama_kernel``) is the deterministic code the
server and a remote agent share. It imports only the standard library — never
``prama``, ``prama_sdk`` or ``prama_agent`` — or the agent would drag the server
onto every machine it runs on; its wheel needs no dependency at all.

**The SDK** is what clients install.

``prama-sdk`` (``sdk/``, imported as ``prama_sdk``) is what clients install. If it
imported the server — for an error class, the version, the configuration
loader — installing it would install all of Prama: FastAPI, SQLAlchemy, DuckDB,
the console. So these fail the build:

* an SDK module importing ``prama``, or a server module importing ``prama_sdk``;
* the SDK failing to import, or to work, with ``prama`` made unimportable;
* the SDK's wheel carrying anything but ``prama_sdk``, or depending on more
  than ``httpx`` and ``PyYAML``;
* a server error code the SDK would raise as the wrong class.

**The agent** (``agent/``, ``prama_agent``) is the daemon that runs on customer
machines beside the data. It depends on the kernel and the SDK and nothing of the
server, so these fail the build too: an agent module importing ``prama``; a
server module importing ``prama_agent``; the daemon failing to import, build and
run a cycle with ``prama`` unimportable; its wheel carrying anything but
``prama_agent`` or requiring more than the kernel, the SDK and PyYAML.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / "sdk" / "src" / "prama_sdk"
SERVER = ROOT / "src" / "prama"
#: What the SDK may depend on, and nothing else.
ALLOWED_REQUIREMENTS = {"httpx", "pyyaml"}
KERNEL = ROOT / "kernel" / "src" / "prama_kernel"
#: The kernel may import the standard library and nothing of Prama but itself.
NOT_FOR_THE_KERNEL = ("prama", "prama_sdk", "prama_agent")
AGENT = ROOT / "agent" / "src" / "prama_agent"
#: What the agent may depend on outside its optional extras.
ALLOWED_AGENT_REQUIREMENTS = {"prama-kernel", "prama-sdk", "pyyaml"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_the_sdk_is_not_inside_the_server() -> None:
    assert SDK.is_dir(), "the SDK should live in sdk/src/prama_sdk"
    assert not (SERVER / "sdk").exists(), "src/prama/sdk would ship the SDK inside the server"


def test_no_sdk_module_imports_the_server() -> None:
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in sorted(SDK.rglob("*.py"))
        for name in _imports(path)
        if name == "prama" or name.startswith("prama.")
    ]
    assert not offenders, "\n".join(offenders)


def test_no_server_module_imports_the_sdk() -> None:
    """The server serves the API; it does not call itself through a client."""
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in sorted(SERVER.rglob("*.py"))
        for name in _imports(path)
        if name == "prama_sdk" or name.startswith("prama_sdk.")
    ]
    assert not offenders, "\n".join(offenders)


#: Run in a fresh interpreter with the server made unimportable, exactly as on a
#: client machine where it is not installed.
_ISOLATED = r"""
import sys, importlib.abc

class NoServer(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "prama" or name.startswith("prama."):
            raise ImportError(f"the SDK imported {name}, which a client does not have")
        return None

sys.meta_path.insert(0, NoServer())
sys.path.insert(0, sys.argv[1])
import prama_sdk as prama

client = prama.Client("http://127.0.0.1:9")          # binds every namespace
assert client.datasets and client.runs and client.evidence
try:
    client.system.health()
except prama.ServerUnavailable as error:
    assert error.code == "SDK.SERVER_UNAVAILABLE"
else:
    raise SystemExit("an unreachable server did not raise ServerUnavailable")
client.close()
open(sys.argv[2], "w").write("server:\n  host: 0.0.0.0\n  port: 6123\n")
assert prama.server_url(sys.argv[2]) == "http://127.0.0.1:6123"
print("standalone", prama.__version__)
"""


def test_the_sdk_works_with_the_server_unimportable(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _ISOLATED, str(SDK.parent), str(tmp_path / "application.yaml")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("standalone ")


def test_the_isolation_can_fail(tmp_path: Path) -> None:
    """The counterfactual: a module importing the server is refused in that interpreter."""
    probe = tmp_path / "leaky.py"
    probe.write_text("import prama.version\n")
    script = _ISOLATED.split("import prama_sdk as prama")[0] + "import leaky\n"
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode != 0 and "a client does not have" in result.stderr


def test_the_wheel_holds_only_the_sdk_and_needs_only_its_own_dependencies(
    tmp_path: Path,
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed, so the SDK wheel was NOT built and checked")
    subprocess.run(
        [uv, "build", "--wheel", str(ROOT / "sdk"), "--out-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    (wheel,) = tmp_path.glob("prama_sdk-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        requires = [
            line.split(":", 1)[1].strip()
            for line in archive.read(metadata).decode().splitlines()
            if line.startswith("Requires-Dist:")
        ]
    packaged = {name.split("/")[0] for name in names if not name.startswith("prama_sdk-")}
    assert packaged == {"prama_sdk"}, packaged
    required = {
        requirement.split(">")[0].split("=")[0].split("[")[0].split(";")[0].strip().lower()
        for requirement in requires
    }
    assert required == ALLOWED_REQUIREMENTS, required


def test_every_server_error_reaches_the_client_as_the_class_for_its_status() -> None:
    """The SDK mirrors the taxonomy it cannot import; this keeps the mirror true."""
    from prama_sdk import errors as client

    from prama.api.errors import status_for
    from prama.core.errors import PramaError

    expected = {401: client.UnauthorisedError, 403: client.ForbiddenError,
                404: client.NotFoundError, 409: client.ConflictError,
                422: client.ValidationError, 429: client.RateLimitedError}  # fmt: skip
    pending: list[type[PramaError]] = [PramaError]
    checked = 0
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        try:
            instance = cls("probe", remedy="probe")
        except TypeError:
            continue  # a subclass with its own constructor; its status is checked where raised
        status = status_for(instance)
        want = expected.get(status, client.ServerError if status >= 500 else client.PramaError)
        got = client.error_for(instance.code, status)
        assert issubclass(got, want), f"{cls.__qualname__} ({instance.code}, {status}) -> {got}"
        checked += 1
    assert checked >= 10


def test_no_kernel_module_imports_the_server_the_sdk_or_the_agent() -> None:
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in sorted(KERNEL.rglob("*.py"))
        for name in _imports(path)
        if any(name == top or name.startswith(top + ".") for top in NOT_FOR_THE_KERNEL)
    ]
    assert not offenders, "\n".join(offenders)


def test_the_kernel_imports_with_the_server_unimportable() -> None:
    """Every kernel module, in an interpreter where prama is blocked."""
    modules = sorted(
        ".".join(path.relative_to(KERNEL.parent).with_suffix("").parts).removesuffix(".__init__")
        for path in KERNEL.rglob("*.py")
    )
    script = _ISOLATED.split("import prama_sdk as prama")[0] + (
        "import importlib\n"
        f"for name in {modules!r}:\n    importlib.import_module(name)\n"
        "print('kernel', len(" + repr(modules) + "))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(KERNEL.parent)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("kernel ")


def test_the_server_aliases_are_the_kernel_modules() -> None:
    """One copy: the server's old import paths are the kernel's modules, not copies."""
    import prama_kernel.delegates.host
    import prama_kernel.errors
    import prama_kernel.judge

    import prama.backend.execute
    import prama.core.errors
    import prama.delegates.host

    assert prama.core.errors is prama_kernel.errors
    assert prama.backend.execute is prama_kernel.judge
    assert prama.delegates.host is prama_kernel.delegates.host


def test_the_kernel_wheel_holds_only_the_kernel_and_needs_nothing(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed, so the kernel wheel was NOT built and checked")
    subprocess.run(
        [uv, "build", "--wheel", str(ROOT / "kernel"), "--out-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    (wheel,) = tmp_path.glob("prama_kernel-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        requires = [
            line
            for line in archive.read(metadata).decode().splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
    assert {name.split("/")[0] for name in names if not name.startswith("prama_kernel-")} == {
        "prama_kernel"
    }
    assert requires == [], requires


# -- the agent ---------------------------------------------------------------


def test_no_agent_module_imports_the_server() -> None:
    assert AGENT.is_dir(), "the agent should live in agent/src/prama_agent"
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in sorted(AGENT.rglob("*.py"))
        for name in _imports(path)
        if name == "prama" or name.startswith("prama.")
    ]
    assert not offenders, "\n".join(offenders)


def test_no_server_module_imports_the_agent() -> None:
    """The server hands out work; it never runs the agent's code."""
    offenders = [
        f"{path.relative_to(ROOT)} imports {name}"
        for path in sorted(SERVER.rglob("*.py"))
        for name in _imports(path)
        if name == "prama_agent" or name.startswith("prama_agent.")
    ]
    assert not offenders, "\n".join(offenders)
    assert not (SERVER / "agent" / "runner.py").exists(), "the runner is the agent's"


#: Run where the server cannot be imported: build the daemon from a
#: configuration, against a real SQLite file, and run one full cycle against a
#: fake server. What a customer's machine does, minus the network.
_AGENT_CYCLE = r"""
import sqlite3
from pathlib import Path
for extra in sys.argv[2:4]:
    sys.path.insert(0, extra)
work = Path(sys.argv[4])
db = work / "w.db"
connection = sqlite3.connect(db)
connection.executescript("CREATE TABLE t (a INTEGER); INSERT INTO t VALUES (1), (NULL);")
connection.commit()
connection.close()

import prama_agent
from prama_agent import Daemon, Identity, parse_config
from prama_kernel.agent.protocol import Assignment, Receipt, Report

config = parse_config({
    "server": "https://prama.example.com",
    "state_dir": str(work / "state"),
    "sources": {"t": {"engine": "sqlite", "path": str(db)}},
    "residency": {"samples": "withhold"},
})
plan = {"assertion_kind": "predicate", "scope": {"dataset": "t"},
        "metrics": [{"name": "scanned_rows", "agg": "count"},
                    {"name": "violating_rows", "agg": "count_if"}],
        "threshold": {"metric": "violating_rows", "op": "<=", "value": 0}}
work_item = Assignment(plan_id="p1", dataset="t", binding="t", engine="sqlite",
    metric_query="SELECT COUNT(*) AS scanned_rows, "
                 "SUM(CASE WHEN a IS NULL THEN 1 ELSE 0 END) AS violating_rows FROM t",
    metric_names=("scanned_rows", "violating_rows"), plan=plan)

class Link:
    reports = []
    queue = [work_item]  # claimed once, as the server claims it
    def hello(self, hello, *, key):
        handed, self.queue = tuple(self.queue), []
        return Receipt(assignments=handed).to_dict()
    def report(self, report, *, key):
        self.reports.append(Report.from_dict(report))
        return Receipt(accepted_through=self.reports[-1].last_sequence).to_dict()
    def close(self):
        pass

identity = Identity(agent_id="a1", key_hex="00" * 32, zone="z", server="https://prama.example.com")
link = Link()
assert Daemon(config, identity, link).run(once=True, handle_signals=False) == 0
(report,) = link.reports
assert [r.verdict for r in report.records] == ["fail"], report.records
assert not [m for m in sys.modules if m == "prama" or m.startswith("prama.")]
print("agent", prama_agent.__version__)
"""


def test_the_agent_runs_a_cycle_with_the_server_unimportable(tmp_path: Path) -> None:
    script = _ISOLATED.split("import prama_sdk as prama")[0] + _AGENT_CYCLE
    paths = [str(AGENT.parent), str(KERNEL.parent), str(SDK.parent), str(tmp_path)]
    result = subprocess.run(
        [sys.executable, "-c", script, *paths],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("agent ")


def test_the_agent_wheel_holds_only_the_agent_and_needs_only_the_kernel_and_sdk(
    tmp_path: Path,
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed, so the agent wheel was NOT built and checked")
    subprocess.run(
        [uv, "build", "--wheel", str(ROOT / "agent"), "--out-dir", str(tmp_path)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    (wheel,) = tmp_path.glob("prama_agent-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        entry_points = next(n for n in names if n.endswith(".dist-info/entry_points.txt"))
        requires = [
            line.split(":", 1)[1].strip()
            for line in archive.read(metadata).decode().splitlines()
            if line.startswith("Requires-Dist:") and "extra ==" not in line
        ]
        scripts = archive.read(entry_points).decode()
    packaged = {name.split("/")[0] for name in names if not name.startswith("prama_agent-")}
    assert packaged == {"prama_agent"}, packaged
    required = {
        requirement.split(">")[0].split("=")[0].split("[")[0].split(";")[0].strip().lower()
        for requirement in requires
    }
    assert required == ALLOWED_AGENT_REQUIREMENTS, required
    assert "prama-agent = prama_agent.cli:main" in scripts
