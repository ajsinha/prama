"""Prama's configuration subsystem.

    from prama.core.config import load_configuration

    config = load_configuration()                 # defaults + files + env
    dialect = config.get_str("database.dialect")

Layering, weakest to strongest: built-in defaults, ``config/application.yaml``,
the git-ignored ``config/application.local.yaml`` overlay, ``PRAMA_``-prefixed
environment variables, then ``--set`` overrides from the command line.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from pathlib import Path

from prama.core.config.coercion import Coercer
from prama.core.config.configuration import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.config.resolver import PlaceholderResolver
from prama.core.config.sources import (
    CliSource,
    ConfigSource,
    EnvironmentSource,
    MappingSource,
    PropertiesFileSource,
    YamlFileSource,
    deep_merge,
    expand_dotted,
    local_overlay_for,
)

__all__ = [
    "Coercer",
    "Configuration",
    "ConfigurationBuilder",
    "ConfigSource",
    "CliSource",
    "DEFAULTS",
    "DEFAULT_CONFIG_PATH",
    "EnvironmentSource",
    "MappingSource",
    "PlaceholderResolver",
    "PropertiesFileSource",
    "YamlFileSource",
    "deep_merge",
    "expand_dotted",
    "load_configuration",
    "local_overlay_for",
]

#: Overridable with ``PRAMA_CONFIG``; relative to the working directory.
DEFAULT_CONFIG_PATH = "config/application.yaml"


def load_configuration(
    path: str | Path | None = None,
    *,
    overrides: list[str] | None = None,
    environ: dict[str, str] | None = None,
    use_environment: bool = True,
) -> Configuration:
    """Build the effective configuration.

    A missing configuration file is not an error: the built-in defaults are a
    complete, safe configuration, so a fresh clone and a CI job both work with
    no file at all. A file that is *named explicitly* and absent **is** an
    error, because that is always a mistake.
    """
    env = environ if environ is not None else dict(os.environ)
    explicit = path is not None or "PRAMA_CONFIG" in env
    resolved = Path(path or env.get("PRAMA_CONFIG", DEFAULT_CONFIG_PATH))

    builder = ConfigurationBuilder().with_defaults(DEFAULTS)
    builder.with_file(resolved, required=explicit)
    if use_environment:
        builder.with_environment(env)
    builder.with_cli(overrides)
    return builder.build()
