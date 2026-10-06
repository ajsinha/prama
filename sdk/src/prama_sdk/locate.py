"""Finding the Prama server from the configuration file it reads.

The server reads ``config/application.yaml`` (or the file ``PRAMA_CONFIG``
names), overlays ``application.local.yaml`` beside it, and lets
``PRAMA_SERVER__HOST`` / ``PRAMA_SERVER__PORT`` from the environment override
both. This does the same for the three settings a client needs —
``server.host``, ``server.port`` and ``server.tls`` — so a script finds the
server its operator configured, without importing the server.

It is deliberately small: three keys, YAML or ``.properties``, the local
overlay, the environment, and ``${VAR:default}`` in those values. It is not
the server's configuration engine and does not try to be; a value it cannot
read falls back to 127.0.0.1:5900, where a server on this machine is reached
whatever interfaces it binds.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from prama_sdk.errors import ValidationError

DEFAULT_CONFIG = Path("config") / "application.yaml"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5900
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.\-]*)(?::([^}]*))?\}")


def _read(path: Path) -> dict[str, Any]:
    """The server section of one YAML or ``.properties`` file, flattened."""
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ValidationError(
                f"{path} is not valid YAML",
                remedy="Fix the file, or pass base_url= instead of config=.",
                context={"path": str(path), "detail": str(exc)[:200]},
            ) from exc
        server = data.get("server") if isinstance(data, dict) else None
        return (
            {f"server.{k}": v for k, v in (server or {}).items()}
            if isinstance(server, dict)
            else {}
        )
    found: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!", "//")):
            continue
        for separator in ("=", ":"):
            if separator in line:
                key, value = line.split(separator, 1)
                if key.strip().startswith("server."):
                    found[key.strip()] = value.strip()
                break
    return found


def _resolve(value: Any, environ: dict[str, str]) -> str:
    """``${VAR:default}`` from the environment, as the server would resolve it."""
    text = "" if value is None else str(value)
    return _PLACEHOLDER.sub(lambda m: environ.get(m.group(1), m.group(2) or ""), text)


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "yes", "on", "1", "y", "t")


def server_url(config: str | Path | None = None, *, environ: dict[str, str] | None = None) -> str:
    """The URL of the server a configuration file describes.

    ``config`` is an ``application.yaml`` (or ``.properties``); by default the
    one ``PRAMA_CONFIG`` names, else ``config/application.yaml`` under the
    working directory. A server bound to every interface (``0.0.0.0``) is
    reached on loopback.
    """
    env = dict(os.environ) if environ is None else environ
    path = Path(config or env.get("PRAMA_CONFIG") or DEFAULT_CONFIG).expanduser()
    if config is not None and not path.is_file():
        raise ValidationError(
            f"no configuration file at {path}",
            remedy="Pass the application.yaml of the server to use, or base_url=.",
            context={"path": str(path)},
        )
    settings = _read(path)
    settings.update(_read(path.with_name(f"{path.stem}.local{path.suffix}")))
    for key in ("host", "port", "tls"):
        override = env.get(f"PRAMA_SERVER__{key.upper()}")
        if override is not None:
            settings[f"server.{key}"] = override

    host = _resolve(settings.get("server.host", DEFAULT_HOST), env) or DEFAULT_HOST
    if host in ("0.0.0.0", "::"):  # a bind address, reached on loopback
        host = DEFAULT_HOST
    port_text = _resolve(settings.get("server.port", DEFAULT_PORT), env) or str(DEFAULT_PORT)
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValidationError(
            f"server.port in {path} is {port_text!r}, not a port number",
            remedy="Set server.port to a number, or pass base_url=.",
            context={"path": str(path)},
        ) from exc
    scheme = "https" if _truthy(_resolve(settings.get("server.tls", "false"), env)) else "http"
    return f"{scheme}://{host}:{port}"
