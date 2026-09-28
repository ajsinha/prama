"""Metadata the bank defines: templates of typed fields, and rules that grow from them.

A **template** is a set of fields for datasets or for attributes: "source system"
(text), "retention days" (number), "golden source" (flag), "allowed values"
(list). Each bank writes its own, as YAML::

    name: data-quality
    applies_to: attribute
    fields:
      - name: mandatory
        kind: flag
        rules:
          - when: "true"
            pql: "CHECK {{ dataset }}.{{ attribute }} IS NOT NULL"
      - name: allowed_values
        kind: list
        rules:
          - pql: "CHECK {{ dataset }}.{{ attribute }} IN {{ values }}"

**Rules grow from metadata.** A field may carry rule templates. When a value is
set that satisfies a rule's `when`, the rule is rendered into PQL and offered
on the Proposals page, like every control Prama derives. A person accepts it,
and it runs. Nothing activates by itself.

Values reach PQL only as literals of their kind, never as raw text:

| placeholder     | becomes                          | for kinds            |
|-----------------|----------------------------------|----------------------|
| `{{ dataset }}`   | the dataset's name, quoted if needed | all              |
| `{{ attribute }}` | the attribute's name             | attribute templates  |
| `{{ value }}`     | a number                         | number               |
| `{{ text }}`      | a quoted string                  | text, choice, day    |
| `{{ values }}`    | `('a', 'b')`                     | list                 |
| `{{ pattern }}`   | `/…/`                            | text                 |
| `{{ columns }}`   | `a, b` (checked identifiers)     | columns              |

So a value like `x' OR 1=1` stays a string inside quotes: metadata cannot
inject PQL.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from prama.core.errors import ValidationError

KINDS = ("text", "longtext", "number", "flag", "choice", "list", "day", "columns")
APPLIES_TO = ("dataset", "attribute")
_SLOT = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Which placeholders each kind may use, beyond dataset and attribute.
_ALLOWED: dict[str, set[str]] = {
    "text": {"text", "pattern"},
    "longtext": {"text"},
    "number": {"value"},
    "flag": set(),
    "choice": {"text"},
    "list": {"values"},
    "day": {"text"},
    "columns": {"columns"},
}


@dataclasses.dataclass(frozen=True, slots=True)
class Rule:
    pql: str
    #: `set` (any non-empty value), `true`/`false` (flags), or `=<choice>`.
    when: str = "set"
    note: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    kind: str
    label: str = ""
    choices: tuple[str, ...] = ()
    required: bool = False
    help: str = ""
    rules: tuple[Rule, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class TemplateSpec:
    name: str
    applies_to: str
    fields: tuple[FieldSpec, ...]
    description: str = ""


def _problem(message: str, remedy: str) -> ValidationError:
    return ValidationError(message, remedy=remedy)


def parse_template(document: Mapping[str, Any]) -> TemplateSpec:
    """A template from its YAML form, checked field by field and rule by rule."""
    name = str(document.get("name", "")).strip()
    applies = str(document.get("applies_to", "")).strip()
    if not name or applies not in APPLIES_TO:
        raise _problem(
            "a template needs a name and applies_to: dataset or attribute",
            "Give both at the top of the template.",
        )
    fields = []
    seen: set[str] = set()
    for raw in document.get("fields") or []:
        field_name = str(raw.get("name", "")).strip()
        kind = str(raw.get("kind", "text")).strip()
        if not _IDENTIFIER.match(field_name) or field_name in seen:
            raise _problem(
                f"field name {field_name!r} is empty, repeated or not an identifier",
                "Name each field once, with letters, digits and underscores.",
            )
        if kind not in KINDS:
            raise _problem(f"{field_name}: unknown kind {kind!r}", f"One of: {', '.join(KINDS)}.")
        choices = tuple(str(c) for c in raw.get("choices") or [])
        if kind == "choice" and not choices:
            raise _problem(f"{field_name}: a choice needs choices", "List them under choices.")
        rules = []
        for item in raw.get("rules") or []:
            rule = Rule(
                pql=str(item.get("pql", "")).strip(),
                when=str(item.get("when", "set")).strip(),
                note=str(item.get("note", "")),
            )
            used = set(_SLOT.findall(rule.pql)) - {"dataset", "attribute"}
            if not rule.pql or used - _ALLOWED[kind]:
                raise _problem(
                    f"{field_name}: the rule uses {', '.join(sorted(used - _ALLOWED[kind]))} "
                    f"which a {kind} field cannot fill",
                    f"A {kind} field may use: {', '.join(sorted(_ALLOWED[kind])) or 'none'}.",
                )
            if "attribute" in _SLOT.findall(rule.pql) and applies != "attribute":
                raise _problem(
                    f"{field_name}: a dataset template's rule cannot name an attribute",
                    "Use {{ columns }} with a columns field, or move the field to an "
                    "attribute template.",
                )
            rules.append(rule)
        seen.add(field_name)
        fields.append(
            FieldSpec(
                name=field_name,
                kind=kind,
                label=str(raw.get("label", "")) or field_name.replace("_", " "),
                choices=choices,
                required=bool(raw.get("required", False)),
                help=str(raw.get("help", "")),
                rules=tuple(rules),
            )
        )
    return TemplateSpec(
        name=name,
        applies_to=applies,
        fields=tuple(fields),
        description=str(document.get("description", "")),
    )


def coerce(field: FieldSpec, raw: Any) -> Any:
    """The value to store for *raw*, of the field's kind, or a refusal naming why."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    text = raw.strip() if isinstance(raw, str) else raw
    try:
        if field.kind == "number":
            number = float(text)
            return int(number) if number.is_integer() else number
        if field.kind == "flag":
            if isinstance(text, bool):
                return text
            lowered = str(text).lower()
            if lowered in ("true", "yes", "y", "1"):
                return True
            if lowered in ("false", "no", "n", "0"):
                return False
            raise ValueError("not yes or no")
        if field.kind == "choice":
            if str(text) not in field.choices:
                raise ValueError(f"not one of {', '.join(field.choices)}")
            return str(text)
        if field.kind in ("list", "columns"):
            items = text if isinstance(text, list) else re.split(r"[,;]", str(text))
            values = [str(v).strip() for v in items if str(v).strip()]
            if field.kind == "columns" and not all(_IDENTIFIER.match(v) for v in values):
                raise ValueError("column names are letters, digits and underscores")
            return values
        if field.kind == "day":
            return date.fromisoformat(str(text)).isoformat()
        return str(text)
    except (TypeError, ValueError) as exc:
        raise _problem(
            f"{field.name}: {raw!r} is not a valid {field.kind} ({exc})",
            field.help or f"Give {field.name} as a {field.kind}.",
        ) from exc


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def render(
    rule: Rule, field: FieldSpec, value: Any, *, dataset: str, attribute: str = ""
) -> str | None:
    """The rule's PQL for *value*, or None when its `when` is not met."""
    from prama.pql.ast import quote_dataset

    if value is None or value == [] or value == "":
        return None
    when = rule.when.lower()
    if when == "true" and value is not True:
        return None
    if when == "false" and value is not False:
        return None
    if when.startswith("=") and str(value) != rule.when[1:]:
        return None
    fill = {
        "dataset": quote_dataset(dataset),
        "attribute": attribute,
        "value": str(value) if field.kind == "number" else "",
        "text": _literal(str(value)),
        "values": "(" + ", ".join(_literal(v) for v in value) + ")"
        if isinstance(value, list)
        else "",
        "pattern": "/" + str(value).replace("/", "\\/") + "/",
        "columns": ", ".join(value) if isinstance(value, list) else "",
    }
    return _SLOT.sub(lambda m: fill[m.group(1)], rule.pql)


#: Templates Prama ships, installed on request (`prama metadata template install`).
STARTER: dict[str, dict[str, Any]] = {
    "data-quality-attribute": {
        "name": "data-quality-attribute",
        "applies_to": "attribute",
        "description": "Common expectations of a column; each one proposes its check.",
        "fields": [
            {
                "name": "mandatory",
                "kind": "flag",
                "help": "Every row must have a value.",
                "rules": [
                    {"when": "true", "pql": "CHECK {{ dataset }}.{{ attribute }} IS NOT NULL"}
                ],
            },
            {
                "name": "unique",
                "kind": "flag",
                "help": "No two rows share a value.",
                "rules": [{"when": "true", "pql": "CHECK {{ dataset }}.{{ attribute }} IS UNIQUE"}],
            },
            {
                "name": "allowed_values",
                "kind": "list",
                "help": "The only values permitted.",
                "rules": [{"pql": "CHECK {{ dataset }}.{{ attribute }} IN {{ values }}"}],
            },
            {
                "name": "pattern",
                "kind": "text",
                "help": "A regular expression every value matches.",
                "rules": [{"pql": "CHECK {{ dataset }}.{{ attribute }} MATCHES {{ pattern }}"}],
            },
            {
                "name": "minimum",
                "kind": "number",
                "rules": [{"pql": "CHECK {{ dataset }}.{{ attribute }} >= {{ value }}"}],
            },
            {
                "name": "maximum",
                "kind": "number",
                "rules": [{"pql": "CHECK {{ dataset }}.{{ attribute }} <= {{ value }}"}],
            },
            {"name": "source_system", "kind": "text", "help": "Where this column comes from."},
            {"name": "pii", "kind": "flag", "help": "Personal data; masked in evidence."},
        ],
    },
    "data-quality-dataset": {
        "name": "data-quality-dataset",
        "applies_to": "dataset",
        "description": "Expectations of a whole dataset; each one proposes its check.",
        "fields": [
            {
                "name": "key",
                "kind": "columns",
                "help": "The columns that identify a row.",
                "rules": [{"pql": "CHECK {{ dataset }} HAS UNIQUE KEY ({{ columns }})"}],
            },
            {
                "name": "minimum_rows",
                "kind": "number",
                "rules": [{"pql": "CHECK {{ dataset }} HAS ROW COUNT AT LEAST {{ value }}"}],
            },
            {"name": "source_system", "kind": "text"},
            {
                "name": "retention_class",
                "kind": "choice",
                "choices": ["transient", "operational", "regulatory-7y", "permanent"],
            },
            {
                "name": "golden_source",
                "kind": "flag",
                "help": "This dataset is the book of record for what it holds.",
            },
        ],
    },
}
