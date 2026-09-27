"""`run_prama_web.py --init-secret` is safe to repeat.

It used to exit 1 when the local file already had a secret, so running the
documented command twice looked like a failure. Now it keeps the secret it
finds, never replaces it (rotating would sign everybody out), and carries on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]


def _launcher() -> Any:
    spec = importlib.util.spec_from_file_location("run_prama_web", REPO / "run_prama_web.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_it_writes_a_secret_once_and_keeps_it_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = _launcher()
    local = tmp_path / "application.local.yaml"
    monkeypatch.setattr(launcher, "LOCAL_CONFIG", local)

    written = launcher._write_local_secret()
    assert written in local.read_text()  # the control: a fresh file gets one
    before = local.read_text()

    assert launcher._write_local_secret() == "kept"
    assert local.read_text() == before  # not replaced, not appended twice
