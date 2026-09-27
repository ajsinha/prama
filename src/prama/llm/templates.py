"""Prompt templates: versioned instructions, rendered with untrusted values fenced.

A template is the system text and body a feature sends a model, with named
`{{ variables }}`. It is versioned like a profile, because a change to the
instructions is a change to every proposal made with them, and a version is
approved before it is used (with `llm.eval.gate_activation`, only after an
evaluation run of that exact version passed).

Rendering does three things a hand-built prompt forgets:

* **Fences every untrusted value** (`prama.assistant.safety.fence`): estate
  data reaches the model marked as data, never as instructions.
* **Sets the request's sensitivity** to the highest any variable declares, so
  residency is decided by what is actually in the prompt.
* **Records which template version** produced the request, on the call ledger.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from prama.core.errors import ValidationError
from prama.llm.spi import Request
from prama.semantic.values import Sensitivity

_SLOT = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_ORDER = [s.value for s in Sensitivity]


@dataclasses.dataclass(frozen=True, slots=True)
class Variable:
    name: str
    sensitivity: str = "internal"
    #: Only for values Prama itself composed (a control's PQL, a count).
    #: Anything from the estate or a person is untrusted and fenced.
    trusted: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    body: str
    system: str = ""
    variables: tuple[Variable, ...] = ()
    response_schema: dict[str, Any] | None = None
    version: int = 0
    template_id: str = ""

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            {
                "system": self.system,
                "body": self.body,
                "variables": [dataclasses.asdict(v) for v in self.variables],
                "schema": self.response_schema,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def check(self) -> None:
        """Every slot is declared, every declaration is used, every sensitivity is known."""
        used = set(_SLOT.findall(self.body)) | set(_SLOT.findall(self.system))
        declared = {v.name for v in self.variables}
        problems = []
        if used - declared:
            problems.append(f"undeclared variable(s): {', '.join(sorted(used - declared))}")
        if declared - used:
            problems.append(f"declared but unused: {', '.join(sorted(declared - used))}")
        bad = [v.name for v in self.variables if v.sensitivity not in _ORDER]
        if bad:
            problems.append(f"unknown sensitivity on {', '.join(bad)}")
        if not self.body.strip():
            problems.append("the body is empty")
        if problems:
            raise ValidationError(
                f"the template {self.name} is not well formed: {'; '.join(problems)}",
                remedy="Declare each {{ variable }} once, with a sensitivity from the catalogue.",
            )

    def render(self, values: Mapping[str, Any], **options: Any) -> Request:
        """The request for *values*. Refuses a missing or unexpected value."""
        from prama.assistant.safety import fence

        declared = {v.name: v for v in self.variables}
        missing = sorted(set(declared) - set(values))
        extra = sorted(set(values) - set(declared))
        if missing or extra:
            raise ValidationError(
                f"the template {self.name} was given the wrong values",
                remedy=f"Missing: {', '.join(missing) or 'none'}; unexpected: "
                f"{', '.join(extra) or 'none'}.",
            )

        def fill(text: str) -> str:
            def one(match: re.Match[str]) -> str:
                variable = declared[match.group(1)]
                value = values[variable.name]
                if variable.trusted:
                    return str(value)
                return fence(value, provenance=f"{self.name}:{variable.name}").render()

            return _SLOT.sub(one, text)

        sensitivity = max(
            (_ORDER.index(v.sensitivity) for v in self.variables), default=_ORDER.index("internal")
        )
        context = dict(options.pop("context", {}) or {})
        if self.template_id:
            context.update(template_id=self.template_id, template_version=str(self.version))
        return Request(
            system=fill(self.system),
            prompt=fill(self.body),
            sensitivity=Sensitivity(_ORDER[sensitivity]),
            context=context,
            **options,
        )


def parse(document: Mapping[str, Any]) -> PromptTemplate:
    """A template from its YAML/JSON form: name, system, body, variables, response_schema."""
    variables = tuple(
        Variable(
            name=str(v["name"]) if isinstance(v, Mapping) else str(v),
            sensitivity=str(v.get("sensitivity", "internal"))
            if isinstance(v, Mapping)
            else "internal",
            trusted=bool(v.get("trusted", False)) if isinstance(v, Mapping) else False,
        )
        for v in document.get("variables") or []
    )
    template = PromptTemplate(
        name=str(document.get("name", "")).strip(),
        system=str(document.get("system", "")),
        body=str(document.get("body", "")),
        variables=variables,
        response_schema=document.get("response_schema"),
    )
    if not template.name:
        raise ValidationError("a template needs a name", remedy="Add `name:` to the document.")
    template.check()
    return template
