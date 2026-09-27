"""Column lineage from a real SQL parser.

`sqlglot` parses about twenty dialects into a syntax tree, and its `lineage()`
follows a column through CTEs and subqueries to the table it came from, which
the regex extractor in `prama.lineage.sql` cannot do. This module produces the
same `Edge`s and named `Gap`s that extractor does, so the rest of Prama sees no
difference except more edges and fewer gaps.

What it keeps from the regex extractor, deliberately:

* **Ambiguity is reported, never guessed.** An unqualified column with more
  than one candidate table and no schema to decide becomes an `ambiguous`
  gap, not an edge to whichever table came first.
* **The same gap kinds** (`no_target`, `no_source`, `unnamed_output`,
  `ambiguous`), so a gap report reads the same whichever path produced it.
* **Filter columns feed the target as `FILTER` edges.**

`extract_statement` returns ``None`` when the statement does not parse. The
caller then falls back to the regex extractor and records that it did.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import lineage

from prama.lineage.graph import Column, Edge, Transform

#: Prama's dialect names to sqlglot's. "ansi" means sqlglot's default.
DIALECTS: dict[str, str | None] = {
    "ansi": None,
    "postgres": "postgres",
    "postgresql": "postgres",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "tsql": "tsql",
    "sqlserver": "tsql",
    "oracle": "oracle",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "redshift": "redshift",
    "databricks": "databricks",
    "spark": "spark",
    "teradata": "teradata",
    "mysql": "mysql",
    "trino": "trino",
    "db2": None,
}

#: Calls that keep a value essentially the same: renamed, cast, trimmed.
_RENAMING = (exp.Cast, exp.TryCast, exp.Coalesce, exp.Trim, exp.Upper, exp.Lower)


def _qualified(table: exp.Table) -> str:
    return ".".join(part for part in (table.catalog, table.db, table.name) if part)


def _transform(projection: Any) -> Transform:
    node = projection.this if isinstance(projection, exp.Alias) else projection
    if node.find(exp.AggFunc) is not None:
        return Transform.AGGREGATED
    if isinstance(node, exp.Column):
        return Transform.IDENTITY
    if isinstance(node, _RENAMING):
        return Transform.RENAME
    return Transform.DERIVED


def _gap(kind: str, detail: str, statement: str) -> Any:
    from prama.lineage.sql import Gap

    return Gap(kind=kind, detail=detail, statement=statement)


class _Scope:
    """The real tables a SELECT reads, by alias, and its CTE names."""

    def __init__(self, select: exp.Select) -> None:
        with_ = select.args.get("with")
        self.ctes = {cte.alias_or_name.lower() for cte in (with_.expressions if with_ else [])}
        self.aliases: dict[str, str] = {}
        for table in select.find_all(exp.Table):
            name = _qualified(table)
            if table.name.lower() in self.ctes:
                continue
            self.aliases[(table.alias or table.name).lower()] = name
            self.aliases[name.lower()] = name

    @property
    def tables(self) -> list[str]:
        return sorted(set(self.aliases.values()))


def _qualify(
    select: exp.Select, scope: _Scope, schema: Mapping[str, Sequence[str]], statement: str
) -> list[Any]:
    """Give every unqualified column its table, or report why it cannot be.

    Done on the tree before `lineage()` runs, so the parser's own resolution
    never guesses between two tables.
    """
    gaps: list[Any] = []
    if scope.ctes:
        # A CTE's columns are resolved by `lineage()` itself; qualifying
        # against the outer tables here would be wrong.
        return gaps
    tables = scope.tables
    for column in list(select.find_all(exp.Column)):
        if column.table:
            continue
        name = column.name.lower()
        owners = [t for t in tables if name in schema.get(t.lower(), ())]
        if len(owners) == 1 or (not owners and len(tables) == 1):
            owner = owners[0] if owners else tables[0]
            alias = next(
                (a for a, t in scope.aliases.items() if t == owner and a != owner.lower()),
                owner.rpartition(".")[2],
            )
            column.set("table", exp.to_identifier(alias))
        elif len(owners) > 1 or len(tables) > 1:
            candidates = owners or tables
            gaps.append(
                _gap(
                    "ambiguous",
                    f"{name!r} appears in more than one source ({', '.join(sorted(candidates))}) "
                    "and nothing says which. Supply the schema and this resolves",
                    statement,
                )
            )
    return gaps


def _leaves(name: str, select: exp.Expression, dialect: str | None) -> list[Column]:
    found: list[Column] = []
    for node in lineage(name, select, dialect=dialect).walk():
        if node.downstream or not isinstance(node.expression, exp.Table):
            continue
        # The leaf name keeps the source's identifier quoting ("x", [x]).
        column = node.name.rpartition(".")[2].strip('"`[]').lower()
        found.append(Column(dataset=_qualified(node.expression), name=column))
    return found


def extract_statement(
    statement: str,
    *,
    job: str,
    schema: Mapping[str, Sequence[str]],
    dialect: str = "ansi",
) -> tuple[list[Edge], list[Any]] | None:
    """Edges and gaps for one statement, or ``None`` if it does not parse."""
    read = DIALECTS.get(dialect.lower())
    try:
        tree = sqlglot.parse_one(statement, read=read)
    except SqlglotError:
        return None

    target_columns: list[str] = []
    if isinstance(tree, exp.Create):
        target_node = tree.this
        select = tree.expression
    elif isinstance(tree, exp.Insert):
        target_node = tree.this
        select = tree.expression
        if isinstance(target_node, exp.Schema):
            target_columns = [c.name.lower() for c in target_node.expressions]
    else:
        return [], [
            _gap(
                "no_target",
                "no INSERT INTO or CREATE TABLE/VIEW, so there is nothing for the columns to "
                "flow into. A bare SELECT tells you what was read and not where it went",
                statement,
            )
        ]
    table = target_node.find(exp.Table) if not isinstance(target_node, exp.Table) else target_node
    if table is None:
        return None
    target = _qualified(table)

    if isinstance(select, exp.Values) or select is None:
        return [], [
            _gap(
                "no_source",
                "the values are literals, so there is no upstream column for them to come from",
                statement,
            )
        ]
    if not isinstance(select, exp.Select):
        # A UNION or another set operation: left to the fallback, which says so.
        return None
    scope = _Scope(select)
    if not scope.tables and not scope.ctes:
        return [], [
            _gap(
                "no_source",
                "no FROM clause, so the values come from literals or a call",
                statement,
            )
        ]

    gaps = _qualify(select, scope, schema, statement)
    ambiguous = {g.detail.split("'")[1] for g in gaps if g.kind == "ambiguous"}
    edges: list[Edge] = []
    for index, projection in enumerate(select.selects):
        name = projection.alias_or_name.lower() if projection.alias_or_name else ""
        if index < len(target_columns) and not isinstance(projection, exp.Alias):
            name = target_columns[index]
        if not name or isinstance(projection, exp.Star):
            gaps.append(
                _gap(
                    "unnamed_output",
                    f"the expression {projection.sql()[:60]!r} has no alias and no obvious "
                    "name, so nothing can be said about which target column it feeds",
                    statement,
                )
            )
            continue
        if any(
            c.name.lower() in ambiguous and not c.table for c in projection.find_all(exp.Column)
        ):
            continue
        try:
            sources = _leaves(projection.alias_or_name, select, read)
        except SqlglotError:
            return None
        transform = _transform(projection)
        text = (projection.this if isinstance(projection, exp.Alias) else projection).sql()
        seen: set[str] = set()
        for source in sources:
            if source.qualified in seen:
                continue
            seen.add(source.qualified)
            edges.append(
                Edge(
                    source=source,
                    target=Column(dataset=target, name=name),
                    transform=transform,
                    produced_by=job,
                    expression=text[:120],
                )
            )

    where = select.args.get("where")
    if where is not None:
        seen_filters: set[str] = set()
        for column in where.find_all(exp.Column):
            dataset = scope.aliases.get(column.table.lower()) if column.table else None
            if dataset is None or f"{dataset}.{column.name}" in seen_filters:
                continue
            seen_filters.add(f"{dataset}.{column.name}")
            edges.append(
                Edge(
                    source=Column(dataset=dataset, name=column.name.lower()),
                    target=Column(dataset=target, name="*"),
                    transform=Transform.FILTER,
                    produced_by=job,
                    expression="WHERE",
                )
            )
    return edges, gaps
