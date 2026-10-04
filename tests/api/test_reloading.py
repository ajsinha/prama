"""``--reload`` reloads: the factory a fresh worker imports, and what it reads.

Both ``prama serve --reload`` and ``run_prama_web.py --reload`` accepted the
flag and ignored it, because each handed uvicorn an application object, which
a reloader cannot rebuild. They now hand it ``prama.api.reloading:application``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI

from prama.api import reloading

ROOT = Path(__file__).resolve().parents[2]


def test_the_factory_is_importable_by_the_name_uvicorn_is_given() -> None:
    module, _, name = reloading.FACTORY.partition(":")
    assert getattr(importlib.import_module(module), name) is reloading.application


def test_a_worker_builds_the_application_from_its_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "application.yaml"
    config.write_text("server:\n  port: 6123\nweb:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("PRAMA_CONFIG", str(config))
    app = reloading.application()
    assert isinstance(app, FastAPI)
    assert app.state.config.get_int("server.port") == 6123


def test_it_watches_the_server_and_the_packages_it_is_built_with() -> None:
    watched = set(reloading.watched_directories())
    assert str(ROOT / "src") in watched
    assert str(ROOT / "kernel" / "src") in watched


def test_set_overrides_are_refused_rather_than_silently_dropped() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = str(probe.getsockname()[1])
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "prama.cli.main",
            "--set",
            "logging.level=DEBUG",
            "serve",
            "--reload",
            "--port",
            port,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert done.returncode != 0
    assert "--reload cannot carry --set" in done.stdout + done.stderr
