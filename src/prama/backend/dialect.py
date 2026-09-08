"""What differs between engines when a control is compiled to SQL.

Small, and every entry earns its place by being something the engines genuinely
disagree about. Anything they agree on is written once in the compiler.

The rule that shapes this file: **a dialect never approximates**. Where an
engine cannot express a construct, it says so and the control is refused at
authoring time. SQLite has no regular expressions; a dialect that quietly
substituted ``LIKE`` would make the same control mean two different things on
two engines and there would be no way to notice. That is the failure this whole
layer exists to prevent, so it is the one thing a dialect is not permitted to do.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: Capability names, matching those the connectors publish, so a control's
#: requirements and a source's abilities are stated in one vocabulary.
REGEX = "pushdown.regex"
FILTER = "pushdown.filter"
AGGREGATION = "pushdown.aggregation"
APPROX_DISTINCT = "pushdown.approx_distinct"
SAMPLING = "pushdown.sampling"


@dataclasses.dataclass(frozen=True, slots=True)
class Unsupported:
    """Why an engine cannot run a control, in terms somebody can act on."""

    capability: str
    detail: str
    remedy: str


class SqlDialect:
    """One engine's SQL, for the handful of things engines disagree about.

    Concrete rather than abstract: the base is the *portable* dialect, and a
    subclass overrides only where its engine can do better. An abstract base
    would force each dialect to restate the parts every engine agrees on, which
    is how three dialects end up with three subtly different definitions of
    count_if.
    """

    name: str = "sql"
    #: What this engine can do. A control needing more is refused, never
    #: approximated.
    capabilities: frozenset[str] = frozenset({FILTER, AGGREGATION})
    #: How this engine spells regular expressions, for the record. ``none``
    #: means it has none, which is a fact about the engine and not a problem to
    #: be worked around.
    regex_flavour: str = "none"
    #: Whether the engine supports ``FILTER (WHERE …)`` on an aggregate. The
    #: alternative — SUM(CASE WHEN …) — is portable and slightly slower, and is
    #: what engines without it get.
    has_aggregate_filter: bool = False

    # -- identifiers and literals -----------------------------------------

    def quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def qualify(self, name: str) -> str:
        """A dataset name, which may already be qualified by schema."""
        return ".".join(self.quote(part) for part in name.split("."))

    def literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return self.boolean(value)
        if isinstance(value, int | float):
            return repr(value)
        return "'" + str(value).replace("'", "''") + "'"

    def boolean(self, value: bool) -> str:
        return "TRUE" if value else "FALSE"

    # -- the things engines disagree about ---------------------------------

    def regex_match(self, expression: str, pattern: str) -> str | Unsupported:
        return Unsupported(
            capability=REGEX,
            detail=(
                f"{self.name} has no regular expression operator, so {expression} "
                f"cannot be matched against /{pattern}/ here"
            ),
            remedy=(
                "Use HAS FORMAT with a named format, or run this control on an engine "
                "with regular expressions. Substituting LIKE would make the same "
                "control mean two different things on two engines."
            ),
        )

    def count_if(self, condition: str) -> str:
        """Count rows satisfying a condition.

        ``FILTER (WHERE …)`` where the engine has it, and the portable
        ``SUM(CASE WHEN … THEN 1 ELSE 0 END)`` where it does not — with
        ``COALESCE`` so an empty scope counts zero rather than null, which
        would otherwise turn an empty table into an indeterminate verdict for
        the wrong reason.
        """
        if self.has_aggregate_filter:
            return f"COUNT(*) FILTER (WHERE {condition})"
        return f"COALESCE(SUM(CASE WHEN {condition} THEN 1 ELSE 0 END), 0)"

    def count_distinct(self, expressions: list[str], *, where: str = "") -> str:
        """Distinct values, optionally over a subset of rows.

        The subset matters more than it looks. SQL is inconsistent about nulls
        here: ``COUNT(DISTINCT x)`` ignores a null, but ``COUNT(DISTINCT (x,
        y))`` counts a row whose x is null as a distinct pair. Deriving a
        duplicate count from either without saying which rows were included
        gives a number that means one thing for a single-column key and
        another for a composite one.
        """
        inner = expressions[0] if len(expressions) == 1 else f"({', '.join(expressions)})"
        return self._distinct_over(inner, where)

    def _distinct_over(self, inner: str, where: str) -> str:
        if not where:
            return f"COUNT(DISTINCT {inner})"
        if self.has_aggregate_filter:
            return f"COUNT(DISTINCT {inner}) FILTER (WHERE {where})"
        # No FILTER: a CASE yielding NULL for excluded rows, which
        # COUNT(DISTINCT) then ignores — the same subset by a longer road.
        return f"COUNT(DISTINCT CASE WHEN {where} THEN {inner} END)"

    def length(self, expression: str) -> str:
        return f"LENGTH({expression})"

    def is_not_distinct_from(self, left: str, right: str) -> str:
        """Null-safe equality, for matching keys where a null is a real value."""
        return f"{left} IS NOT DISTINCT FROM {right}"

    def limit(self, query: str, count: int) -> str:
        return f"{query} LIMIT {count}"

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def missing(self, required: frozenset[str]) -> frozenset[str]:
        return frozenset(required) - self.capabilities


class PostgresDialect(SqlDialect):
    name = "postgresql"
    capabilities = frozenset({FILTER, AGGREGATION, REGEX, APPROX_DISTINCT, SAMPLING})
    regex_flavour = "posix"
    has_aggregate_filter = True

    def regex_match(self, expression: str, pattern: str) -> str:
        return f"{expression} ~ {self.literal(pattern)}"


class DuckDbDialect(SqlDialect):
    name = "duckdb"
    capabilities = frozenset({FILTER, AGGREGATION, REGEX, APPROX_DISTINCT, SAMPLING})
    regex_flavour = "re2"
    has_aggregate_filter = True

    def regex_match(self, expression: str, pattern: str) -> str:
        return f"regexp_matches({expression}, {self.literal(pattern)})"

    def count_distinct(self, expressions: list[str], *, where: str = "") -> str:
        # DuckDB counts a multi-column DISTINCT over a struct rather than a
        # parenthesised row.
        if len(expressions) == 1:
            return self._distinct_over(expressions[0], where)
        fields = ", ".join(f"'c{i}': {e}" for i, e in enumerate(expressions))
        return self._distinct_over(f"{{{fields}}}", where)


class SqliteDialect(SqlDialect):
    """SQLite: everywhere, and missing several things.

    Kept as a first-class dialect precisely because its gaps are real. A
    platform that only ever compiled for capable engines would never exercise
    the refusal path, and the refusal path is the promise.
    """

    name = "sqlite"
    capabilities = frozenset({FILTER, AGGREGATION})
    regex_flavour = "none"
    has_aggregate_filter = False

    def boolean(self, value: bool) -> str:
        # No BOOLEAN type; 1 and 0 are what comparisons yield.
        return "1" if value else "0"

    def is_not_distinct_from(self, left: str, right: str) -> str:
        return f"{left} IS {right}"

    def count_distinct(self, expressions: list[str], *, where: str = "") -> str:
        if len(expressions) == 1:
            return self._distinct_over(expressions[0], where)
        # No row constructor. Concatenation with a separator that cannot occur
        # in the data would be a guess; a null-safe join with a sentinel is
        # explicit about what it assumes.
        joined = " || CHAR(31) || ".join(
            f"COALESCE(CAST({e} AS TEXT), CHAR(30))" for e in expressions
        )
        return self._distinct_over(f"({joined})", where)


DIALECTS: dict[str, SqlDialect] = {
    d.name: d for d in (PostgresDialect(), DuckDbDialect(), SqliteDialect())
}


def dialect(name: str) -> SqlDialect:
    from prama.core.errors import RegistryError

    if name not in DIALECTS:
        raise RegistryError(
            f"no SQL dialect named {name!r}",
            remedy=f"Available: {', '.join(sorted(DIALECTS))}.",
            context={"requested": name},
        )
    return DIALECTS[name]
