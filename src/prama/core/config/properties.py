"""The properties engine, adopted from DishtaYantra's ``core/properties_configurator.py``.

Two things live here, both DishtaYantra's:

* **The ``${...}`` resolution algorithm** (`resolve_value`): innermost
  placeholders first, repeatedly, so a nested reference such as
  ``${db.${env}.host}`` resolves; ``${VAR:default}`` split on the first colon; a
  reference looked up in a caller-supplied order. Prama's typed configuration
  resolves through it (`prama.core.config.resolver`).
* **`PropertiesConfigurator`**: a flat, string-valued view of configuration
  with DishtaYantra's API — ``get``, ``get_int``, ``get_bool``, ``get_list``,
  ``get_source``, the pattern queries, and resolving ``${...}`` inside
  arbitrary text, files and JSON — built from files with file < environment <
  command-line precedence and the source of every value tracked. Any
  configuration hands one out: ``config.properties()``.

Adapted, each for a stated reason:

* **Not a singleton, and no reload thread.** Prama builds many configurations
  in one process (every test does), and its concurrency rule forbids a bare
  ``threading.Thread``. `PropertiesConfigurator.changed()` and ``reload()`` do
  what the thread did, for a supervised task to call when one is wanted.
* **An unresolved placeholder with no default is an error**, and a cycle is
  reported with the chain that formed it. DishtaYantra leaves both in place as
  literal text, which is visible; Prama refuses, because a literal
  ``${DB_PASSWORD}`` reaching a driver is visible only as an outage.
* **``$${...}`` escapes** to a literal ``${...}``, as Prama already allowed.
* **Environment variables carry the ``PRAMA_`` prefix** in the typed
  configuration (``PRAMA_DATABASE__POOL__SIZE``), so an unrelated ``PATH`` or
  ``HOME`` can never become a setting. A placeholder may still name any
  variable exactly (``${HOME}``), as in DishtaYantra.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Final

from prama.core.config.parsers import parse_config_file, scalar_to_str
from prama.core.errors import ConfigError

#: The innermost placeholder: no brace inside it. Resolving these repeatedly
#: is what makes a nested reference resolve from the inside out.
_INNERMOST: Final[re.Pattern[str]] = re.compile(r"\$\{([^{}]+)\}")
#: ``$${`` is an escape. Hidden behind a marker while resolving, restored after.
_ESCAPE: Final[str] = "\x00ESCAPED\x00"
MAX_DEPTH: Final[int] = 16
MAX_PASSES: Final[int] = 100

Lookup = Callable[[str], str | None]


def resolve_value(value: str, lookup: Lookup, *, path: str = "", seen: tuple[str, ...] = ()) -> str:
    """Resolve every ``${name}`` and ``${name:default}`` in *value*.

    *lookup* answers a name with its raw (unresolved) value, or None. A found
    value is itself resolved, with *name* added to the chain, so a cycle is
    caught; a nested reference resolves because the innermost placeholder is
    replaced first and the text searched again.
    """
    if "${" not in value:
        return value
    if len(seen) > MAX_DEPTH:
        raise ConfigError(
            f"placeholder recursion exceeded {MAX_DEPTH} levels at {path or '<value>'}",
            code="CONFIG.PLACEHOLDER_CYCLE",
            remedy="Break the cycle: a placeholder chain must terminate in a literal.",
            context={"path": path, "chain": " -> ".join(seen)},
        )
    text = value.replace("$${", _ESCAPE)
    for _ in range(MAX_PASSES):
        matches = list(_INNERMOST.finditer(text))
        if not matches:
            break
        for match in reversed(matches):
            token = match.group(1)
            name, has_default, default = token.partition(":")
            name = name.strip()
            if name in seen:
                raise ConfigError(
                    f"placeholder cycle: {' -> '.join((*seen, name))}",
                    code="CONFIG.PLACEHOLDER_CYCLE",
                    remedy="Remove the self-reference; a placeholder cannot resolve to itself.",
                    context={"path": path, "name": name},
                )
            found = lookup(name)
            if found is None:
                if not has_default:
                    raise ConfigError(
                        f"no value for ${{{name}}}" + (f" (referenced by {path})" if path else ""),
                        code="CONFIG.PLACEHOLDER_UNRESOLVED",
                        remedy=(
                            f"Set the environment variable {name}, define {name} in "
                            f"configuration, or give the placeholder a default: "
                            f"${{{name}:value}}."
                        ),
                        context={"path": path, "name": name},
                    )
                replacement = resolve_value(default, lookup, path=path, seen=seen)
            else:
                replacement = resolve_value(found, lookup, path=path, seen=(*seen, name))
            text = text[: match.start()] + replacement + text[match.end() :]
    else:
        raise ConfigError(
            f"placeholders in {path or '<value>'} did not settle in {MAX_PASSES} passes",
            code="CONFIG.PLACEHOLDER_CYCLE",
            remedy="Simplify the nested placeholders; each pass must remove at least one.",
            context={"path": path},
        )
    return text.replace(_ESCAPE, "${")


class PropertiesConfigurator:
    """DishtaYantra's properties API over a flat, string-valued configuration.

    Precedence, highest first: command-line ``--key=value``, then environment
    variables named exactly as the key, then the files (the rightmost file
    wins). Each file is followed by its ``*.local.*`` overlay when one exists.
    """

    def __init__(
        self,
        properties_files: str | Sequence[str | Path] | None = None,
        *,
        properties: dict[str, str] | None = None,
        sources: dict[str, str] | None = None,
        environ: dict[str, str] | None = None,
        argv: Sequence[str] | None = None,
    ) -> None:
        self._files = self._with_local_overlays(self._parse_file_paths(properties_files))
        self._environ = dict(os.environ) if environ is None else environ
        self._commandline = self._parse_commandline(sys.argv[1:] if argv is None else argv)
        self._mtimes: dict[str, float] = {}
        self._seeded = dict(properties or {})
        self._seeded_sources = dict(sources or {})
        self._properties: dict[str, str] = {}
        self._sources: dict[str, str] = {}
        self.reload()

    # -- building ------------------------------------------------------------

    @staticmethod
    def _parse_file_paths(files: str | Sequence[str | Path] | None) -> list[str]:
        if files is None:
            return []
        if isinstance(files, str):
            return [part.strip() for part in files.split(",") if part.strip()]
        return [str(part).strip() for part in files if str(part).strip()]

    @staticmethod
    def _with_local_overlays(files: list[str]) -> list[str]:
        """Each file followed by its ``<name>.local.<ext>`` overlay, if it exists."""
        out: list[str] = []
        for path in files:
            out.append(path)
            given = Path(path)
            local = str(given.with_name(f"{given.stem}.local{given.suffix}"))
            if local not in files and Path(local).exists():
                out.append(local)
        return out

    @staticmethod
    def _parse_commandline(argv: Sequence[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for arg in argv:
            if arg.startswith("--") and "=" in arg:
                key, value = arg[2:].split("=", 1)
                if key.strip():
                    found[key.strip()] = value.strip()
        return found

    def reload(self) -> None:
        """Read the files again and re-apply precedence and resolution."""
        raw: dict[str, str] = dict(self._seeded)
        sources: dict[str, str] = dict(self._seeded_sources)
        for path in self._files:
            if not Path(path).exists():
                continue
            self._mtimes[path] = Path(path).stat().st_mtime
            for key, value in parse_config_file(path).items():
                raw[key] = scalar_to_str(value)
                sources[key] = f"file:{path}"

        def lookup(name: str) -> str | None:
            if name in self._commandline:
                return self._commandline[name]
            if name in self._environ:
                return self._environ[name]
            return raw.get(name)

        resolved = {k: resolve_value(v, lookup, path=k) for k, v in raw.items()}
        final: dict[str, str] = {}
        final_sources: dict[str, str] = {}
        for key, value in resolved.items():
            final[key], final_sources[key] = value, sources.get(key, "file")
            if key in self._environ:
                final[key], final_sources[key] = self._environ[key], "env"
            if key in self._commandline:
                final[key], final_sources[key] = self._commandline[key], "commandline"
        for key, value in self._commandline.items():
            if key not in final:
                final[key], final_sources[key] = value, "commandline"
        self._properties, self._sources = final, final_sources

    def changed(self) -> bool:
        """Whether any file has been modified since it was read (what the reload thread checked)."""
        return any(
            Path(path).exists() and Path(path).stat().st_mtime > self._mtimes.get(path, 0.0)
            for path in self._files
        )

    # -- access ----------------------------------------------------------------

    def get(self, key: str, default_value: str | None = None) -> str | None:
        return self._properties.get(key, default_value)

    def get_source(self, key: str) -> str | None:
        """``commandline``, ``env``, ``file:<path>``, or the typed source's name."""
        return self._sources.get(key)

    def get_system_name(self) -> str | None:
        return self.get("app.name")

    def get_int(self, key: str, default_value: int | None = None) -> int | None:
        value = self.get(key)
        try:
            return int(value) if value is not None else default_value
        except (TypeError, ValueError):
            return default_value

    def get_float(self, key: str, default_value: float | None = None) -> float | None:
        value = self.get(key)
        try:
            return float(value) if value is not None else default_value
        except (TypeError, ValueError):
            return default_value

    def get_bool(self, key: str, default_value: bool | None = None) -> bool | None:
        value = self.get(key)
        if value is None:
            return default_value
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "on", "1", "y", "t"):
            return True
        if lowered in ("false", "no", "off", "0", "n", "f"):
            return False
        try:
            return bool(float(lowered))
        except ValueError:
            return default_value

    def get_list(self, key: str, delim: str = ",") -> list[str] | None:
        value = self.get(key)
        if value is None:
            return None
        return [item.strip() for item in value.split(delim) if item.strip()]

    def get_int_list(self, key: str, delim: str = ",") -> list[int] | None:
        found = [int(v) for v in self.get_list(key, delim) or [] if _is_int(v)]
        return found or None

    def get_float_list(self, key: str, delim: str = ",") -> list[float] | None:
        found = [float(v) for v in self.get_list(key, delim) or [] if _is_float(v)]
        return found or None

    def get_properties_by_pattern(self, pattern: str) -> dict[str, str]:
        regex = _compile(pattern)
        return {k: v for k, v in self._properties.items() if regex.match(k)}

    def get_values_by_pattern(self, pattern: str) -> list[str]:
        return list(self.get_properties_by_pattern(pattern).values())

    def get_all_properties(self) -> dict[str, str]:
        return dict(self._properties)

    def get_all_sources(self) -> dict[str, str]:
        return dict(self._sources)

    # -- resolving other content -------------------------------------------------

    def _lookup(self, name: str) -> str | None:
        if name in self._commandline:
            return self._commandline[name]
        if name in self._environ:
            return self._environ[name]
        return self._properties.get(name)

    def resolve_string_content(self, content: str) -> str:
        """Resolve ``${prop}`` in *content*: command line, then environment, then properties."""
        return resolve_value(content, self._lookup, path="<content>") if content else content

    def load_and_resolve_file_content(self, filename: str | Path) -> list[str]:
        """A text file's lines, each resolved."""
        text = Path(filename).read_text(encoding="utf-8")
        return [self.resolve_string_content(line) for line in text.splitlines()]

    def resolve_string_json_content(self, content: str) -> dict[str, Any]:
        """A JSON document, resolved and then parsed."""
        resolved = json.loads(self.resolve_string_content(content))
        if not isinstance(resolved, dict):
            raise ConfigError(
                "resolved JSON content is not an object",
                code="CONFIG.JSON_SHAPE",
                remedy="The document must be a JSON object at the top level.",
            )
        return resolved

    def load_and_resolve_json_file_content(self, filename: str | Path) -> dict[str, Any]:
        return self.resolve_string_json_content(Path(filename).read_text(encoding="utf-8"))


#: DishtaYantra's format-neutral alias.
ConfigurationManager = PropertiesConfigurator


def flat_strings(values: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """A typed configuration tree as DishtaYantra's flat string view.

    Lists follow its convention: a list of scalars gives a joined value and
    indexed children; a list of mappings, indexed children only.
    """
    from prama.core.config.parsers import flatten_yaml

    return {k: scalar_to_str(v) for k, v in flatten_yaml(values, prefix).items()}


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ConfigError(
            f"invalid pattern {pattern!r}: {exc}",
            code="CONFIG.PATTERN_INVALID",
            remedy="Give a valid regular expression over property keys.",
        ) from exc


def _is_int(value: str) -> bool:
    try:
        int(value)
    except ValueError:
        return False
    return True


def _is_float(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def sources_of(provenance: dict[str, str], keys: Iterable[str]) -> dict[str, str]:
    """Each flat key's source, from a typed configuration's provenance."""
    out: dict[str, str] = {}
    for key in keys:
        cursor = key
        while cursor and cursor not in provenance:
            cursor = cursor.rsplit(".", 1)[0] if "." in cursor else ""
        out[key] = provenance.get(cursor, "defaults")
    return out
