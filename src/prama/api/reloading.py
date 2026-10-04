"""Serving with ``--reload``: the application rebuilt on every code change.

``prama serve --reload`` and ``run_prama_web.py --reload`` both advertised
this and neither did it: each handed uvicorn an application *object*, and a
reloader cannot reload an object. It starts a fresh worker process on every
change and imports the application there, by name. This module is that name,
and the one place both entry points start a reloading server.

A fresh process reads configuration the way any process does: the file named
in ``PRAMA_CONFIG``, its local overlay, and ``PRAMA_*`` environment
overrides. So what an entry point decided (which file, which tenant) is
passed on as those, not as an object the worker could never receive.

For development only: reloading watches the source tree and restarts on
every save, which is what an IDE session wants and no deployment should.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI

#: What the reloader imports in each worker.
FACTORY = "prama.api.reloading:application"


def application() -> FastAPI:
    """The application a reloading worker serves, built from its environment."""
    from prama.api.app import create_app
    from prama.core.config import load_configuration

    return create_app(load_configuration())


def watched_directories() -> list[str]:
    """The source roots a change in which should restart the server.

    The server's own package and the three it is built with (kernel, SDK,
    agent), when running from a checkout; a change anywhere else (tests, docs,
    the data a case study writes) restarts nothing.
    """
    src = Path(__file__).resolve().parents[2]  # .../src
    repo = src.parent
    roots = [src, repo / "kernel" / "src", repo / "sdk" / "src", repo / "agent" / "src"]
    return [str(root) for root in roots if root.is_dir()]


def serve(
    host: str,
    port: int,
    *,
    config_path: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> None:
    """Run a reloading server until interrupted."""
    import uvicorn

    if config_path:
        os.environ["PRAMA_CONFIG"] = str(Path(config_path).resolve())
    os.environ.update(environment or {})
    uvicorn.run(
        FACTORY,
        factory=True,
        reload=True,
        reload_dirs=watched_directories(),
        host=host,
        port=port,
        log_config=None,  # Prama configures logging itself
    )


__all__ = ["FACTORY", "application", "serve", "watched_directories"]
