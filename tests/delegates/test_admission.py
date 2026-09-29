"""Admission in the sandbox: the server never imports a configured delegate.

With ``delegates.sandbox: true`` (the default), configured paths and installed
entry points are scanned, imported and probed by a sandboxed worker, one per
file, and the server registers stand-ins from their descriptions. These tests
hold the three things that buys: nothing is imported here, a delegate that
hangs its admission is refused alone, and the audit hook is sealed before a
delegate's import-time code runs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest

from prama.delegates.host import host_from_config
from prama.ir.resolve import resolved
from prama.pql import parse_control

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="POSIX resource limits")

GOOD = (
    Path(__file__).resolve().parents[1] / "fixtures" / "delegates" / "good" / "threshold_count.py"
)

TEMPLATE = """
from collections.abc import Iterable, Mapping
from typing import Any

from prama.delegates import DqDelegate, Measurement
{imports}
{top}


class Awkward(DqDelegate):
    name = "awkward.{name}"
    version = "1"
    requires = ("id",)
    summary = "awkward at admission"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        scanned = len(list(rows))
{body}
        return Measurement(scanned=scanned, violating=0)
"""


def _write(directory: Path, name: str, *, imports: str = "", top: str = "", body: str = "") -> None:
    (directory / f"awkward_{name}.py").write_text(
        TEMPLATE.format(imports=imports, top=top, name=name, body=body or "        pass"),
        encoding="utf-8",
    )


def _host(directory: Path, **section: object) -> object:
    return host_from_config(
        {"delegates": {"paths": [str(directory)], "entry_points": False, **section}}
    )


def test_the_server_never_imports_a_configured_delegate(tmp_path: Path) -> None:
    shutil.copy(GOOD, tmp_path / "isolated_threshold_count.py")
    host = _host(tmp_path)
    admitted = host.registry.get("test.over_limit")
    assert admitted.sandbox_only
    assert "prama_delegate_isolated_threshold_count" not in sys.modules
    # ...and it still runs, in the sandbox, with the same identity as in process.
    plan = resolved(parse_control("CHECK payments USING DELEGATE 'test.over_limit@2'"))
    result = host.measure_plan(plan, [{"id": 1, "amount": 500, "booked": "2026-09-01"}])
    assert result.metrics["violating_rows"] == 1
    in_process = _host(tmp_path, sandbox=False).registry.get("test.over_limit")
    assert admitted.implementation_hash == in_process.implementation_hash


def test_a_delegate_that_hangs_its_admission_is_refused_alone(tmp_path: Path) -> None:
    _write(
        tmp_path, "sleeper", imports="import threading", body="        threading.Event().wait(60)"
    )
    shutil.copy(GOOD, tmp_path / "neighbour.py")
    started = time.monotonic()
    host = _host(tmp_path, timeout=3)
    assert time.monotonic() - started < 20
    assert "admission ran longer than 3s" in host.registry.refused["awkward_sleeper.py"]
    assert host.registry.get("test.over_limit").sandbox_only  # the neighbour still loaded


def test_import_time_code_runs_under_the_seal(tmp_path: Path) -> None:
    """An event loop opens a socket pair: refused while the module is imported."""
    _write(tmp_path, "loop", imports="import asyncio", top="LOOP = asyncio.new_event_loop()")
    host = _host(tmp_path)
    reason = " ".join(host.registry.refused.values())
    assert "refuses socket" in reason, host.registry.refused
    with pytest.raises(Exception, match="not installed"):
        host.registry.get("awkward.loop")


def test_without_the_sandbox_admission_stays_in_process(tmp_path: Path) -> None:
    shutil.copy(GOOD, tmp_path / "inprocess_threshold_count.py")
    host = _host(tmp_path, sandbox=False)
    assert not host.registry.get("test.over_limit").sandbox_only
    assert "prama_delegate_inprocess_threshold_count" in sys.modules
