"""What configuration each connector actually accepts, DERIVED from its code.

A form that offers "Snowflake" and then a single connection-string box is not
help. A real connection needs an account, a warehouse, a role, and usually a
key-pair or an SSO mode — and those have to be fillable by a data architect, or
the form is a toy.

The obvious way to provide that is a hand-written table of connectors and their
settings. This module does not do that, because a hand-written table is a second
description of the truth and it drifts the first time a connector gains an
option — silently, in the direction of a form that cannot express what the
engine supports.

Instead:

* the **fields** are parsed from each connector's own module, by finding every
  ``self.config.get("name", default)`` it reads, so a connector that gains an
  option gains it here, with its real default, the moment the code is written;
* a **curated overlay** adds only presentation: which fields are secret, which
  are required, what input to render, which group they belong to, and a line of
  help. The overlay may annotate a derived field; it cannot invent one;
* ``audit()`` reports an overlay key the code does not read, so the two cannot
  quietly disagree.

The result is a form that follows the implementation, and a test that fails when
they diverge. Adopted from DishtaYantra, where the pattern proved itself.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import inspect
from typing import Any

from prama.core.errors import ValidationError


class InputKind(enum.Enum):
    """How a field is rendered. Presentation only — never affects behaviour."""

    TEXT = "text"
    PASSWORD = "password"  # never rendered; shows a vault picker instead
    NUMBER = "number"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTILINE = "multiline"
    PATH = "path"
    DURATION = "duration"
    BYTES = "bytes"


@dataclasses.dataclass(frozen=True, slots=True)
class FieldSpec:
    """One configuration field, derived from code and annotated for a human."""

    name: str
    default: Any = None
    #: True when the connector reads it with no default, i.e. it must be given.
    required: bool = False
    #: Secrets are never rendered as an input; the UI offers a vault reference.
    secret: bool = False
    input_kind: InputKind = InputKind.TEXT
    label: str = ""
    help: str = ""
    group: str = "connection"
    choices: tuple[str, ...] = ()
    order: int = 100

    @property
    def display_label(self) -> str:
        return self.label or self.name.replace("_", " ").capitalize()

    @property
    def inferred_kind(self) -> InputKind:
        """A sensible input from the default's type, before any overlay."""
        if self.secret:
            return InputKind.PASSWORD
        if isinstance(self.default, bool):
            return InputKind.BOOLEAN
        if isinstance(self.default, (int, float)):
            return InputKind.NUMBER
        return self.input_kind

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.display_label,
            "input": self.inferred_kind.value,
            "required": self.required,
            "secret": self.secret,
            # A secret's default is never emitted, even when the code has one.
            "default": None if self.secret else self.default,
            "help": self.help,
            "group": self.group,
            "choices": list(self.choices),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class FieldPresentation:
    """The curated half. May annotate a derived field; may not invent one."""

    secret: bool = False
    input_kind: InputKind | None = None
    label: str = ""
    help: str = ""
    group: str = "connection"
    choices: tuple[str, ...] = ()
    order: int = 100
    required: bool | None = None


class ConfigSchemaDeriver:
    """Reads a connector's source and reports the configuration it consumes.

    Deliberately syntactic. It looks for ``self.config.get(...)`` with a literal
    key, and nothing cleverer: a deriver that tried to follow indirection would
    sometimes be right and sometimes silently wrong, and silently wrong is the
    condition this whole design exists to avoid. A connector that reads its
    configuration dynamically simply declares those fields explicitly.
    """

    #: Attribute chains treated as the configuration mapping.
    CONFIG_ACCESSORS = ("config", "self.config", "cfg")

    def derive(self, connector_class: type) -> dict[str, FieldSpec]:
        """Every field the connector reads, including through its base classes.

        Walking the MRO matters as soon as connectors share a base: a SQL
        connector inherits ``statement_timeout_ms`` and ``schemas`` from the
        base that reads them, and a deriver that saw only the leaf class would
        omit those fields from the form — leaving a setting that the code
        honours but that nobody can set.

        Most-derived first, and ``setdefault`` inside, so a subclass that reads
        the same key with a different default wins over its base.
        """
        fields: dict[str, FieldSpec] = {}
        for klass in connector_class.__mro__:
            if klass is object:
                continue
            try:
                source = inspect.getsource(klass)
            except (OSError, TypeError):  # built dynamically, e.g. in a test
                continue
            for name, spec in self.derive_source(ast.parse(_dedent(source))).items():
                fields.setdefault(name, spec)
        return fields

    def derive_source(self, tree: ast.AST) -> dict[str, FieldSpec]:
        fields: dict[str, FieldSpec] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not self._is_config_get(node):
                continue
            key = self._literal_key(node)
            if key is None:
                continue
            default, has_default = self._literal_default(node)
            # First read wins: a later read with a different default would be a
            # defect in the connector, and reporting the first is deterministic.
            fields.setdefault(key, FieldSpec(name=key, default=default, required=not has_default))
        return dict(sorted(fields.items()))

    def _is_config_get(self, node: ast.Call) -> bool:
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "get":
            return False
        target = func.value
        if isinstance(target, ast.Name):
            return target.id in self.CONFIG_ACCESSORS
        if isinstance(target, ast.Attribute):
            return target.attr in self.CONFIG_ACCESSORS
        return False

    @staticmethod
    def _literal_key(node: ast.Call) -> str | None:
        if not node.args:
            return None
        first = node.args[0]
        return (
            first.value
            if isinstance(first, ast.Constant) and isinstance(first.value, str)
            else None
        )

    @staticmethod
    def _literal_default(node: ast.Call) -> tuple[Any, bool]:
        if len(node.args) < 2:
            return None, False
        try:
            return ast.literal_eval(node.args[1]), True
        except (ValueError, SyntaxError):
            return None, True  # a computed default: real, but not renderable


class ConnectorConfigSchema:
    """The form for one connector: derived fields, curated presentation.

    Construct through ``build`` rather than directly, so the two halves are
    always reconciled and never merely adjacent.
    """

    def __init__(
        self,
        connector_key: str,
        fields: tuple[FieldSpec, ...],
        *,
        unknown_overlay_keys: tuple[str, ...] = (),
    ) -> None:
        self.connector_key = connector_key
        self.fields = fields
        #: Overlay keys the code does not read. Reported, never rendered.
        self.unknown_overlay_keys = unknown_overlay_keys

    @classmethod
    def build(
        cls,
        connector_class: type,
        *,
        overlay: dict[str, FieldPresentation] | None = None,
        extra_fields: tuple[FieldSpec, ...] = (),
        deriver: ConfigSchemaDeriver | None = None,
    ) -> ConnectorConfigSchema:
        derived = (deriver or ConfigSchemaDeriver()).derive(connector_class)
        for field in extra_fields:
            derived.setdefault(field.name, field)
        overlay = overlay or {}

        merged: list[FieldSpec] = []
        for name, field in derived.items():
            presentation = overlay.get(name)
            if presentation is None:
                merged.append(field)
                continue
            merged.append(
                dataclasses.replace(
                    field,
                    secret=presentation.secret or field.secret,
                    input_kind=presentation.input_kind or field.input_kind,
                    label=presentation.label,
                    help=presentation.help,
                    group=presentation.group,
                    choices=presentation.choices,
                    order=presentation.order,
                    required=(
                        field.required if presentation.required is None else presentation.required
                    ),
                )
            )
        merged.sort(key=lambda f: (f.order, f.name))
        unknown = tuple(sorted(set(overlay) - set(derived)))
        key = getattr(connector_class, "plugin_key", connector_class.__name__.lower())
        return cls(key, tuple(merged), unknown_overlay_keys=unknown)

    # -- use ---------------------------------------------------------------

    def field(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def required_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.required)

    @property
    def secret_fields(self) -> tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.secret)

    def groups(self) -> dict[str, list[FieldSpec]]:
        grouped: dict[str, list[FieldSpec]] = {}
        for field in self.fields:
            grouped.setdefault(field.group, []).append(field)
        return grouped

    def to_form(self) -> dict[str, Any]:
        """The typed form a data architect fills in — no connection strings."""
        return {
            "connector": self.connector_key,
            "groups": [
                {"name": name, "fields": [f.to_dict() for f in fields]}
                for name, fields in self.groups().items()
            ],
        }

    def validate(self, config: dict[str, Any]) -> None:
        """Refuse a configuration the connector cannot use.

        Checked here rather than at connect time so a missing field is a message
        beside the input, not a driver error twenty seconds later.
        """
        missing = sorted(
            f.name
            for f in self.required_fields
            if config.get(f.name) in (None, "") and not f.secret
        )
        if missing:
            raise ValidationError(
                f"{self.connector_key} needs {', '.join(missing)}",
                remedy="Fill in the highlighted fields; the connector reads them with no default.",
                context={"connector": self.connector_key, "missing": missing},
            )
        supplied_secrets = sorted(
            f.name for f in self.secret_fields if config.get(f.name) not in (None, "")
        )
        if supplied_secrets:
            raise ValidationError(
                f"a secret may not be stored in connection configuration: "
                f"{', '.join(supplied_secrets)}",
                remedy=(
                    "Reference a vault entry with credential_ref instead. Connection "
                    "configuration is exported to Git and shown in the UI."
                ),
                context={"connector": self.connector_key, "keys": supplied_secrets},
            )

    def audit(self) -> list[str]:
        """Overlay keys the code does not read — the drift this design prevents."""
        return [
            f"{self.connector_key}: overlay describes {key!r}, which the connector never reads"
            for key in self.unknown_overlay_keys
        ]


def _dedent(source: str) -> str:
    """Class source extracted from a module is indented; ast.parse is not."""
    import textwrap

    return textwrap.dedent(source)
