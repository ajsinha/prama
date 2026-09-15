"""The reference interpreter: the IR's meaning, written out in full.

Three SQL backends agreeing proves less than it appears to. They all compile
through the same file, so a mistake in how a violation is expressed — the
handling of an unknown, say — would produce the same wrong answer on every
engine and the conformance suite would go green. Agreement between
implementations that share a compiler is agreement about the compiler, not
about the meaning.

So this evaluates a plan directly, in Python, over rows. It emits no SQL and
shares nothing with the compiler but the IR itself. When it agrees with
PostgreSQL, DuckDB and SQLite, four independent paths reached the same answer;
when it disagrees, one of them is wrong and the disagreement says which
construct.

Its other job is to be the engine of last resort. A feed file, a REST payload,
a mainframe extract — sources with no query engine at all — are read into rows
and judged here, so a control's reach is not limited to what happens to speak
SQL.

**Three-valued logic is written out rather than inherited.** Python's ``and``
and ``or`` are two-valued and its ``None`` is falsy; using them would quietly
turn every unknown into a false and lose exactly the distinction the language
is built around. Every operator below is Kleene's, spelled out.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from prama.backend.execute import ControlResult, judge, judge_segments
from prama.classify.validators import REGISTRY as VALIDATORS
from prama.ir.model import ControlPlan, Expr, Metric, MetricAggregate
from prama.pql.errors import PqlUnsupportedError
from prama.pql.functions import UNSET
from prama.pql.library import FUNCTIONS

#: The aggregates this interpreter computes exactly. `APPROX_COUNT_DISTINCT`
#: is deliberately absent: an approximation is an engine's own algorithm and
#: its own error bound, and the interpreter has no way to reproduce either.
_EXACT: dict[MetricAggregate, Callable[[list[float]], float]] = {
    MetricAggregate.SUM: sum,
    MetricAggregate.MIN: min,
    MetricAggregate.MAX: max,
    MetricAggregate.AVG: lambda numbers: sum(numbers) / len(numbers),
}

#: A row, as the interpreter sees it.
Row = Mapping[str, Any]

#: Unknown. Distinct from Python's None-as-a-value, because a column holding
#: NULL and an expression that could not be evaluated are the same thing in SQL
#: and must stay the same thing here.
UNKNOWN: Any = None


class MissingRelatedDataset(LookupError):
    """A referential control was run without the dataset it refers to.

    Raised rather than answered, because every possible answer would be a
    guess: assuming the value is present reports green on an estate nobody
    checked, and assuming it is absent reports every row as an orphan.
    """

    def __init__(self, dataset: str) -> None:
        super().__init__(
            f"this control refers to {dataset!r}, which was not supplied. "
            f"Pass it as a related dataset, or run the control on an engine "
            f"that can reach both."
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Bindings:
    """Values the run supplies, which the control refers to by name."""

    values: dict[str, Any] = dataclasses.field(default_factory=dict)

    def get(self, name: str) -> Any:
        return self.values.get(name)


class ReferenceEvaluator:
    """Evaluates a plan over rows. No SQL, no engine, no shared compiler."""

    def __init__(
        self,
        bindings: Bindings | None = None,
        *,
        related: dict[str, list[Row]] | None = None,
    ) -> None:
        self._bindings = bindings or Bindings()
        self._patterns: dict[str, re.Pattern[str]] = {}
        #: Other datasets a control reaches into, by name. A referential
        #: control is about two datasets, and an interpreter given only one of
        #: them can either say so or invent an answer.
        self._related = related or {}
        self._value_sets: dict[tuple[str, str], set[Any]] = {}

    # -- entry point -------------------------------------------------------

    def run(self, plan: ControlPlan, rows: Iterable[Row]) -> ControlResult:
        materialised = [dict(r) for r in rows]
        kept = [r for r in materialised if self._passes_filter(plan, r)]
        if plan.scope.segment_by:
            return judge_segments(plan, self._by_segment(plan, kept), engine="reference")
        return judge(plan, self._metrics(plan, kept), engine="reference")

    def _passes_filter(self, plan: ControlPlan, row: Row) -> bool:
        """A filter keeps a row only when it is definitely true.

        An unknown filter does not include the row. That is SQL's rule for
        WHERE and, unlike the assertion case, it is the right one: a row we
        cannot tell is in scope is not in scope, and counting it would put rows
        in the denominator that the engine never looked at.
        """
        if plan.scope.filter is None:
            return True
        return self.evaluate(plan.scope.filter, row) is True

    def _by_segment(
        self, plan: ControlPlan, rows: list[dict[str, Any]]
    ) -> list[tuple[str, dict[str, float]]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = "|".join(str(row.get(c)) for c in plan.scope.segment_by)
            groups.setdefault(key, []).append(row)
        return [(key, self._metrics(plan, members)) for key, members in sorted(groups.items())]

    # -- metrics -----------------------------------------------------------

    def _metrics(self, plan: ControlPlan, rows: list[dict[str, Any]]) -> dict[str, float]:
        computed: dict[str, float] = {}
        for metric in plan.metrics:
            if metric.aggregate is MetricAggregate.COUNT:
                computed[metric.name] = float(len(rows))
            elif metric.aggregate is MetricAggregate.COUNT_IF:
                computed[metric.name] = float(self._count_if(plan, metric, rows))
            elif metric.aggregate is MetricAggregate.COUNT_DISTINCT:
                computed[metric.name] = float(self._distinct(metric.expression, rows))
            else:
                value = self._aggregate(metric.aggregate, metric.expression, rows)
                if value is not None:
                    # Omitted rather than defaulted, which is what the SQL side
                    # already does with a NULL metric: `_judge` builds its dict
                    # with `if row.get(n) is not None`. The two paths now say
                    # the same thing about "no answer", which is the only way a
                    # comparison between them means anything.
                    computed[metric.name] = value
        return computed

    def _count_if(self, plan: ControlPlan, metric: Metric, rows: list[dict[str, Any]]) -> int:
        if metric.applies_unknown_policy:
            return sum(1 for row in rows if self.is_violation(plan, row))
        return sum(1 for row in rows if self.evaluate(metric.expression, row) is True)

    def is_violation(self, plan: ControlPlan, row: Row) -> bool:
        """Whether this row counts against the control.

        The predicate is stated positively, so a violation is its negation —
        and an unknown is a violation unless the control says otherwise. This
        one line is the language's central decision, and the reason the
        interpreter exists: if the compiler expresses it differently, the two
        disagree here rather than in production.
        """
        if plan.predicate is None:
            return False
        outcome = self.evaluate(plan.predicate, row)
        if outcome is UNKNOWN:
            return plan.unknown_is_violation
        if not outcome:
            return True
        # The screen said the row *might* be valid. For a two-stage control
        # that is not a pass, and treating it as one is how a column of
        # fabricated identifiers runs green for a year: every value has the
        # right shape, and the shape was never the standard. The interpreter
        # can do the arithmetic no engine here does faithfully, so it does.
        return self.fails_residual(plan, row)

    def fails_residual(self, plan: ControlPlan, row: Row) -> bool:
        """Whether a row the screen accepted fails the exact check.

        Public because the streaming path needs exactly this and had been
        reimplementing the surrounding logic without it — a control that caught
        a fabricated identifier overnight passed it in flight (finding T3). The
        alternative to sharing it is two copies of the rule, which is how they
        came to differ.
        """
        for name, column in plan.residual_validators:
            value = row.get(column)
            if value is None:
                continue
            if not VALIDATORS.get(name).judge(str(value)).valid:
                return True
        return False

    def _distinct(self, expression: Expr | None, rows: list[dict[str, Any]]) -> int:
        """Distinct values, excluding those with any unknown part.

        SQL's COUNT(DISTINCT) ignores nulls, and matching it is not deference —
        it is the only way the count means the same thing here as it does on
        the three engines. The rows excluded are counted separately as null
        keys, so nothing is lost; it is just counted as what it is.
        """
        if expression is None:
            return len(rows)
        parts = expression.args if expression.kind == "list" else (expression,)
        seen = set()
        for row in rows:
            key = tuple(self.evaluate(part, row) for part in parts)
            if any(value is UNKNOWN for value in key):
                continue
            seen.add(key)
        return len(seen)

    def _aggregate(
        self, aggregate: MetricAggregate, expression: Expr | None, rows: list[dict[str, Any]]
    ) -> float | None:
        """The aggregate, or `None` where SQL would answer NULL.

        Two `0.0` defaults used to live here, and both were answers to
        questions this function cannot answer.

        An aggregate with no entry in the table fell through `.get(aggregate,
        0.0)` — so `APPROX_COUNT_DISTINCT` returned **zero, presented as a real
        approximation**. This is the interpreter the conformance suite compares
        every SQL engine against; a confident wrong number here produces a
        disagreement that looks like a backend defect. QA round 4, `BE-096`.

        And `SUM`/`MIN`/`MAX`/`AVG` over no numeric values returned `0.0`, where
        SQL answers NULL. A sum of zero and a sum of nothing are different
        facts: the first says the values cancelled, the second says there were
        none, and a threshold of `>= 0` passes on one and should not be reached
        by the other. QA round 4, `BE-097`.
        """
        if aggregate not in _EXACT:
            raise PqlUnsupportedError(
                f"the reference interpreter does not compute {aggregate.value}",
                remedy=(
                    "An approximation is the engine's own algorithm and its own error "
                    "bound. Compare engines against each other for this metric, not "
                    "against the interpreter."
                ),
            )
        values = [self.evaluate(expression, row) for row in rows] if expression is not None else []
        numbers = [float(v) for v in values if isinstance(v, int | float)]
        if not numbers:
            return None
        return _EXACT[aggregate](numbers)

    # -- expressions, in three-valued logic --------------------------------

    def evaluate(self, node: Expr | None, row: Row) -> Any:
        if node is None:
            return True
        if node.kind == "col":
            return row.get(node.name)
        if node.kind == "lit":
            return node.value
        if node.kind == "param":
            return self._bindings.get(node.name)
        if node.kind == "list":
            return [self.evaluate(a, row) for a in node.args]
        if node.kind == "call":
            return self._call(node, row)
        return self._operation(node, row)

    def _call(self, node: Expr, row: Row) -> Any:
        name = node.name.upper()
        arguments = [self.evaluate(a, row) for a in node.args]
        declared = FUNCTIONS.find(name)
        if declared is None:
            # An unrecognised name. The compiler refuses these now, so reaching
            # here means an aggregate or a drift — either way, undetermined is
            # the only honest answer.
            return UNKNOWN
        if declared.strict_unknown and any(a is UNKNOWN for a in arguments):
            # A function of an unknown is unknown. Returning 0 for LENGTH(NULL)
            # would make a length check silently pass on every null.
            #
            # The exceptions declare themselves: ISBLANK's entire job is to
            # answer a question *about* an unknown, and IF must choose between
            # two values rather than propagate.
            return UNKNOWN
        result = declared.evaluate(list(arguments))
        return UNKNOWN if result is UNSET else result

    def _operation(self, node: Expr, row: Row) -> Any:
        operator = node.name
        if operator == "AND":
            return _and(*(self.evaluate(a, row) for a in node.args))
        if operator == "OR":
            return _or(*(self.evaluate(a, row) for a in node.args))
        if operator == "NOT":
            return _not(self.evaluate(node.args[0], row))
        if operator == "IS NULL":
            return self.evaluate(node.args[0], row) is UNKNOWN
        if operator == "IS NOT NULL":
            return self.evaluate(node.args[0], row) is not UNKNOWN
        values = [self.evaluate(a, row) for a in node.args]
        if operator in ("IN", "NOT IN"):
            return _membership(values[0], values[1], negated=operator.startswith("NOT"))
        if operator in ("BETWEEN", "NOT BETWEEN"):
            inside = _and(
                _compare(">=", values[0], values[1]), _compare("<=", values[0], values[2])
            )
            return _not(inside) if operator.startswith("NOT") else inside
        if operator == "EXISTS":
            return self._exists(values[0], str(node.args[1].value), str(node.args[2].value))
        if operator in ("MATCHES", "NOT MATCHES"):
            matched = self._matches(values[0], node.args[1].value)
            return _not(matched) if operator.startswith("NOT") else matched
        if operator in ("LIKE", "NOT LIKE", "ILIKE", "NOT ILIKE"):
            liked = _like(values[0], values[1], fold_case=operator.endswith("ILIKE"))
            return _not(liked) if operator.startswith("NOT") else liked
        if operator == "HAS FORMAT":
            return _has_format(values[0], node.args[1].value)
        if operator in ("-", "+") and len(values) == 1:
            return _sign(operator, values[0])
        if operator in ("+", "-", "*", "/", "%"):
            return _arithmetic(operator, values)
        return _compare(operator, values[0], values[1] if len(values) > 1 else UNKNOWN)

    def _exists(self, value: Any, dataset: str, column: str) -> Any:
        """Whether a value appears in another dataset's column.

        A null never matches, which makes an orphaned null a violation under
        the default policy — the same answer SQL's EXISTS gives, and the same
        one the compiler produces.
        """
        if value is UNKNOWN:
            return False
        if dataset not in self._related:
            raise MissingRelatedDataset(dataset)
        key = (dataset, column)
        if key not in self._value_sets:
            self._value_sets[key] = {
                row.get(column) for row in self._related[dataset] if row.get(column) is not UNKNOWN
            }
        return value in self._value_sets[key]

    def _matches(self, value: Any, pattern: Any) -> Any:
        if value is UNKNOWN or pattern is UNKNOWN:
            return UNKNOWN
        compiled = self._patterns.get(str(pattern))
        if compiled is None:
            compiled = re.compile(str(pattern))
            self._patterns[str(pattern)] = compiled
        return compiled.search(str(value)) is not None


# -- Kleene's three-valued operators ---------------------------------------


def _and(*operands: Any) -> Any:
    """False dominates; unknown survives; only all-true is true."""
    if any(o is False for o in operands):
        return False
    if any(o is UNKNOWN for o in operands):
        return UNKNOWN
    return True


def _or(*operands: Any) -> Any:
    """True dominates; unknown survives; only all-false is false."""
    if any(o is True for o in operands):
        return True
    if any(o is UNKNOWN for o in operands):
        return UNKNOWN
    return False


def _not(operand: Any) -> Any:
    return UNKNOWN if operand is UNKNOWN else not operand


def _compare(operator: str, left: Any, right: Any) -> Any:
    """A comparison with an unknown operand is unknown, never false.

    This is the whole reason a null-heavy column silently passes a naive rule:
    ``notional > 0`` is not false for a null, it is unknown, and treating the
    two the same is how the mistake gets made.
    """
    if left is UNKNOWN or right is UNKNOWN:
        return UNKNOWN
    try:
        return {
            "=": left == right,
            "<>": left != right,
            ">": left > right,
            ">=": left >= right,
            "<": left < right,
            "<=": left <= right,
        }[operator]
    except TypeError:
        # Comparing a number with text. The type checker refuses this at
        # authoring time; reaching here means it was not checked, and unknown
        # is the honest answer rather than an arbitrary ordering.
        return UNKNOWN


def _membership(value: Any, candidates: Any, *, negated: bool) -> Any:
    """SQL's IN, including the part everybody forgets.

    ``x NOT IN (1, 2, NULL)`` is never true: the null makes it unknown for any
    x that is not 1 or 2, because x might equal the null. Getting this wrong is
    the classic SQL bug, and an engine that got it right while the interpreter
    got it wrong would show up as a conformance failure — which is the point.
    """
    if value is UNKNOWN:
        return UNKNOWN
    items = candidates if isinstance(candidates, list) else [candidates]
    if any(item == value for item in items if item is not UNKNOWN):
        return not negated
    if any(item is UNKNOWN for item in items):
        return UNKNOWN
    return negated


def _like(value: Any, pattern: Any, *, fold_case: bool) -> Any:
    """SQL ``LIKE``, with the same unknown rule as everything else here.

    `LIKE` and `ILIKE` reached this interpreter's final `_compare` fallback,
    which meant a control that compiled fine on three engines was answered by
    the reference with a comparison nobody asked for (QA finding BE-054). The
    reference is the conformance oracle, so it disagreeing is worse than it
    refusing.
    """
    if value is UNKNOWN or value is None or pattern is UNKNOWN or pattern is None:
        return UNKNOWN
    text, shape = str(value), str(pattern)
    if fold_case:
        text, shape = text.upper(), shape.upper()
    return _sql_like(text, shape)


def _sql_like(text: str, pattern: str) -> bool:
    """``%`` is any run, ``_`` is one character, everything else is itself."""
    expression = "".join(
        ".*" if character == "%" else "." if character == "_" else re.escape(character)
        for character in pattern
    )
    return re.fullmatch(expression, text, re.DOTALL) is not None


def _has_format(value: Any, pattern: Any) -> Any:
    """``HAS FORMAT '999-AAA'`` — 9 a digit, A a letter, X either, * a run.

    The reference raised a bare, uncaught `KeyError: 'HAS FORMAT'` here, while
    the SQL side refused with a well-formed error — the same control failing
    two different ways depending on where it ran (QA finding PQL-093).

    This is stricter than the SQL translation, which has no digit class and
    settles for `_`. That is a deliberate asymmetry and it is the right way
    round: the reference is what a residual check re-runs, so it may be exact
    where the pushdown can only screen.
    """
    if value is UNKNOWN or value is None or pattern is UNKNOWN or pattern is None:
        return UNKNOWN
    classes = {"9": r"\d", "A": r"[A-Za-z]", "X": r"[A-Za-z0-9]", "*": r".*"}
    expression = "".join(classes.get(character, re.escape(character)) for character in str(pattern))
    return re.fullmatch(expression, str(value), re.DOTALL) is not None


def _sign(operator: str, value: Any) -> Any:
    """A unary minus or plus. Unknown stays unknown."""
    if value is UNKNOWN or not isinstance(value, int | float):
        return UNKNOWN
    return value if operator == "+" else -value


def _arithmetic(operator: str, values: list[Any]) -> Any:
    if any(v is UNKNOWN for v in values):
        return UNKNOWN
    left, right = float(values[0]), float(values[1])
    if operator in ("/", "%") and right == 0:
        # Division by zero is unknown, not an error and not zero. An error
        # would abort a control over one bad row; zero would silently change
        # the answer.
        return UNKNOWN
    return {
        "+": left + right,
        "-": left - right,
        "*": left * right,
        "/": left / right if right else UNKNOWN,
        # `math.fmod`, not `%`. Python floors and every SQL engine truncates:
        # -10 % 3 is 2 here and -1 there, so this interpreter reported a
        # violation none of the three engines did (finding C4). The engines
        # already agreed with each other, and the emitted SQL is what a DBA
        # reads, so the SQL meaning is the one Prama defines and this is the
        # side that changed.
        "%": math.fmod(left, right) if right else UNKNOWN,
    }[operator]
