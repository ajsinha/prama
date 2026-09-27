"""Scanning a SQL source into the lineage store.

Statement by statement, so each edge carries how it was found: an edge the SQL
parser produced is `parsed` at full confidence, and one the pattern reader
produced after the parser gave up is `inferred` at lower confidence, for a
person to review. Takes the unit of work opaquely; `prama.lineage` imports
nothing from `prama.db`.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from prama.lineage.sql import SqlLineage, split_statements

#: Confidence of an edge read by the pattern reader after the parser failed.
FALLBACK_CONFIDENCE = 0.8


async def scan_sql(
    uow: Any,
    tenant_id: str,
    *,
    source: str,
    sql: str,
    location: str = "",
    dialect: str = "ansi",
    schema: Mapping[str, Sequence[str]] | None = None,
    job: str = "",
    by: str | None = None,
) -> Any:
    """Read *sql* into the store as a run of the named source. Returns the run."""
    lineage = SqlLineage(schema=schema, dialect=dialect)
    row = await uow.lineage.ensure_source(
        tenant_id, source, kind="sql", location=location, dialect=dialect, by=by
    )
    batches: list[tuple[Any, str, str, float]] = []
    gaps: list[Any] = []
    statements = unparsed = 0
    for statement in split_statements(sql):
        extraction = lineage.extract(statement, job=job or source)
        statements += 1
        fell_back = any(g.kind == "regex_fallback" for g in extraction.gaps)
        if fell_back:
            batches.append((extraction.edges, "parsed:regex", "inferred", FALLBACK_CONFIDENCE))
        else:
            batches.append((extraction.edges, "parsed:sqlglot", "parsed", 1.0))
        if any(g.kind == "unparsed" for g in extraction.gaps):
            unparsed += 1
        gaps.extend(extraction.gaps)
    understood = 1.0 - unparsed / statements if statements else 0.0
    return await uow.lineage.record_run(
        tenant_id, row, batches, gaps, statements=statements, understood=understood, by=by
    )
