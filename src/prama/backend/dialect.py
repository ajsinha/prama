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
import math
import re
from decimal import Decimal
from typing import Any

from prama.core.errors import ValidationError

#: Capability names, matching those the connectors publish, so a control's
#: requirements and a source's abilities are stated in one vocabulary.
REGEX = "pushdown.regex"
FILTER = "pushdown.filter"
AGGREGATION = "pushdown.aggregation"
APPROX_DISTINCT = "pushdown.approx_distinct"
SAMPLING = "pushdown.sampling"
CROSS_OBJECT_JOIN = "pushdown.cross_object_join"


#: Constructs RE2 does not implement and Python's `re` does. Verified against
#: DuckDB rather than taken from documentation: each raises
#: `InvalidInputException` there and compiles fine in Python, so a control
#: written and tested against the interpreter fails on DuckDB at execution —
#: after the scan, in a run somebody is waiting on.
#:
#: Deliberately conservative and deliberately incomplete. A `\1` inside a
#: character class is an octal escape rather than a backreference and is refused
#: here anyway: a false refusal costs a rewrite, a false acceptance costs a run
#: that fails on one engine only. And it does not attempt the *silent*
#: divergences, which no scan of the pattern can find — `\d` is Unicode-aware in
#: Python and ASCII-only in RE2, so `/^\d+$/` matches Arabic-Indic digits on
#: SQLite and on the interpreter and not on DuckDB, with no error on either
#: side. That one is recorded as a known divergence, not fixed.
#: QA round 4, `BE-015`.
RE2_ABSENT: tuple[tuple[str, str], ...] = (
    (r"\(\?=", "lookahead"),
    (r"\(\?!", "negative lookahead"),
    (r"\(\?<=", "lookbehind"),
    (r"\(\?<!", "negative lookbehind"),
    (r"(?<!\\)\\[1-9]", "a backreference"),
)


def re2_gap(pattern: str) -> str:
    """The first RE2-absent construct in *pattern*, or "" if there is none."""
    for expression, name in RE2_ABSENT:
        if re.search(expression, pattern):
            return name
    return ""


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
    capabilities: frozenset[str] = frozenset({FILTER, AGGREGATION, CROSS_OBJECT_JOIN})
    #: How this engine spells regular expressions, for the record. ``none``
    #: means it has none, which is a fact about the engine and not a problem to
    #: be worked around.
    regex_flavour: str = "none"
    #: What this engine calls a double-precision float. Asked rather than
    #: branched on: a fixture writing ``"REAL" if dialect == "sqlite"`` would be
    #: the one place in the codebase deciding behaviour from an engine name,
    #: which is exactly what the dialect object exists to prevent.
    double_type: str = "DOUBLE PRECISION"
    #: Whether the engine supports ``FILTER (WHERE …)`` on an aggregate. The
    #: alternative — SUM(CASE WHEN …) — is portable and slightly slower, and is
    #: what engines without it get.
    has_aggregate_filter: bool = False
    #: Whether the engine has ``ILIKE``. SQLite does not, and does not need it:
    #: its ``LIKE`` is already case-insensitive for ASCII. Declared here rather
    #: than branched on a name at the call site, which is what this object
    #: exists to prevent.
    has_ilike: bool = False

    # -- identifiers and literals -----------------------------------------

    def quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def qualify(self, name: str) -> str:
        """A dataset name, which may already be qualified by schema."""
        return ".".join(self.quote(part) for part in name.split("."))

    def as_text(self, expression: str) -> str:
        """The expression as text, for an operation that only means text.

        A regular expression is by definition a test on characters. Asking for
        one on a DATE or a NUMERIC means "its textual form", and a strict
        engine refuses to bind the function rather than guessing — DuckDB says
        ``regexp_matches(DATE, ...)`` has no candidate, which surfaces as a
        control that cannot run rather than as a wrong answer.

        Casting here rather than at each call site keeps the decision in one
        place and makes it visible in the emitted SQL, which is the artefact a
        DBA reads before granting access. All three shipped engines render a
        date as ISO-8601, which is what any pattern for a date expects.
        """
        return f"CAST({expression} AS VARCHAR)"

    def as_real(self, expression: str) -> str:
        """The expression as a floating-point number.

        Emitted around the left operand of ``/`` so that division means the
        same thing everywhere. Without it the engines disagree *with each
        other*: SQLite and PostgreSQL do integer division on two integers, so
        ``row_id / 2`` is 0 for row 1, while DuckDB and the reference
        interpreter give 0.5. A control reading ``(row_id / 2) > 0`` therefore
        passed on two engines and failed on the third — finding C4.

        True division is the meaning Prama defines, because silent truncation
        is a defect a data-quality tool exists to find rather than commit, and
        because a business reader writing ``amount / count`` means the
        quotient.
        """
        return f"CAST({expression} AS DOUBLE PRECISION)"

    def modulo(self, left: str, right: str) -> str:
        """Remainder, with the sign of the *dividend*.

        Every SQL engine here truncates; Python floors. ``-10 % 3`` is -1 in
        SQL and 2 in Python, so the reference interpreter reported a violation
        the engines did not. Prama defines the SQL meaning — all three engines
        already agree on it, and it is what a reader gets if they run the
        emitted SQL themselves. The reference interpreter is the side that
        changed.
        """
        return f"({left} % {right})"

    def literal(self, value: Any) -> str:
        """A Python value as SQL, or a refusal when it has no SQL spelling.

        `Decimal` used to fall past `isinstance(value, int | float)` into the
        string branch and be emitted as `'1.5'` — **quoted**. That is not a
        cosmetic type change: it makes the comparison lexical. `9.0 > 10.0` is
        true as text on both DuckDB and SQLite, so a control reading
        `amount > 10.00` passes rows of nine pounds and says so with a verdict.
        `Decimal` is exactly how money is represented everywhere else in this
        codebase. QA round 4, `BE-006`.

        A non-finite float has no literal spelling the three engines share, and
        `repr(float("inf"))` is the Python string `inf`, which parses on none of
        them. `BE-007`.
        """
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return self.boolean(value)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValidationError(
                f"{value!r} has no SQL spelling",
                remedy=(
                    "A threshold must be a finite number. An infinity or a NaN here "
                    "is usually a division that produced one earlier."
                ),
                context={"value": repr(value)},
            )
        if isinstance(value, int | float):
            return repr(value)
        if isinstance(value, Decimal):
            # `str`, not `repr`: `repr(Decimal("1.5"))` is `Decimal('1.5')`.
            # Emitted unquoted so the engine reads it as the number it is.
            if not value.is_finite():
                raise ValidationError(
                    f"{value!s} has no SQL spelling",
                    remedy="A threshold must be a finite number.",
                    context={"value": str(value)},
                )
            return str(value)
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

    def exists_in(self, value: str, table: str, column: str) -> str:
        """Whether a value appears in another dataset's column.

        A correlated EXISTS rather than ``IN (SELECT …)``: the two differ when
        the target column contains a null, where ``NOT IN`` becomes unknown for
        every row and the control silently stops finding orphans. That is the
        classic SQL trap, and it is worth spending a subquery to avoid.
        """
        return f"EXISTS (SELECT 1 FROM {table} WHERE {column} = {value})"

    def limit(self, query: str, count: int) -> str:
        return f"{query} LIMIT {count}"

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def missing(self, required: frozenset[str]) -> frozenset[str]:
        return frozenset(required) - self.capabilities


class PostgresDialect(SqlDialect):
    name = "postgresql"
    capabilities = frozenset(
        {FILTER, AGGREGATION, REGEX, APPROX_DISTINCT, SAMPLING, CROSS_OBJECT_JOIN}
    )
    regex_flavour = "posix"
    has_aggregate_filter = True
    has_ilike = True

    def regex_match(self, expression: str, pattern: str) -> str:
        return f"{expression} ~ {self.literal(pattern)}"

    def modulo(self, left: str, right: str) -> str:
        """Remainder, over NUMERIC.

        PostgreSQL's `%` is defined for integer and numeric and *not* for
        double precision: `notional % 3` on a DOUBLE column raises "operator
        does not exist: double precision % integer". DuckDB and SQLite both
        accept it, so the corpus case passed on two engines and could not run
        on the third.

        Found by pointing the conformance suite at a real PostgreSQL for the
        first time — the suite exists to prove the three engines agree and had
        never met one of them (QA findings BE-024 and Q-60).

        NUMERIC rather than integer, so a fractional dividend keeps its
        fraction. Truncating to integer here would silently change what the
        control asks.
        """
        return f"(CAST({left} AS NUMERIC) % CAST({right} AS NUMERIC))"


class DuckDbDialect(SqlDialect):
    name = "duckdb"
    capabilities = frozenset(
        {FILTER, AGGREGATION, REGEX, APPROX_DISTINCT, SAMPLING, CROSS_OBJECT_JOIN}
    )
    regex_flavour = "re2"
    has_aggregate_filter = True
    has_ilike = True

    def regex_match(self, expression: str, pattern: str) -> str | Unsupported:
        if gap := re2_gap(pattern):
            return Unsupported(
                capability=REGEX,
                detail=(
                    f"DuckDB matches with RE2, which has no {gap}, so /{pattern}/ "
                    "cannot be run here"
                ),
                remedy=(
                    f"Rewrite the pattern without {gap} — RE2 has none — or run this "
                    "control on PostgreSQL or SQLite. Left as it is, the control "
                    "passes on the interpreter and fails on DuckDB at execution."
                ),
            )
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
    capabilities = frozenset({FILTER, AGGREGATION, CROSS_OBJECT_JOIN, REGEX})

    def as_real(self, expression: str) -> str:
        """SQLite has no ``DOUBLE PRECISION``; the affinity is spelled ``REAL``."""
        return f"CAST({expression} AS REAL)"

    #: Python's ``re``, not POSIX and not RE2. SQLite ships no regular
    #: expression engine at all: it reserves the ``REGEXP`` operator and calls
    #: a function of that name if the host has registered one, which is exactly
    #: what ``prama.connect.sources.query`` does for every SQLite connection it
    #: opens. The capability is therefore real for Prama's own executor and
    #: absent for a bare connection — where it fails loudly as "no such
    #: function: REGEXP" rather than quietly matching nothing.
    regex_flavour = "python"
    double_type = "REAL"
    has_aggregate_filter = False

    def regex_match(self, expression: str, pattern: str) -> str:
        return f"{expression} REGEXP {self.literal(pattern)}"

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
