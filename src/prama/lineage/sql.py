"""Column-level lineage read out of SQL.

`FR-LIN-003`, and the honest way into the docs/20 G2 gap. Most of an
enterprise's lineage is not in dbt or OpenLineage; it is in views, stored
procedures and ETL jobs that nobody has touched in eight years, and the only
description of what they do is the SQL itself.

**This is a lineage extractor, not a SQL engine, and the distinction is the
whole design.** A parser that tries to be complete will fail on the first
dialect quirk and produce nothing. One that extracts what it can and *reports
what it could not* produces a partial graph that is useful immediately and
gets better — and, crucially, a partial graph whose gaps are visible is worth
far more than a complete-looking one whose gaps are not.

So every statement produces edges *and* a confession: which clauses were not
understood, which references could not be resolved to a source table, which
expressions were too complex to attribute. A lineage graph that quietly drops
a CASE expression looks the same as one that handled it, and the impact
analysis built on it is wrong in a way nobody can see.

**Ambiguous columns are reported rather than guessed.** ``SELECT amount FROM a
JOIN b`` where both have an ``amount`` is genuinely ambiguous, and picking one
produces an edge that is wrong half the time. Naming the ambiguity lets
somebody supply the schema that resolves it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import Any

from prama.backend.sql import _AGGREGATES as _COMPILED_AGGREGATES
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

#: Aggregate functions, which mark an edge as attenuating. Recognised by name
#: because that is the only signal available without a type system.
#:
#: Two sources, deliberately. The names below are what *other people's* SQL uses
#: — this module reads warehouse views it did not write, so it must know
#: `percentile_cont` and `listagg` even though Prama never emits them. Union'd
#: with what Prama's own compiler emits, because anything the backend renders as
#: an aggregate certainly is one, and the two lists were maintained separately
#: until `approx_count_distinct` turned out to be in the compiler and not here —
#: so an edge through it was not marked attenuating. QA round 4.
_FOREIGN_AGGREGATES = frozenset(
    {
        "sum",
        "avg",
        "count",
        "min",
        "max",
        "stddev",
        "variance",
        "median",
        "percentile_cont",
        "percentile_disc",
        "array_agg",
        "string_agg",
        "listagg",
    }
)

_AGGREGATES = _FOREIGN_AGGREGATES | {name.lower() for name in _COMPILED_AGGREGATES}

#: An aggregate call, bounded so a longer name that merely ends in one is not
#: mistaken for it. Built from `_AGGREGATES` rather than restated, so a name
#: added there is matched here without anybody remembering to.
_AGGREGATE_CALL = re.compile(
    r"(?<![a-z0-9_])(" + "|".join(sorted(_AGGREGATES, key=len, reverse=True)) + r")\s*\("
)

#: As above, for the cast that marks a rename.
_CAST_CALL = re.compile(r"(?<![a-z0-9_])cast\s*\(")


_SELECT = re.compile(r"\bselect\b(?P<body>.*?)\bfrom\b", re.IGNORECASE | re.DOTALL)
_INSERT = re.compile(
    r"\binsert\s+into\s+(?P<target>[\w.\"\[\]]+)\s*(\((?P<columns>[^)]*)\))?",
    re.IGNORECASE,
)
_CREATE = re.compile(
    r"\bcreate\s+(or\s+replace\s+)?(table|view)\s+(?P<target>[\w.\"\[\]]+)",
    re.IGNORECASE,
)
#: The alias group must refuse to match a keyword, and the reason is a bug this
#: found the hard way: without the lookahead, ``FROM a JOIN b`` matches with
#: alias="JOIN", the regex consumes it, and `finditer` resumes past the joined
#: table — so every table after the first was silently dropped and the
#: extractor produced a confident half-graph.
_ALIAS_STOP = (
    r"on|join|inner|left|right|outer|full|cross|where|group|order|having|"
    r"union|limit|offset|using|as|and|or|set|values"
)
_FROM = re.compile(
    rf"\b(from|join)\s+(?P<table>[\w.\"\[\]]+)"
    rf"(\s+(as\s+)?(?!(?:{_ALIAS_STOP})\b)(?P<alias>[a-z_][\w]*))?",
    re.IGNORECASE,
)
_WHERE = re.compile(
    r"\bwhere\b(?P<body>.*?)(\bgroup\s+by\b|\border\s+by\b|$)", re.IGNORECASE | re.DOTALL
)
_IDENTIFIER = re.compile(r"(?P<qualifier>[a-z_][\w]*)\.(?P<column>[a-z_][\w]*)", re.IGNORECASE)
_BARE = re.compile(r"(?<![\w.])(?P<column>[a-z_][\w]*)(?![\w.(])", re.IGNORECASE)

_KEYWORDS = frozenset(
    {
        "select",
        "from",
        "where",
        "join",
        "inner",
        "left",
        "right",
        "outer",
        "full",
        "on",
        "and",
        "or",
        "not",
        "as",
        "case",
        "when",
        "then",
        "else",
        "end",
        "null",
        "group",
        "by",
        "order",
        "having",
        "distinct",
        "union",
        "all",
        "with",
        "over",
        "partition",
        "asc",
        "desc",
        "is",
        "in",
        "like",
        "between",
        "cast",
        "coalesce",
        "true",
        "false",
        "insert",
        "into",
        "values",
        "create",
        "replace",
        "table",
        "view",
        "cross",
        "using",
        "limit",
        "offset",
    }
)


#: Type names, which look exactly like bare column references inside a CAST and
#: are not. Without these, ``CAST(p.ccy AS VARCHAR)`` reports `varchar` as an
#: ambiguous column — a gap that is not a gap, and the fastest way to make a
#: gap report something nobody reads.
_TYPES = frozenset(
    {
        "varchar",
        "nvarchar",
        "char",
        "nchar",
        "text",
        "int",
        "integer",
        "bigint",
        "smallint",
        "tinyint",
        "decimal",
        "numeric",
        "float",
        "real",
        "double",
        "precision",
        "date",
        "datetime",
        "timestamp",
        "time",
        "boolean",
        "bool",
        "bytes",
        "blob",
        "clob",
        "uuid",
        "json",
        "jsonb",
        "money",
        "interval",
    }
)


@dataclasses.dataclass(frozen=True, slots=True)
class Gap:
    """Something the parser did not understand, named so it can be fixed."""

    kind: str
    detail: str
    statement: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "statement": self.statement[:200]}


@dataclasses.dataclass(frozen=True, slots=True)
class Extraction:
    """Edges found, and everything not understood.

    The second half matters as much as the first. A lineage graph that quietly
    drops a CASE expression looks identical to one that handled it, and the
    impact analysis built on it is wrong in a way nobody can see.
    """

    edges: tuple[Edge, ...] = ()
    gaps: tuple[Gap, ...] = ()
    statements: int = 0

    @property
    def understood(self) -> float:
        """Rough fraction of statements that produced any lineage at all."""
        if not self.statements:
            return 0.0
        failed = len({gap.statement for gap in self.gaps if gap.kind == "unparsed"})
        return 1.0 - failed / self.statements

    def into(self, graph: LineageGraph | None = None) -> LineageGraph:
        target = graph or LineageGraph()
        target.add_all(self.edges)
        return target

    def describe(self) -> str:
        head = (
            f"{len(self.edges)} column edges from {self.statements} statement"
            f"{'s' if self.statements != 1 else ''}"
        )
        if not self.gaps:
            return head
        kinds: dict[str, int] = {}
        for gap in self.gaps:
            kinds[gap.kind] = kinds.get(gap.kind, 0) + 1
        return (
            f"{head}; {len(self.gaps)} thing"
            f"{'' if len(self.gaps) == 1 else 's'} not understood ("
            + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
            + "). A partial graph whose gaps are visible is worth more than a "
            "complete-looking one whose gaps are not"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [edge.to_dict() for edge in self.edges],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "statements": self.statements,
            "understood": round(self.understood, 4),
            "summary": self.describe(),
        }


class SqlLineage:
    """Reads column lineage out of SELECT, INSERT and CREATE statements."""

    def __init__(
        self,
        *,
        #: Known columns per table, which is what resolves an unqualified
        #: reference in a join. Without it, ambiguity is reported rather than
        #: guessed at.
        schema: Mapping[str, Sequence[str]] | None = None,
        dialect: str = "ansi",
    ) -> None:
        self._schema = {
            table.lower(): [column.lower() for column in columns]
            for table, columns in (schema or {}).items()
        }
        self._dialect = dialect

    def extract(self, sql: str, *, job: str = "") -> Extraction:
        edges: list[Edge] = []
        gaps: list[Gap] = []
        statements = [
            statement.strip() for statement in re.split(r";\s*(?:\n|$)", sql) if statement.strip()
        ]

        for statement in statements:
            found, problems = self._statement(statement, job)
            edges.extend(found)
            gaps.extend(problems)

        return Extraction(edges=tuple(edges), gaps=tuple(gaps), statements=len(statements))

    # -- one statement -----------------------------------------------------

    def _statement(self, sql: str, job: str) -> tuple[list[Edge], list[Gap]]:
        target = self._target(sql)
        if target is None:
            return [], [
                Gap(
                    kind="no_target",
                    detail=(
                        "no INSERT INTO or CREATE TABLE/VIEW, so there is nothing for "
                        "the columns to flow into. A bare SELECT tells you what was "
                        "read and not where it went"
                    ),
                    statement=sql,
                )
            ]

        select = _SELECT.search(sql)
        if select is None:
            # A VALUES insert is not a parse failure. It genuinely has no
            # lineage — the values are literals — and classifying it as
            # unparsed would put it in the pile of things somebody should go
            # and improve the parser for.
            literal = re.search(r"\bvalues\s*\(", sql, re.IGNORECASE) is not None
            return [], [
                Gap(
                    kind="no_source" if literal else "unparsed",
                    detail=(
                        "the values are literals, so there is no upstream column for "
                        "them to come from"
                        if literal
                        else "no SELECT clause found"
                    ),
                    statement=sql,
                )
            ]

        sources = self._sources(sql)
        if not sources:
            return [], [
                Gap(
                    kind="no_source",
                    detail="no FROM clause, so the values come from literals or a call",
                    statement=sql,
                )
            ]

        target_columns = self._target_columns(sql)
        edges: list[Edge] = []
        gaps: list[Gap] = []

        for index, item in enumerate(self._select_items(select.group("body"))):
            expression, alias = item
            name = alias or (
                target_columns[index]
                if index < len(target_columns)
                else self._implied_name(expression)
            )
            if name is None:
                gaps.append(
                    Gap(
                        kind="unnamed_output",
                        detail=(
                            f"the expression {expression.strip()[:60]!r} has no alias "
                            f"and no obvious name, so nothing can be said about which "
                            f"target column it feeds"
                        ),
                        statement=sql,
                    )
                )
                continue

            transform = self._transform(expression)
            references, ambiguous = self._references(expression, sources)
            for reference in references:
                edges.append(
                    Edge(
                        source=reference,
                        target=Column(dataset=target, name=name.lower()),
                        transform=transform,
                        produced_by=job,
                        expression=expression.strip()[:120],
                    )
                )
            gaps.extend(
                Gap(
                    kind="ambiguous",
                    detail=(
                        f"{column!r} appears in more than one source "
                        f"({', '.join(sorted(candidates))}) and nothing says which. "
                        f"Supply the schema and this resolves"
                    ),
                    statement=sql,
                )
                for column, candidates in ambiguous.items()
            )

        edges.extend(self._filter_edges(sql, sources, target, job))
        return edges, gaps

    def _filter_edges(
        self, sql: str, sources: Mapping[str, str], target: str, job: str
    ) -> list[Edge]:
        """Columns in a WHERE clause feed the target too, as filters.

        A wrong filter changes which rows exist, which is often worse than a
        wrong value — and a lineage graph that only follows the SELECT list
        misses it entirely, so the impact analysis says the filter column has
        no consumers.
        """
        where = _WHERE.search(sql)
        if where is None:
            return []
        references, _ = self._references(where.group("body"), sources)
        return [
            Edge(
                source=reference,
                target=Column(dataset=target, name="*"),
                transform=Transform.FILTER,
                produced_by=job,
                expression="WHERE",
            )
            for reference in references
        ]

    # -- pieces ------------------------------------------------------------

    @staticmethod
    def _target(sql: str) -> str | None:
        for pattern in (_INSERT, _CREATE):
            found = pattern.search(sql)
            if found:
                return _clean(found.group("target"))
        return None

    @staticmethod
    def _target_columns(sql: str) -> list[str]:
        found = _INSERT.search(sql)
        if not found or not found.group("columns"):
            return []
        return [_clean(part).lower() for part in found.group("columns").split(",")]

    @staticmethod
    def _sources(sql: str) -> dict[str, str]:
        """Alias (and bare name) to table, so a qualifier can be resolved."""
        sources: dict[str, str] = {}
        for found in _FROM.finditer(sql):
            table = _clean(found.group("table"))
            if table.lower() in _KEYWORDS:
                continue
            alias = found.group("alias")
            if alias and alias.lower() not in _KEYWORDS:
                sources[alias.lower()] = table
            sources[table.lower()] = table
            sources[table.rpartition(".")[2].lower()] = table
        return sources

    @staticmethod
    def _select_items(body: str) -> list[tuple[str, str | None]]:
        """Split a SELECT list on commas that are not inside brackets."""
        items: list[tuple[str, str | None]] = []
        depth = 0
        current: list[str] = []
        for character in body:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            if character == "," and depth == 0:
                items.append(_split_alias("".join(current)))
                current = []
                continue
            current.append(character)
        if "".join(current).strip():
            items.append(_split_alias("".join(current)))
        return items

    @staticmethod
    def _transform(expression: str) -> Transform:
        lowered = expression.lower()
        # Word-bounded, not a substring search. `any(f"{name}(" in lowered)`
        # read `discount(price)` as an aggregate because it contains `count(`,
        # and `checksum(x)` because it contains `sum(` — so an ordinary derived
        # column was classified as summed over many rows, its edge attenuated
        # to 0.35, and it could fall below the impact floor and disappear from
        # the graph entirely (QA finding LIN-030).
        #
        # Lineage that quietly drops an edge is worse than lineage that has
        # none: an impact analysis run against it comes back clean.
        if _AGGREGATE_CALL.search(lowered):
            return Transform.AGGREGATED
        stripped = expression.strip()
        if _IDENTIFIER.fullmatch(stripped) or _BARE.fullmatch(stripped):
            return Transform.IDENTITY
        # `cast(` had the same flaw — `broadcast(` contains it.
        if _CAST_CALL.search(lowered) or lowered.startswith("coalesce("):
            return Transform.RENAME
        return Transform.DERIVED

    def _references(
        self, expression: str, sources: Mapping[str, str]
    ) -> tuple[list[Column], dict[str, set[str]]]:
        """Columns an expression reads, and the ones that cannot be resolved."""
        found: list[Column] = []
        ambiguous: dict[str, set[str]] = {}
        seen: set[str] = set()

        for match in _IDENTIFIER.finditer(expression):
            qualifier = match.group("qualifier").lower()
            column = match.group("column").lower()
            table = sources.get(qualifier)
            if table is None:
                continue
            key = f"{table}.{column}"
            if key not in seen:
                seen.add(key)
                found.append(Column(dataset=table, name=column))

        without_qualified = _IDENTIFIER.sub(" ", expression)
        tables = sorted(set(sources.values()))
        for match in _BARE.finditer(without_qualified):
            column = match.group("column").lower()
            if column in _KEYWORDS or column in _AGGREGATES or column in _TYPES:
                continue
            owners = [table for table in tables if column in self._schema.get(table.lower(), [])]
            if len(owners) == 1:
                key = f"{owners[0]}.{column}"
                if key not in seen:
                    seen.add(key)
                    found.append(Column(dataset=owners[0], name=column))
            elif len(owners) > 1:
                ambiguous[column] = set(owners)
            elif len(tables) == 1:
                # One source and no schema: the reference can only be to it,
                # and refusing here would make the parser useless on exactly
                # the simple views that make up most of a legacy estate.
                key = f"{tables[0]}.{column}"
                if key not in seen:
                    seen.add(key)
                    found.append(Column(dataset=tables[0], name=column))
            elif len(tables) > 1:
                ambiguous[column] = set(tables)
        return found, ambiguous

    @staticmethod
    def _implied_name(expression: str) -> str | None:
        stripped = expression.strip()
        qualified = _IDENTIFIER.fullmatch(stripped)
        if qualified:
            return qualified.group("column")
        bare = _BARE.fullmatch(stripped)
        return bare.group("column") if bare else None


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("[]").strip("`")


def _split_alias(item: str) -> tuple[str, str | None]:
    """Separate `expression AS alias`, tolerating the implicit form."""
    stripped = item.strip()
    lowered = stripped.lower()
    if " as " in lowered:
        index = lowered.rindex(" as ")
        return stripped[:index], _clean(stripped[index + 4 :])
    parts = stripped.rsplit(None, 1)
    if (
        len(parts) == 2
        and re.fullmatch(r"[a-z_][\w]*", parts[1], re.IGNORECASE)
        and parts[1].lower() not in _KEYWORDS
        and not parts[0].rstrip().endswith(",")
    ):
        return parts[0], _clean(parts[1])
    return stripped, None
