"""The delegate sandbox, tested with delegates that misbehave.

Each delegate here passes admission: it imports nothing the scan refuses, and it
behaves on the admission probes. It misbehaves only when a control asks it to
(``mode = 'go'``), which is what a delegate written to get past admission would
do. What it then tries to do (open a socket through asyncio, start a
process through multiprocessing, load a native library through ctypes, sleep
past its deadline, eat memory, spin) is what the sandbox exists to stop, and
each test asserts that it was stopped and said so.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.delegates import sandbox as sandbox_module
from prama.delegates.host import host_from_config
from prama.delegates.sandbox import isolation_in_force, network_isolation
from prama.ir.resolve import resolved
from prama.pql import parse_control

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="POSIX resource limits")

HEAD = """
from collections.abc import Iterable, Mapping
from typing import Any

from prama.delegates import DqDelegate, Measurement, Parameter
{imports}


class Hostile(DqDelegate):
    name = "hostile.{name}"
    version = "1"
    requires = ("id",)
    parameters = (Parameter("mode", "text", "calm"),)
    summary = "misbehaves when asked"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        scanned = len(list(rows))
        if params["mode"] == "go":
{body}
        return Measurement(scanned=scanned, violating=0)
"""

BEHAVIOURS: dict[str, tuple[str, str]] = {
    "network": (
        "import asyncio",
        "            async def go() -> None:\n"
        "                await asyncio.open_connection('127.0.0.1', 9)\n"
        "            asyncio.run(go())",
    ),
    "process": (
        "import multiprocessing",
        "            worker = multiprocessing.Process(target=print)\n            worker.start()",
    ),
    "native": ("import ctypes", "            ctypes.CDLL(None)"),
    "sleep": ("import threading", "            threading.Event().wait(60)"),
    "memory": ("", "            hoard = bytearray(3 << 30)\n            del hoard"),
    "spin": ("", "            while True:\n                pass"),
}


def _host(tmp_path: Path, behaviour: str, **options: Any) -> Any:
    imports, body = BEHAVIOURS[behaviour]
    directory = tmp_path / behaviour
    directory.mkdir()
    (directory / f"hostile_{behaviour}.py").write_text(
        HEAD.format(imports=imports, name=behaviour, body=body), encoding="utf-8"
    )
    host = host_from_config(
        {"delegates": {"paths": [str(directory)], "entry_points": False, "sandbox": True}}
    )
    assert not host.registry.refused, host.registry.refused  # it passed admission
    for key, value in options.items():
        setattr(host, key, value)
    return host


def _run(host: Any, behaviour: str) -> Any:
    plan = resolved(parse_control(f"CHECK t USING DELEGATE 'hostile.{behaviour}@1' (mode = 'go')"))
    return host.measure_plan(plan, [{"id": 1}])


@pytest.mark.parametrize(
    ("behaviour", "refusal"),
    [
        ("network", "refuses socket"),
        ("process", "refuses"),
        ("native", "refuses ctypes.dlopen"),
    ],
)
def test_what_a_delegate_has_no_use_for_is_refused(
    tmp_path: Path, behaviour: str, refusal: str
) -> None:
    host = _host(tmp_path, behaviour, timeout_s=20)
    with pytest.raises(ValidationError, match=refusal):
        _run(host, behaviour)


def test_a_sleeping_delegate_is_stopped_at_its_deadline(tmp_path: Path) -> None:
    """Sleeping uses no CPU, so the CPU limit never fires. The host's own deadline
    covers both pipes: before this, the host waited on the answer for ever."""
    host = _host(tmp_path, "sleep", timeout_s=2)
    started = time.monotonic()
    with pytest.raises(ValidationError, match="ran longer than 2s"):
        _run(host, "sleep")
    assert time.monotonic() - started < 15


def test_memory_is_limited(tmp_path: Path) -> None:
    host = _host(tmp_path, "memory", memory_mb=512, timeout_s=20)
    with pytest.raises(ValidationError, match=r"MemoryError|failed in its sandbox"):
        _run(host, "memory")


def test_a_spinning_delegate_is_stopped(tmp_path: Path) -> None:
    host = _host(tmp_path, "spin", timeout_s=2)
    started = time.monotonic()
    with pytest.raises(ValidationError):
        _run(host, "spin")
    assert time.monotonic() - started < 15


def test_the_worker_gets_no_secrets_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent's environment carries DSNs and keys; the worker's does not."""
    monkeypatch.setenv("PRAMA_DATABASE_DSN", "postgresql://user:secret@db/prama")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-for-delegates")
    seen: dict[str, str] = {}
    real = subprocess.Popen

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs.get("env") or {})
        return real(*args, **kwargs)

    monkeypatch.setattr(sandbox_module.subprocess, "Popen", spy)
    good = Path(__file__).resolve().parents[1] / "fixtures" / "delegates" / "good"
    host = host_from_config({"delegates": {"paths": [str(good)], "entry_points": False}})
    plan = resolved(parse_control("CHECK payments USING DELEGATE 'test.over_limit@2'"))
    result = host.measure_plan(plan, [{"id": 1, "amount": 1, "booked": "2026-09-01"}])
    assert result.metrics["violating_rows"] == 0
    assert seen, "the worker was not started"
    assert not {"PRAMA_DATABASE_DSN", "OPENAI_API_KEY"} & set(seen)
    assert seen["HOME"] != os.environ.get("HOME")
    assert "audit hook" in result.parameters["delegate_isolation"]


def test_the_evidence_says_which_isolation_applied() -> None:
    assert isolation_in_force(False) == "none: in process"
    described = isolation_in_force(True)
    assert ("network namespace" in described) is bool(network_isolation())
