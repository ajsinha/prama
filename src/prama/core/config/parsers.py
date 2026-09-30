"""Configuration file parsers, adopted from DishtaYantra's ``core/config_parsers.py``.

Format-agnostic parsing: each parser turns a file into a flat
``{dotted.key: value}`` dictionary, and the engine in `prama.core.config.properties`
runs that through the same ``${...}`` resolution and precedence whatever the
format was. Keeping the parser apart from the engine means a YAML file and a
``.properties`` file produce the same configuration, and Prama and DishtaYantra
read the same files the same way.

Formats, chosen by extension:

    .yaml / .yml         YAML, flattened to dotted keys (Spring Boot style)
    .properties / .props classic line-based ``key=value``

Adopted as DishtaYantra has it, with three adaptations, each for a stated reason:

* **Typed mode.** DishtaYantra renders every value as a string, and a list as
  both a joined string and indexed children (``tags`` = ``"a,b"``,
  ``tags.0`` = ``"a"``). That is the flat, string-valued view
  (`prama.core.config.properties.PropertiesConfigurator`), and is the default
  here too. Prama's typed configuration tree also parses through this module,
  with ``typed=True``: scalars keep the type YAML gave them and a list stays a
  list, because a hundred call sites read ``config.get(...)`` expecting the
  value YAML wrote, not its string form.
* **A malformed ``.properties`` line is an error**, not silently skipped: a line
  somebody wrote that is not read is a setting they believe they made. ``:`` is
  accepted as a separator and ``!`` as a comment, per the ``.properties`` format.
* **Errors are Prama's** (`ConfigError` codes and remedies), so a bad file
  reports what to fix in the same shape as every other configuration error.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from prama.core.errors import ConfigError


class ConfigParseError(ConfigError):
    """A configuration file could not be parsed. Fatal: never half-load."""

    code = "CONFIG.PARSE"


def detect_format(file_path: str | Path) -> str:
    """``yaml`` or ``properties``, from the extension; anything else is refused."""
    suffix = Path(file_path).suffix.lower()
    if suffix in (".yaml", ".yml"):
        return "yaml"
    if suffix in (".properties", ".props"):
        return "properties"
    raise ConfigError(
        f"unsupported configuration format: {Path(file_path).suffix or '(none)'}",
        code="CONFIG.FORMAT_UNSUPPORTED",
        remedy="Use a .yaml, .yml or .properties file.",
        context={"path": str(file_path)},
    )


def scalar_to_str(value: Any) -> str:
    """A YAML scalar as the string the resolution engine expects.

    Booleans become lowercase ``true``/``false``, to match how the boolean
    getters read them; ``None`` becomes an empty string.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def flatten_yaml(data: Any, prefix: str = "", *, typed: bool = False) -> dict[str, Any]:
    """A parsed YAML document as a flat dotted-key dictionary.

    Mappings nest with dots (``a: {b: c}`` -> ``a.b``). In the string view a
    sequence of scalars gives both a joined value at the key and indexed
    children (``tags: [x, y]`` -> ``tags`` = ``"x,y"``, ``tags.0`` = ``"x"``);
    a sequence of mappings gives indexed children only. In the typed view a
    sequence is kept whole at its key.
    """
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            if typed and isinstance(value, dict) and not value:
                out[child] = {}  # an empty section is a value, not nothing
            else:
                out.update(flatten_yaml(value, child, typed=typed))
    elif isinstance(data, (list, tuple)):
        if typed:
            if prefix:
                out[prefix] = list(data)
            return out
        scalars = [item for item in data if not isinstance(item, (dict, list, tuple))]
        if prefix and scalars and len(scalars) == len(data):
            out[prefix] = ",".join(scalar_to_str(v) for v in data)
        for index, item in enumerate(data):
            child = f"{prefix}.{index}" if prefix else str(index)
            if isinstance(item, (dict, list, tuple)):
                out.update(flatten_yaml(item, child, typed=typed))
            else:
                out[child] = scalar_to_str(item)
    elif prefix:
        out[prefix] = data if typed else scalar_to_str(data)
    return out


def parse_properties_text(text: str, *, source: str = "<properties>") -> dict[str, str]:
    """Classic ``key=value`` (or ``key: value``) properties text as a flat dictionary."""
    result: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", "!", "//")):
            continue
        for separator in ("=", ":"):
            if separator in line:
                key, value = line.split(separator, 1)
                break
        else:
            raise ConfigParseError(
                f"{source}:{lineno} is not a key/value line",
                code="CONFIG.PROPERTIES_INVALID",
                remedy="Use `key = value`, or comment the line with '#'.",
                context={"path": source, "line": lineno},
            )
        if key.strip():
            result[key.strip()] = value.strip()
    return result


def load_yaml_mapping(text: str, *, source: str = "<yaml>") -> dict[str, Any]:
    """YAML text as the mapping it declares, refused unless it is one.

    The typed configuration tree uses this directly, so a key that itself
    contains a dot (a map keyed by ``author.v2``, say) stays one key; the flat
    view flattens it (`parse_yaml_text`).
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigParseError(
            f"invalid YAML in {source}",
            code="CONFIG.YAML_INVALID",
            remedy="Fix the YAML syntax reported below and retry.",
            context={"path": source, "detail": str(exc)},
            cause=exc,
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigParseError(
            f"{source} must contain a mapping at the top level",
            code="CONFIG.YAML_SHAPE",
            remedy="Wrap the document in key: value pairs.",
            context={"path": source, "found": type(data).__name__},
        )
    return dict(data)


def parse_yaml_text(text: str, *, source: str = "<yaml>", typed: bool = False) -> dict[str, Any]:
    """YAML text as a flat dotted-key dictionary."""
    return flatten_yaml(load_yaml_mapping(text, source=source), typed=typed)


def read_config_text(file_path: str | Path) -> str:
    """A configuration file's text, or a `ConfigError` that says what to fix."""
    path = Path(file_path)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # A UnicodeDecodeError is a ValueError, not an OSError: without this
        # clause a latin-1 file reached the terminal as a traceback. QA CFG-062.
        raise ConfigError(
            f"{path} is not valid UTF-8: byte 0x{exc.object[exc.start]:02x} "
            f"at position {exc.start}",
            code="CONFIG.FILE_UNREADABLE",
            remedy=(
                "Save the file as UTF-8. An editor defaulting to latin-1 or "
                "cp1252 produces this as soon as a value contains an accent."
            ),
            context={"path": str(path), "position": exc.start},
            cause=exc,
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"could not read configuration file: {path}",
            code="CONFIG.FILE_UNREADABLE",
            remedy="Check the file's permissions and encoding (UTF-8 is expected).",
            context={"path": str(path)},
            cause=exc,
        ) from exc


def parse_config_file(file_path: str | Path, *, typed: bool = False) -> dict[str, Any]:
    """One configuration file as a flat dotted-key dictionary, by its extension.

    No silent fallback: a malformed file raises, because a configuration that
    half-loaded is one nobody can reason about.
    """
    fmt = detect_format(file_path)
    text = read_config_text(file_path)
    if fmt == "yaml":
        return parse_yaml_text(text, source=str(file_path), typed=typed)
    return parse_properties_text(text, source=str(file_path))


def find_default_config(config_dir: str | Path = "config") -> Path:
    """The application's configuration file, preferring YAML.

    ``application.yaml``, then ``application.yml``, then
    ``application.properties``, under *config_dir*.
    """
    candidates = ("application.yaml", "application.yml", "application.properties")
    for name in candidates:
        path = Path(config_dir) / name
        if path.exists():
            return path
    raise ConfigError(
        f"no application configuration in {config_dir}",
        code="CONFIG.FILE_MISSING",
        remedy=f"Create one of: {', '.join(candidates)}.",
        context={"path": str(config_dir)},
    )
