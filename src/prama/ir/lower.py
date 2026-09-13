"""Lowering a parsed control into the IR.

This is where a control stops being text and becomes a plan. Everything after
this point — every backend, the executor, the evidence record — sees only the
IR, which is what makes "the same control on two engines" a checkable claim
rather than a hope.

The interesting work is turning each assertion into the same shape: a row-level
predicate plus metrics plus a threshold. Most of the catalogue reduces to that
directly. The ones that do not — a unique key, a functional dependency, a
reference — carry an ``assertion_kind`` and their columns instead, because they
are inherently about *sets* of rows and pretending otherwise would force every
backend to reconstruct the same grouping from a predicate that could not express
it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
from typing import Any

from prama.classify.plugins import PLUGINS
from prama.classify.validators import REGISTRY as VALIDATORS
from prama.classify.validators import ValidatorRegistry
from prama.core.errors import ValidationError
from prama.ir.model import (
    Comparator,
    ControlPlan,
    EvidencePolicy,
    Expr,
    Metric,
    MetricAggregate,
    Provenance,
    Scope,
    Threshold,
)
from prama.pql import ast

#: The metric every control computes, so a rate is expressible without a second
#: pass and so "how much was looked at" is always on the record.
SCANNED = "scanned_rows"
#: The metric a threshold is compared against by default.
VIOLATING = "violating_rows"


class Lowerer:
    """Turns checked PQL into an executable plan."""

    def __init__(
        self,
        *,
        binding: str = "",
        as_of: str = "",
        codelists: dict[str, tuple[str, ...]] | None = None,
        validators: ValidatorRegistry | None = None,
    ) -> None:
        self._binding = binding
        self._as_of = as_of
        self._validators = VALIDATORS if validators is None else validators
        #: Semantic types whose exact test does not fit in a predicate,
        #: collected while lowering one control. Reset per call — the lowerer
        #: is not reentrant and does not need to be, since ``control`` is the
        #: only entry point.
        self._residuals: list[dict[str, str]] = []
        #: Codelists resolved into the plan, so the compiled control is closed
        #: over its permitted values. Resolving at run time instead would mean
        #: a codelist edited on Tuesday silently changes what Monday's evidence
        #: was asserting — and the plan hash would not move to say so.
        #:
        #: Empty by default, and deliberately: resolving the shipped lists is
        #: `prama.ir.resolve.resolved`'s job, and that module exists because
        #: "each caller remembering is how three of six call sites end up
        #: subtly different". `prama control compile` was one of the callers
        #: that did not use it, so it answered "the codelist 'iso4217' is not
        #: registered" about a list the product ships (QA finding Q-14) — the
        #: fix belongs at that call site, not in a default here that would make
        #: bare lowering quietly reach for a registry.
        self._codelists = codelists or {}

    def control(self, control: ast.Control, *, source: str = "") -> ControlPlan:
        self._residuals = []
        predicate, kind, detail = self._assertion(control.assertion)
        filter_expression = self._expression(control.where) if control.where is not None else None
        if self._residuals:
            # Part of ``detail``, which is part of the plan's meaning, so a
            # two-stage control hashes differently from a screen-only one. Two
            # plans that check different things must never share an id.
            unique = {(r["validator"], r["column"]): r for r in self._residuals}
            detail = {
                **detail,
                "residual_validators": [unique[k] for k in sorted(unique)],
            }
        scope = Scope(
            dataset=control.target,
            binding=self._binding,
            filter=filter_expression,
            segment_by=tuple(c.name for c in control.segmentation.columns)
            if control.segmentation
            else (),
            as_of=self._as_of,
        )
        metrics = self._metrics(predicate, kind, detail)
        return ControlPlan(
            scope=scope,
            predicate=predicate,
            metrics=metrics,
            threshold=self._threshold(control.threshold),
            evidence=EvidencePolicy(
                level=control.evidence.level.value,
                max_samples=control.evidence.max_samples,
            ),
            unknown_is_violation=control.unknown_policy is ast.UnknownPolicy.VIOLATION,
            severity=control.severity.value,
            dimensions=tuple(d.value for d in control.dimensions),
            because=control.because,
            description=control.describe(),
            assertion_kind=kind,
            detail=detail,
            provenance=Provenance(
                pql_hash=_hash(source or control.render()),
                declared_by=control.owner,
            ),
        )

    def program(self, program: ast.Program, *, source: str = "") -> list[ControlPlan]:
        return [self.control(c, source=source) for c in program.all_controls]

    # -- assertions --------------------------------------------------------

    def _assertion(self, assertion: ast.Assertion) -> tuple[Expr | None, str, dict[str, Any]]:
        if isinstance(assertion, ast.PredicateAssertion):
            return self._predicate(assertion), "predicate", {}
        if isinstance(assertion, ast.ExpressionAssertion):
            return self._expression(assertion.condition), "predicate", {}
        if isinstance(assertion, ast.UniqueKeyAssertion):
            return None, "unique_key", {"key_columns": [c.name for c in assertion.columns]}
        if isinstance(assertion, ast.FunctionalDependencyAssertion):
            return (
                None,
                "functional_dependency",
                {
                    "determinant": [c.name for c in assertion.determinant],
                    "dependent": [c.name for c in assertion.dependent],
                },
            )
        if isinstance(assertion, ast.RowCountAssertion):
            return (
                None,
                "row_count",
                {"minimum": assertion.minimum, "maximum": assertion.maximum},
            )
        if isinstance(assertion, ast.ReferenceAssertion):
            # EXISTS against the target, not a null check. Lowering a
            # referential control to IS NOT NULL would leave it passing on
            # every orphan — a control that looks present, reports green, and
            # checks something else entirely.
            return (
                Expr.operation(
                    "EXISTS",
                    Expr.column(assertion.column.name),
                    Expr.literal(assertion.target_dataset),
                    Expr.literal(assertion.target_column),
                ),
                "reference",
                {
                    "column": assertion.column.name,
                    "target_dataset": assertion.target_dataset,
                    "target_column": assertion.target_column,
                },
            )
        if isinstance(assertion, ast.FreshnessAssertion):
            return (
                None,
                "freshness",
                {
                    "tolerance_minutes": assertion.tolerance_minutes,
                    "due_time": assertion.due_time,
                    "calendar": assertion.calendar,
                    "column": assertion.column.name if assertion.column else "",
                },
            )
        raise ValidationError(
            f"{type(assertion).__name__} cannot yet be lowered to a plan",
            remedy=(
                "This assertion parses but has no execution strategy yet. Use one that "
                "does, or raise it as a gap — the language deliberately refuses to "
                "pretend it can run something it cannot."
            ),
            context={"assertion": type(assertion).__name__},
        )

    def _predicate(self, assertion: ast.PredicateAssertion) -> Expr:
        """A row predicate: true means the row is fine.

        Stated positively throughout, so ``violating_rows`` is uniformly
        ``count_if(NOT predicate)`` and no backend has to remember which
        assertions were written the other way round.
        """
        subject = self._expression(assertion.subject)
        argument = self._expression(assertion.argument) if assertion.argument else None
        upper = self._expression(assertion.upper) if assertion.upper else None
        operator = assertion.operator
        if operator in ast.COMPARISONS:
            assert argument is not None
            return Expr.operation(operator, subject, argument)
        built = {
            "is_null": lambda: Expr.operation("IS NULL", subject),
            "is_not_null": lambda: Expr.operation("IS NOT NULL", subject),
            "is_unique": lambda: Expr.operation("IS NOT NULL", subject),
            "in": lambda: Expr.operation("IN", subject, argument or Expr.values()),
            "in_codelist": lambda: self._codelist(subject, argument),
            "between": lambda: Expr.operation(
                "BETWEEN", subject, argument or Expr.literal(0), upper or Expr.literal(0)
            ),
            "matches": lambda: Expr.operation(
                "MATCHES", subject, argument or Expr.literal("", "pattern")
            ),
            "is_valid": lambda: self._valid(subject, argument),
            "has_length_between": lambda: Expr.operation(
                "BETWEEN",
                Expr.call("LENGTH", subject, type_name="number"),
                argument or Expr.literal(0),
                upper or Expr.literal(0),
            ),
            "has_format": lambda: Expr.operation(
                "HAS FORMAT", subject, argument or Expr.literal("")
            ),
            "is_of_type": lambda: Expr.operation(
                "IS OF TYPE", subject, argument or Expr.literal("")
            ),
        }[operator]()
        # A unique-key predicate cannot be a row predicate; the caller handles
        # it, and the positive form here only guards against nulls.
        if operator == "is_unique":
            return built
        return Expr.operation("NOT", built) if assertion.negated else built

    def _valid(self, subject: Expr, argument: Expr | None) -> Expr:
        """A semantic type, resolved into what an engine can actually test.

        Same discipline as :meth:`_codelist`: the reference is resolved here so
        the plan means one fixed thing, rather than at execution where the
        answer could change under a plan that claims to be the same control.

        The difference is that a semantic type does not always *fit* in a
        predicate. A UUID does — its regular expression is the whole standard.
        An ISIN does not: the check digit is Luhn over a letter-expanded string,
        which no engine here computes faithfully. For those, what goes into the
        plan is the **screen** — a necessary condition every valid value
        satisfies — and the exact test is recorded as a *residual* the executor
        must apply before it may report a pass.

        Lowering the screen and calling it the whole control is the tempting
        alternative and the one this design exists to refuse: ``GB0000000000``
        satisfies every ISIN regular expression ever written, so the control
        would run green over a column of fabricated identifiers.
        """
        name = str(argument.value) if argument is not None else ""
        validator = self._validators.find(name)
        if validator is None:
            raise ValidationError(
                f"there is no semantic type called {name!r}",
                remedy=(
                    "Register a validator for it, or use a known type. An unresolved "
                    "type would compile to a check that passes everything, which is "
                    "worse than no control because it looks like coverage."
                ),
                context={"semantic_type": name},
            )
        screen = Expr.operation(
            "MATCHES", subject, Expr.literal(validator.screen_pattern, "pattern")
        )
        if not validator.screen_is_complete:
            if subject.kind != "col":
                # A residual nobody can locate is a residual nobody will apply,
                # and the failure mode of dropping it silently is a green
                # control over invalid data. Refusing is the only safe answer.
                raise ValidationError(
                    f"IS VALID {name!r} can only be applied to a column",
                    remedy=(
                        f"A {validator.label} is checked in two stages — a shape the "
                        "engine can test, then an exact check on the rows that pass — "
                        "and the second stage needs a column to read. Apply it to the "
                        "column directly rather than to an expression over it."
                    ),
                    context={"semantic_type": name},
                )
            # The implementation's hash travels with the residual, so editing
            # a validator changes the plan id of every control that uses it.
            # Without this the code is part of the control's *meaning* and not
            # part of its identity: somebody edits the check digit routine, and
            # last month's evidence silently starts meaning something else
            # while claiming to be the same control.
            residual = {"validator": name, "column": subject.name}
            provenance = PLUGINS.provenance(name)
            if provenance is not None:
                residual["implementation"] = provenance.implementation_hash
            self._residuals.append(residual)
        return screen

    def _codelist(self, subject: Expr, argument: Expr | None) -> Expr:
        """A codelist, resolved into the values it stood for.

        Left unresolved it would have to be looked up at execution, which puts
        a control's meaning outside the artefact that names it: the plan hash
        would be identical before and after somebody edited the list, and two
        runs with different verdicts would claim to be the same control.
        """
        name = str(argument.value) if argument is not None else ""
        values = self._codelists.get(name)
        if values is None:
            raise ValidationError(
                f"the codelist {name!r} is not registered",
                remedy=(
                    "Register it before compiling, or write the values out. A control "
                    "cannot be run against a list nobody has defined."
                ),
                context={"codelist": name},
            )
        return Expr.operation("IN", subject, Expr.values(*(Expr.literal(v) for v in values)))

    # -- expressions -------------------------------------------------------

    def _expression(self, node: ast.Expression) -> Expr:
        if isinstance(node, ast.ColumnRef):
            return Expr.column(node.name)
        if isinstance(node, ast.Literal):
            return Expr.literal(node.value, _literal_type(node.literal_type))
        if isinstance(node, ast.ParameterRef):
            return Expr.parameter(node.name)
        if isinstance(node, ast.UnaryOp):
            folded = _fold_sign(node)
            if folded is not None:
                # -10 becomes the literal -10 rather than a negation applied to
                # 10. Both for correctness — a unary operator that reaches a
                # backend expecting two operands is a sign silently dropped —
                # and for identity: "-10" and "- 10" must hash the same, or two
                # spellings of one control become two controls.
                return folded
            return Expr.operation(node.operator, self._expression(node.operand))
        if isinstance(node, ast.BinaryOp):
            if node.operator.endswith("BETWEEN") and isinstance(node.right, ast.ListExpression):
                lower, upper = node.right.items
                built = Expr.operation(
                    "BETWEEN",
                    self._expression(node.left),
                    self._expression(lower),
                    self._expression(upper),
                )
                return Expr.operation("NOT", built) if node.operator.startswith("NOT") else built
            return Expr.operation(
                node.operator, self._expression(node.left), self._expression(node.right)
            )
        if isinstance(node, ast.FunctionCall):
            return Expr.call(node.name.upper(), *(self._expression(a) for a in node.arguments))
        if isinstance(node, ast.ListExpression):
            return Expr.values(*(self._expression(item) for item in node.items))
        raise ValidationError(
            f"{type(node).__name__} has no IR form",
            remedy="Use an expression the language supports, or report the gap.",
            context={"node": type(node).__name__},
        )

    # -- metrics and thresholds -------------------------------------------

    def _metrics(
        self, predicate: Expr | None, kind: str, detail: dict[str, Any]
    ) -> tuple[Metric, ...]:
        scanned = Metric(name=SCANNED, aggregate=MetricAggregate.COUNT)
        if kind == "row_count":
            # The row count *is* the metric; there is no per-row violation.
            return (scanned,)
        if kind == "functional_dependency":
            # NOT the unique-key test. A functional dependency says each
            # determinant has one dependent, not that the determinant occurs
            # once — an account appears on a thousand rows and still belongs to
            # one entity. Testing distinct-against-scanned would fail every
            # legitimate dataset, which is a control that cannot be satisfied
            # dressed as one that is failing.
            determinant = [Expr.column(c) for c in detail.get("determinant", [])]
            pair = determinant + [Expr.column(c) for c in detail.get("dependent", [])]
            return (
                scanned,
                Metric(
                    name="distinct_determinants",
                    aggregate=MetricAggregate.COUNT_DISTINCT,
                    expression=Expr.values(*determinant),
                ),
                Metric(
                    name="distinct_pairs",
                    aggregate=MetricAggregate.COUNT_DISTINCT,
                    expression=Expr.values(*pair),
                ),
            )
        if kind == "unique_key":
            # No violating_rows metric: uniqueness is a property of the set, so
            # the count of offending rows is derived after the engine answers.
            # Emitting a literal zero for it would put a meaningless number on
            # the record.
            #
            # Nulls need their own count. Every engine's COUNT(DISTINCT)
            # ignores them, so scanned minus distinct silently charges each
            # null row as a duplicate — which it is not. A null key is its own
            # kind of failure: it identifies nothing, so it cannot be one row
            # per anything.
            keys = detail.get("key_columns", detail.get("determinant", []))
            key_is_null = _any_null(keys)
            return (
                scanned,
                Metric(
                    name="distinct_keys",
                    aggregate=MetricAggregate.COUNT_DISTINCT,
                    expression=Expr.values(*(Expr.column(c) for c in keys)),
                ),
                Metric(
                    name="null_key_rows",
                    aggregate=MetricAggregate.COUNT_IF,
                    expression=key_is_null,
                ),
            )
        if predicate is None:
            return (scanned,)
        return (
            scanned,
            Metric(
                name=VIOLATING,
                aggregate=MetricAggregate.COUNT_IF,
                expression=Expr.operation("NOT", predicate),
                applies_unknown_policy=True,
            ),
        )

    @staticmethod
    def _threshold(threshold: ast.Threshold) -> Threshold:
        if threshold.unit in ("rate", "percent"):
            # Relative to the scanned count rather than a second query: one
            # pass, and the denominator is on the record beside the numerator.
            return Threshold(
                metric=VIOLATING,
                comparator=Comparator.LE,
                value=threshold.value,
                relative_to=SCANNED,
            )
        return Threshold(
            metric=VIOLATING, comparator=Comparator(threshold.comparator), value=threshold.value
        )


def _literal_type(name: str) -> str:
    return {
        "text": "text",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
        "percentage": "number",
        "pattern": "pattern",
    }.get(name, "unknown")


def _hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def lower(control: ast.Control, **kwargs: Any) -> ControlPlan:
    return Lowerer(**kwargs).control(control)


def _fold_sign(node: ast.UnaryOp) -> Expr | None:
    """A signed numeric literal, as the single literal it is."""
    if node.operator not in ("-", "+") or not isinstance(node.operand, ast.Literal):
        return None
    if not isinstance(node.operand.value, int | float) or isinstance(node.operand.value, bool):
        return None
    value = node.operand.value if node.operator == "+" else -node.operand.value
    return Expr.literal(value, "number")


def _any_null(columns: list[str]) -> Expr:
    """True when any part of a key is missing."""
    tests = [Expr.operation("IS NULL", Expr.column(c)) for c in columns]
    if len(tests) == 1:
        return tests[0]
    combined = tests[0]
    for test in tests[1:]:
        combined = Expr.operation("OR", combined, test)
    return combined
