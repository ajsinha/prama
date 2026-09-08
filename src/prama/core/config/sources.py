"""Configuration sources.

A source answers one question: *what mapping of settings do you contribute?*
Sources are ordered, and a later source overrides an earlier one key by key —
never wholesale, so an operator can override ``database.pool.size`` without
having to restate the rest of ``database``.

The ordering that matters in practice, weakest to strongest:

    built-in defaults → application.yaml → application.local.yaml → env → CLI

``application.yaml`` is tracked and is documentation as much as configuration.
``application.local.yaml`` is git-ignored and is where a real secret belongs; the
overlay is discovered automatically from the base file's name, which is why a
deployment never has to name it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from prama.core.errors import ConfigError

#: Environment variables contributing configuration must carry this prefix, so
#: that an unrelated ``PATH`` or ``HOME`` can never silently become a setting.
ENV_PREFIX = "PRAMA_"

#: ``PRAMA_DATABASE__POOL__SIZE`` -> ``database.pool.size``. A double underscore
#: is used because a single one is legal inside a key segment.
ENV_SEPARATOR = "__"


class ConfigSource(ABC):
    """Contributes a nested mapping of configuration values."""

    #: Shown in provenance output and in ``prama config show``.
    name: str = "source"

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Return this source's contribution. May be empty; may not be None."""

    def describe(self) -> str:
        return self.name


class MappingSource(ConfigSource):
    """An in-memory mapping. Used for built-in defaults and for tests."""

    def __init__(self, values: dict[str, Any], *, name: str = "defaults") -> None:
        self._values = values
        self.name = name

    def load(self) -> dict[str, Any]:
        return _deep_copy(self._values)


class FileSource(ConfigSource):
    """Base for file-backed sources.

    A missing file is not an error when ``required`` is false: an overlay that
    does not exist is the normal case, and forcing operators to create empty
    files is friction with no safety benefit.
    """

    def __init__(self, path: str | Path, *, required: bool = True) -> None:
        self.path = Path(path)
        self.required = required
        self.name = str(self.path)

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            if self.required:
                raise ConfigError(
                    f"configuration file not found: {self.path}",
                    code="CONFIG.FILE_MISSING",
                    remedy=f"Create {self.path}, or point --config at an existing file.",
                    context={"path": str(self.path)},
                )
            return {}
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                f"could not read configuration file: {self.path}",
                code="CONFIG.FILE_UNREADABLE",
                remedy="Check the file's permissions and encoding (UTF-8 is expected).",
                context={"path": str(self.path)},
                cause=exc,
            ) from exc
        return self._parse(text)

    @abstractmethod
    def _parse(self, text: str) -> dict[str, Any]:
        """Parse the file body into a nested mapping."""


class YamlFileSource(FileSource):
    """A YAML document. The recommended format."""

    def _parse(self, text: str) -> dict[str, Any]:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(
                f"invalid YAML in {self.path}",
                code="CONFIG.YAML_INVALID",
                remedy="Fix the YAML syntax reported below and retry.",
                context={"path": str(self.path), "detail": str(exc)},
                cause=exc,
            ) from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigError(
                f"{self.path} must contain a mapping at the top level",
                code="CONFIG.YAML_SHAPE",
                remedy="Wrap the document in key: value pairs.",
                context={"path": str(self.path), "found": type(data).__name__},
            )
        return data


class PropertiesFileSource(FileSource):
    """A ``.properties`` file: ``database.pool.size = 20``.

    Supported because estates migrating from JVM tooling already have thousands
    of these, and asking them to convert before they can evaluate anything is a
    pointless obstacle. Dotted keys expand into the same nested shape YAML
    produces, so nothing downstream can tell which format was used.
    """

    def _parse(self, text: str) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for lineno, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith(("#", "!")):
                continue
            for sep in ("=", ":"):
                if sep in line:
                    key, value = line.split(sep, 1)
                    break
            else:
                raise ConfigError(
                    f"{self.path}:{lineno} is not a key/value line",
                    code="CONFIG.PROPERTIES_INVALID",
                    remedy="Use `key = value`, or comment the line with '#'.",
                    context={"path": str(self.path), "line": lineno},
                )
            flat[key.strip()] = value.strip()
        return expand_dotted(flat)


class EnvironmentSource(ConfigSource):
    """Environment variables carrying the ``PRAMA_`` prefix.

    Values arrive as strings; coercion happens at read time against the type the
    caller asks for, so ``PRAMA_DATABASE__POOL__SIZE=20`` becomes an int when
    read as one and stays a string when read as one.
    """

    name = "environment"

    def __init__(self, environ: dict[str, str] | None = None, prefix: str = ENV_PREFIX) -> None:
        self._environ = environ if environ is not None else dict(os.environ)
        self._prefix = prefix

    def load(self) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for key, value in self._environ.items():
            if not key.startswith(self._prefix):
                continue
            path = key[len(self._prefix) :].replace(ENV_SEPARATOR, ".").lower()
            if path:
                flat[path] = value
        return expand_dotted(flat)


class CliSource(ConfigSource):
    """``--set database.dialect=postgres`` overrides, the strongest source."""

    name = "command line"

    def __init__(self, assignments: list[str] | None = None) -> None:
        self._assignments = assignments or []

    def load(self) -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for item in self._assignments:
            if "=" not in item:
                raise ConfigError(
                    f"malformed override: {item!r}",
                    code="CONFIG.CLI_INVALID",
                    remedy="Use --set path.to.key=value.",
                    context={"assignment": item},
                )
            key, value = item.split("=", 1)
            flat[key.strip()] = value.strip()
        return expand_dotted(flat)


def expand_dotted(flat: dict[str, Any]) -> dict[str, Any]:
    """Turn ``{"a.b": 1}`` into ``{"a": {"b": 1}}``.

    A collision between a scalar and a nested path (``a=1`` and ``a.b=2``) is
    reported rather than resolved, because either resolution silently discards
    something the operator wrote.
    """
    out: dict[str, Any] = {}
    for dotted, value in flat.items():
        parts = [p for p in dotted.split(".") if p]
        if not parts:
            continue
        cursor = out
        for part in parts[:-1]:
            existing = cursor.get(part)
            if existing is None:
                cursor[part] = {}
            elif not isinstance(existing, dict):
                raise ConfigError(
                    f"configuration key {dotted!r} conflicts with a scalar at {part!r}",
                    code="CONFIG.KEY_CONFLICT",
                    remedy="Remove one of the two definitions; a key cannot be both.",
                    context={"key": dotted, "conflict_at": part},
                )
            cursor = cursor[part]
        cursor[parts[-1]] = value
    return out


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge *overlay* onto *base*, recursing into mappings only.

    Lists replace rather than concatenate. Concatenation looks helpful and then
    makes it impossible to *remove* a default entry, which is the operation
    operators actually need.
    """
    result = _deep_copy(base)
    for key, value in overlay.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = deep_merge(current, value)
        else:
            result[key] = _deep_copy(value)
    return result


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


def local_overlay_for(path: str | Path) -> Path:
    """``config/application.yaml`` -> ``config/application.local.yaml``."""
    p = Path(path)
    return p.with_name(f"{p.stem}.local{p.suffix}")


def source_for(path: str | Path, *, required: bool = True) -> FileSource:
    """Pick a file source from the extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return YamlFileSource(p, required=required)
    if suffix in (".properties", ".props"):
        return PropertiesFileSource(p, required=required)
    raise ConfigError(
        f"unsupported configuration format: {p.suffix or '(none)'}",
        code="CONFIG.FORMAT_UNSUPPORTED",
        remedy="Use a .yaml, .yml or .properties file.",
        context={"path": str(p)},
    )
