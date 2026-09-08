"""The merged, resolved configuration and the builder that produces it.

``Configuration`` is immutable and read-only. It knows three things beyond the
values themselves, and each exists because of a real operational question:

* **Provenance** — *"where did this value come from?"* Answered per key, because
  the usual production mystery is not what a setting is but which of five files
  set it.
* **Redaction** — *"can I paste this into a ticket?"* ``redacted()`` returns a
  copy safe to display, so ``prama config show`` is never a credential leak.
* **Binding** — *"is this section shaped the way the component expects?"*
  ``bind()`` maps a section onto a dataclass, validating types once at startup
  rather than discovering them at the first use in production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from pathlib import Path
from typing import Any, TypeVar

from prama.core.config.coercion import Coercer
from prama.core.config.resolver import PlaceholderResolver
from prama.core.config.sources import (
    CliSource,
    ConfigSource,
    EnvironmentSource,
    MappingSource,
    deep_merge,
    local_overlay_for,
    source_for,
)
from prama.core.errors import ConfigError, ConfigMissingError, SecretMissingError
from prama.core.log import SENSITIVE_KEYS, redact_mapping

T = TypeVar("T")

_MISSING = object()


class Configuration:
    """An immutable, fully-resolved view of the platform's settings."""

    def __init__(
        self,
        values: dict[str, Any],
        *,
        provenance: dict[str, str] | None = None,
        prefix: str = "",
    ) -> None:
        self._values = values
        self._provenance = provenance or {}
        self._prefix = prefix

    # -- access ------------------------------------------------------------

    def raw(self) -> dict[str, Any]:
        """The underlying mapping. Callers must not mutate it."""
        return self._values

    def _qualify(self, path: str) -> str:
        return f"{self._prefix}.{path}" if self._prefix else path

    def _lookup(self, path: str) -> Any:
        cursor: Any = self._values
        for part in path.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return _MISSING
            cursor = cursor[part]
        return cursor

    def has(self, path: str) -> bool:
        return self._lookup(path) is not _MISSING

    def get(self, path: str, default: Any = None) -> Any:
        value = self._lookup(path)
        return default if value is _MISSING else value

    def require(self, path: str) -> Any:
        value = self._lookup(path)
        if value is _MISSING:
            raise ConfigMissingError(
                f"required configuration key is not set: {self._qualify(path)}",
                remedy=(
                    f"Set {self._qualify(path)} in config/application.yaml, or export "
                    f"PRAMA_{self._qualify(path).upper().replace('.', '__')}."
                ),
                context={"key": self._qualify(path)},
            )
        return value

    def section(self, path: str) -> Configuration:
        """A sub-view rooted at *path*. A missing section is an empty one."""
        value = self._lookup(path)
        if value is _MISSING:
            value = {}
        if not isinstance(value, dict):
            raise ConfigError(
                f"configuration key {self._qualify(path)} is a value, not a section",
                code="CONFIG.NOT_A_SECTION",
                remedy="Remove the scalar definition, or read the key directly.",
                context={"key": self._qualify(path)},
            )
        return Configuration(value, provenance=self._provenance, prefix=self._qualify(path))

    # -- typed readers -----------------------------------------------------

    def _coercer(self, path: str) -> Coercer:
        return Coercer(self._qualify(path))

    def get_str(self, path: str, default: str | None = None) -> str:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            if default is None:
                return self._coercer(path).to_str(self.require(path))
            return default
        return self._coercer(path).to_str(value)

    def get_bool(self, path: str, default: bool | None = None) -> bool:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            if default is None:
                return self._coercer(path).to_bool(self.require(path))
            return default
        return self._coercer(path).to_bool(value)

    def get_int(self, path: str, default: int | None = None) -> int:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            if default is None:
                return self._coercer(path).to_int(self.require(path))
            return default
        return self._coercer(path).to_int(value)

    def get_float(self, path: str, default: float | None = None) -> float:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            if default is None:
                return self._coercer(path).to_float(self.require(path))
            return default
        return self._coercer(path).to_float(value)

    def get_list(self, path: str, default: list[Any] | None = None) -> list[Any]:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            return list(default or [])
        return self._coercer(path).to_list(value)

    def get_dict(self, path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            return dict(default or {})
        return self._coercer(path).to_dict(value)

    def get_duration(self, path: str, default: str | float | None = None) -> float:
        """Seconds."""
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            if default is None:
                return self._coercer(path).to_duration_seconds(self.require(path))
            return self._coercer(path).to_duration_seconds(default)
        return self._coercer(path).to_duration_seconds(value)

    def get_bytes(self, path: str, default: str | int | None = None) -> int:
        value = self.get(path, _MISSING)
        if value is _MISSING or value is None:
            if default is None:
                return self._coercer(path).to_bytes(self.require(path))
            return self._coercer(path).to_bytes(default)
        return self._coercer(path).to_bytes(value)

    def get_path(self, path: str, default: str | None = None) -> Path:
        return Path(self.get_str(path, default)).expanduser()

    def require_secret(self, path: str) -> str:
        """A secret that must be present and non-empty.

        The shipped default for every secret is deliberately empty so that a
        fresh clone refuses to boot rather than running on a public value.
        """
        value = self.get(path, "")
        text = "" if value is None else str(value).strip()
        if not text:
            key = self._qualify(path)
            raise SecretMissingError(
                f"{key} is empty, and Prama will not start without it",
                remedy=(
                    f"Set {key} in config/application.local.yaml (git-ignored), or export "
                    f"PRAMA_{key.upper().replace('.', '__')}. Never put it in a tracked file."
                ),
                context={"key": key},
            )
        return text

    # -- provenance and display -------------------------------------------

    def provenance(self, path: str) -> str | None:
        return self._provenance.get(self._qualify(path))

    def redacted(self) -> dict[str, Any]:
        """A copy safe to print, with sensitive values masked."""
        return redact_mapping(self._values)

    def flatten(self, *, redact: bool = True) -> dict[str, Any]:
        """Dotted-key view, for ``prama config show`` and diagnostics."""
        out: dict[str, Any] = {}

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{prefix}.{key}" if prefix else key)
            else:
                leaf = prefix.rsplit(".", 1)[-1].lower()
                out[prefix] = "***" if redact and leaf in SENSITIVE_KEYS and node else node

        walk(self._values, self._prefix)
        return out

    # -- binding -----------------------------------------------------------

    def bind(self, path: str, cls: type[T]) -> T:
        """Map a configuration section onto a dataclass, coercing field types.

        Validation happens once, at startup. A component that receives a bound
        settings object never has to re-check a type, and a typo in a key name
        is a boot failure rather than a 3am ``KeyError``.
        """
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f"{cls.__name__} is not a dataclass")
        section = self.section(path)
        hints = typing.get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(cls):
            hint = hints.get(field.name, str)
            has_default = (
                field.default is not dataclasses.MISSING
                or field.default_factory is not dataclasses.MISSING
            )
            if not section.has(field.name):
                if has_default:
                    continue
                raise ConfigMissingError(
                    f"required configuration key is not set: {section._qualify(field.name)}",
                    remedy=f"Add {field.name} under {self._qualify(path)}.",
                    context={"key": section._qualify(field.name)},
                )
            kwargs[field.name] = _coerce_hint(section, field.name, hint)
        return typing.cast("T", cls(**kwargs))


def _coerce_hint(section: Configuration, name: str, hint: Any) -> Any:
    """Read ``name`` from ``section`` as the type described by ``hint``."""
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if section.get(name) is None:
            return None
        hint = args[0] if args else str
        origin = typing.get_origin(hint)
    if origin in (list, set, tuple):
        return section.get_list(name)
    if origin is dict:
        return section.get_dict(name)
    if hint is bool:
        return section.get_bool(name)
    if hint is int:
        return section.get_int(name)
    if hint is float:
        return section.get_float(name)
    if hint is Path:
        return section.get_path(name)
    return section.get_str(name)


class ConfigurationBuilder:
    """Assembles a ``Configuration`` from ordered sources.

    Order is weakest to strongest. ``with_file`` automatically adds the
    git-ignored ``*.local.*`` overlay immediately after the base file, which is
    the mechanism that keeps secrets out of tracked configuration without any
    deployment having to know the overlay exists.
    """

    def __init__(self) -> None:
        self._sources: list[ConfigSource] = []
        self._environ: dict[str, str] | None = None

    def with_defaults(self, values: dict[str, Any]) -> ConfigurationBuilder:
        self._sources.append(MappingSource(values, name="built-in defaults"))
        return self

    def with_file(
        self, path: str | Path, *, required: bool = True, overlay: bool = True
    ) -> ConfigurationBuilder:
        self._sources.append(source_for(path, required=required))
        if overlay:
            local = local_overlay_for(path)
            self._sources.append(source_for(local, required=False))
        return self

    def with_mapping(self, values: dict[str, Any], *, name: str) -> ConfigurationBuilder:
        self._sources.append(MappingSource(values, name=name))
        return self

    def with_environment(self, environ: dict[str, str] | None = None) -> ConfigurationBuilder:
        self._environ = environ
        self._sources.append(EnvironmentSource(environ))
        return self

    def with_cli(self, assignments: list[str] | None) -> ConfigurationBuilder:
        if assignments:
            self._sources.append(CliSource(assignments))
        return self

    def build(self) -> Configuration:
        merged: dict[str, Any] = {}
        provenance: dict[str, str] = {}
        for source in self._sources:
            contribution = source.load()
            _record_provenance(contribution, source.describe(), provenance, "")
            merged = deep_merge(merged, contribution)
        resolved = PlaceholderResolver(self._environ).resolve_tree(merged)
        return Configuration(resolved, provenance=provenance)


def _record_provenance(node: Any, source: str, into: dict[str, str], prefix: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _record_provenance(value, source, into, f"{prefix}.{key}" if prefix else key)
    else:
        into[prefix] = source
