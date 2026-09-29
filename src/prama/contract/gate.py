"""Reading a contract and rows from text, and the check a build gates on.

Shared by ``prama contract`` and ``/api/v1/contracts``, so the gate a pipeline
calls over HTTP and the one it runs as a command are the same gate. The check
used to live inside the command, where an API would have had to restate it;
and the one time the check was already split between two output paths, the
JSON path let an empty file through (see `check`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from prama.contract import odcs, quality
from prama.contract.diff import compare, compare_schema
from prama.core.errors import ValidationError


def _is_yaml(name: str) -> bool:
    return name.lower().endswith((".yaml", ".yml"))


def document_from_text(text: str, *, name: str, what: str = "contract") -> dict[str, Any]:
    """A contract document from JSON or YAML text, YAML chosen by *name*'s suffix."""
    try:
        if _is_yaml(name):
            import yaml

            parsed = yaml.safe_load(text)
        else:
            parsed = json.loads(text)
    except Exception as exc:
        syntax = "YAML" if _is_yaml(name) else "JSON"
        raise ValidationError(
            f"{name} could not be read as {syntax}",
            remedy="Check the syntax.",
            context={"path": name},
            cause=exc,
        ) from exc
    if not isinstance(parsed, dict):
        # A bare scalar parses cleanly and is then used as a mapping downstream:
        # `'str' object has no attribute 'get'`, several frames from here, with
        # nothing naming the file. QA round 4, `CTR-060`.
        raise ValidationError(
            f"{name} does not hold a {what}",
            remedy=(
                f"A {what} is an object with named fields. This file parses, but "
                f"it holds a {type(parsed).__name__} — check it is the right file."
            ),
            context={"path": name},
        )
    return parsed


def rows_from_text(text: str, *, name: str) -> list[dict[str, Any]]:
    """Rows from JSON, JSON Lines or CSV, chosen by *name*'s suffix."""
    lowered = name.lower()
    if lowered.endswith(".csv"):
        return list(csv.DictReader(io.StringIO(text, newline="")))
    # A truncated or hand-edited data file used to reach the terminal as a
    # json.decoder stack trace. The position is the useful part of that trace
    # and is the part kept. QA round 3, Q-68.
    if lowered.endswith((".jsonl", ".ndjson")):
        rows: list[dict[str, Any]] = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(
                    f"{name} line {number} is not valid JSON: {exc.msg} at column {exc.colno}",
                    remedy=(
                        "Each line of a .jsonl file is one complete JSON object. "
                        "A trailing comma or an unclosed brace makes the line unreadable."
                    ),
                    context={"path": name, "line": number},
                ) from None
        return rows
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{name} is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}",
            remedy="Give a JSON array of rows, a .jsonl file, or a .csv.",
            context={"path": name, "line": exc.lineno, "column": exc.colno},
        ) from None
    if isinstance(payload, dict):
        payload = payload.get("rows", [])
    if not isinstance(payload, list):
        raise ValidationError(
            f"{name} does not hold a list of rows",
            remedy="Give a JSON array, a .jsonl file, or a .csv.",
            context={"path": name},
        )
    return payload


def check(
    document: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    allow_additions: bool = False,
    contract: str = "",
) -> dict[str, Any]:
    """Whether *rows* keep the promises *document* makes about its schema.

    ``breached`` is the gate. A missing promised column and an empty required
    one are breaches; an unexpected column is one too unless additions are
    allowed, because a removed column breaks every consumer and an added one
    breaks none, and blocking both is how a gate gets switched off.
    """
    result = odcs.load(document)
    if result.declaration is None:
        raise ValidationError(
            "that contract declares no schema, so there is nothing to check against",
            remedy="Check the file.",
            context={"contract": contract},
        )

    promised = {a.name: a for a in result.declaration.attributes}
    present = {column for row in rows for column in row}

    schema = compare_schema(list(promised), present)
    missing = schema.removed
    extra = schema.added

    # A promised-mandatory column that is null anywhere is a breach too: the
    # contract's `required` is a promise about values, not only about the
    # column existing, and checking only the header would pass a table of
    # nulls.
    empty_mandatory = tuple(
        sorted(
            name
            for name, attribute in promised.items()
            if attribute.optionality.name == "MANDATORY"
            and name in present
            and any(row.get(name) in (None, "") for row in rows)
        )
    )

    # An empty file establishes nothing, so it is never a pass. Decided here,
    # once, because it used to be decided after the `--json` early return:
    # `prama contract check` refused an empty file and `prama --json contract
    # check` — the spelling a build uses — let it through with exit 0. It is
    # also reported as its own field, because a caller parsing the result
    # cannot otherwise tell "nothing was checked" from "checked, and every
    # promise held".
    checked = bool(rows)
    breached = (
        not checked or bool(missing or empty_mandatory) or (bool(extra) and not allow_additions)
    )
    return {
        "contract": contract,
        "rows": len(rows),
        # With no rows the column comparison is vacuous — every promised
        # column looks absent because there is nothing for it to be in — so
        # reporting it as a schema breach would name the wrong cause.
        "missing_columns": list(missing) if checked else [],
        "unexpected_columns": list(extra) if checked else [],
        "mandatory_with_nulls": list(empty_mandatory) if checked else [],
        "checked": checked,
        "breached": breached,
    }


def imported(document: dict[str, Any]) -> dict[str, Any]:
    """An ODCS contract read as a declaration, with what did not come across.

    The quality blocks are always included. A contract's quality blocks are
    the part a consumer is relying on, and importing the schema while silently
    taking on none of the checks is the failure this whole package is about.
    """
    result = odcs.load(document)
    checks = quality.controls_from(document)
    declaration = result.declaration
    return {
        **result.to_dict(),
        "dataset": (
            {
                "name": declaration.name,
                "description": declaration.description,
                "purpose": declaration.purpose,
                "criticality": declaration.criticality.name,
                "attributes": [
                    {
                        "name": attribute.name,
                        "definition": attribute.definition,
                        "semantic_type": attribute.semantic_type,
                        "optionality": attribute.optionality.name.lower(),
                    }
                    for attribute in declaration.attributes
                ],
            }
            if declaration is not None
            else None
        ),
        "quality": checks.to_dict(),
    }


def difference(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    *,
    key: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict[str, Any]:
    """What changed between two versions of a dataset, matched by *key*."""
    return compare(before, after, key=key or [], ignore=ignore or []).to_dict()


async def exported(uow: Any, tenant_id: str, dataset: str) -> dict[str, Any]:
    """A declared dataset, by slug, as an ODCS contract document."""
    from prama.core.errors import NotFoundError
    from prama.derive.persisted import dataset_declaration_of

    versions = await uow.datasets.list_current(tenant_id, limit=5000)
    version = next((v for v in versions if v.slug == dataset), None)
    if version is None:
        raise NotFoundError(
            f"no dataset called {dataset!r} is declared",
            remedy="Check the slug against `prama estate export`.",
            context={"dataset": dataset},
        )
    attributes = await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id)
    return odcs.dump(dataset_declaration_of(version, attributes))


__all__ = ["check", "difference", "document_from_text", "exported", "imported", "rows_from_text"]
