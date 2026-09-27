"""Column lineage from a Power BI model: where each report column and measure comes from.

Reads the tabular model (`DataModelSchema` inside a `.pbit`, or a `model.bim`),
never Power BI itself. Three things are followed, each only where its meaning
is certain:

* **Power Query sources.** A table navigated from a database
  (`Source{[Schema="dbo",Item="Trades"]}[Data]`) maps each model column to its
  source column, through any `Table.RenameColumns`. A native query
  (`Sql.Database(…, [Query="SELECT …"])` or `Value.NativeQuery`) is read by the
  SQL parser.
* **DAX references** in measures and calculated columns: `'Table'[Column]`,
  `Table[Column]`, and `[Measure]` within the model. A measure that is one
  aggregate over one column is `aggregated`; anything else is `derived`.
* **Everything else is a named gap**: a web or file source, a merge, a custom
  function, an M step this reader does not follow.

Model objects are named `powerbi.<model>.<table>`, so a report measure sits in
the same graph as the warehouse column it is built from, and an impact
analysis from a defective column reaches the dashboard.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Extraction, Gap, SqlLineage

#: The largest model schema read, uncompressed. A real model is a few MB.
MAX_SCHEMA = 64 << 20

_NAVIGATION = re.compile(
    r'\{\s*\[\s*Schema\s*=\s*"([^"]+)"\s*,\s*Item\s*=\s*"([^"]+)"\s*\]\s*\}\s*\[\s*Data\s*\]'
)
_NATIVE = re.compile(r'(?:Query\s*=|Value\.NativeQuery\s*\([^,]+,)\s*"((?:[^"]|"")*)"', re.S)
_RENAMES = re.compile(r"Table\.RenameColumns\s*\([^{]*\{(.*?)\}\s*\)", re.S)
_PAIR = re.compile(r'\{\s*"((?:[^"]|"")*)"\s*,\s*"((?:[^"]|"")*)"\s*\}')
_UNFOLLOWED = re.compile(
    r"\b(Web\.Contents|Csv\.Document|Excel\.Workbook|Table\.NestedJoin|Table\.Combine|"
    r"Table\.AddColumn|Table\.Group|Table\.Pivot|Table\.Unpivot)\b"
)
_TABLE_COLUMN = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_][\w]*))\s*\[([^\]]+)\]")
_BARE = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
_ONE_AGGREGATE = re.compile(
    r"^\s*(SUM|AVERAGE|MIN|MAX|COUNT|COUNTA|DISTINCTCOUNT)\s*\(\s*[^()]+\)\s*$", re.I
)


def schema_of(content: bytes, filename: str) -> dict[str, Any]:
    """The model JSON from a `.pbit` (zip, UTF-16) or a `model.bim` (JSON)."""
    if filename.lower().endswith(".pbit"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            info = archive.getinfo("DataModelSchema")
            if info.file_size > MAX_SCHEMA:
                raise ValueError("the model schema is larger than this reader accepts")
            raw = archive.read(info)
        text = raw.decode("utf-16-le" if raw[:2] != b"\xef\xbb" else "utf-8-sig").lstrip("﻿")
    else:
        text = content.decode("utf-8-sig")
    return dict(json.loads(text))


def _name(text: str) -> str:
    return re.sub(r"[^\w]+", "_", text.strip()).strip("_").lower() or "unnamed"


def _expression(value: Any) -> str:
    return "\n".join(value) if isinstance(value, list) else str(value or "")


def extract(model: dict[str, Any], *, name: str, job: str = "") -> Extraction:
    """Edges and gaps from one tabular model."""
    root = model.get("model") or model
    # The model's own name when it has one; a `model.bim` is always called that.
    prefix = f"powerbi.{_name(str(model.get('name') or name))}"
    tables = root.get("tables") or []
    edges: list[Edge] = []
    gaps: list[Gap] = []
    measures: dict[str, str] = {}
    for table in tables:
        for measure in table.get("measures") or []:
            measures[str(measure.get("name", "")).lower()] = _name(str(table.get("name", "")))

    def gap(where: str, why: str) -> None:
        gaps.append(Gap(kind="unread", detail=f"{where}: {why}", statement=job or name))

    for table in tables:
        tname = str(table.get("name", ""))
        dataset = f"{prefix}.{_name(tname)}"
        columns = {
            str(c.get("sourceColumn") or c.get("name")): str(c.get("name"))
            for c in table.get("columns") or []
            if c.get("type") != "calculated" and not str(c.get("name", "")).startswith("RowNumber")
        }
        for partition in table.get("partitions") or []:
            source = partition.get("source") or {}
            expression = _expression(source.get("expression") or source.get("query"))
            edges.extend(_partition(expression, dataset, columns, f"{tname}", gap, job or name))
        for column in table.get("columns") or []:
            if column.get("type") == "calculated":
                target = Column(dataset=dataset, name=str(column.get("name", "")).lower())
                edges.extend(
                    _dax(
                        _expression(column.get("expression")), target, prefix, tname, measures, job
                    )
                )
        for measure in table.get("measures") or []:
            target = Column(dataset=dataset, name=str(measure.get("name", "")).lower())
            found = _dax(
                _expression(measure.get("expression")), target, prefix, tname, measures, job
            )
            if not found:
                gap(
                    f"{tname}[{measure.get('name')}]", "a measure with no column reference followed"
                )
            edges.extend(found)
    return Extraction(edges=tuple(edges), gaps=tuple(gaps), statements=max(1, len(tables)))


def _partition(
    expression: str, dataset: str, columns: dict[str, str], where: str, gap: Any, job: str
) -> list[Edge]:
    if not expression.strip():
        return []
    unfollowed = _UNFOLLOWED.findall(expression)
    if unfollowed:
        gap(where, f"Power Query uses {', '.join(sorted(set(unfollowed)))}, not followed")
        return []
    native = _NATIVE.search(expression)
    if native:
        sql = native.group(1).replace('""', '"').replace("#(lf)", "\n")
        extraction = SqlLineage().extract(f"CREATE VIEW {dataset} AS {sql}", job=job)
        for g in extraction.gaps:
            gap(where, f"in the native query: {g.detail}")
        return [
            Edge(
                e.source,
                Column(dataset, columns.get(e.target.name, e.target.name).lower()),
                e.transform,
                produced_by=job,
                expression="native query",
            )
            for e in extraction.edges
        ]
    navigation = _NAVIGATION.findall(expression)
    if len(navigation) != 1:
        gap(where, "a Power Query source this reader does not follow")
        return []
    schema, item = navigation[0]
    source = f"{schema}.{item}".lower()
    renamed = {
        new.replace('""', '"'): old.replace('""', '"')
        for block in _RENAMES.findall(expression)
        for old, new in _PAIR.findall(block)
    }
    return [
        Edge(
            Column(source, renamed.get(output, output).lower()),
            Column(dataset, model_name.lower()),
            Transform.RENAME if renamed.get(output, output) != model_name else Transform.IDENTITY,
            produced_by=job,
            expression="power query",
        )
        for output, model_name in columns.items()
    ]


def _dax(
    expression: str, target: Column, prefix: str, table: str, measures: dict[str, str], job: str
) -> list[Edge]:
    inputs: set[Column] = set()
    for quoted, plain, column in _TABLE_COLUMN.findall(expression):
        owner = (quoted.replace("''", "'") if quoted else plain) or table
        inputs.add(Column(f"{prefix}.{_name(owner)}", column.strip().lower()))
    stripped = _TABLE_COLUMN.sub("", expression)
    for reference in _BARE.findall(stripped):
        key = reference.strip().lower()
        owner = measures.get(key, _name(table))
        inputs.add(Column(f"{prefix}.{owner}", key))
    inputs.discard(target)
    transform = (
        Transform.AGGREGATED
        if len(inputs) == 1 and _ONE_AGGREGATE.match(expression)
        else Transform.DERIVED
    )
    return [
        Edge(source, target, transform, produced_by=job, expression=expression.strip()[:200])
        for source in sorted(inputs, key=lambda c: (c.dataset, c.name))
    ]
