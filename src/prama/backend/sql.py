"""Compiling an IR plan into SQL for one engine.

The whole point of the IR is that this file is the *only* place a control's
meaning is turned into a particular engine's syntax, and that it either
succeeds or refuses. There is no third option where it produces something
approximately right, because approximately right is indistinguishable from
right until the day it matters.

The compiled shape is one aggregate query producing every metric at once:

    SELECT count(*) AS scanned_rows,
           count(*) FILTER (WHERE NOT coalesce(pred, false)) AS violating_rows
    FROM "risk"."positions"
    WHERE "trade_status" = 'ACTIVE'

One pass, one set of numbers, and a denominator recorded beside every
numerator — so a rate is never computed from two queries that saw different
data.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.backend.dialect import SqlDialect, Unsupported, dialect
from prama.ir.model import ControlPlan, Expr, Metric, MetricAggregate
from prama.pql.errors import PqlUnsupportedError

#: Operators that map straight through to SQL with the same spelling.
INFIX: frozenset[str] = frozenset(
    {"=", "<>", ">", ">=", "<", "<=", "+", "-", "*", "/", "%", "||", "AND", "OR"}
)


@dataclasses.dataclass(frozen=True, slots=True)
class CompiledControl:
    """A plan, ready to run on one engine."""

    plan_id: str
    dialect: str
    metric_query: str
    sample_query: str = ""
    #: Names in the order the metric query returns them.
    metric_names: tuple[str, ...] = ()
    #: Parameters the run must bind before this can execute.
    parameters: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "dialect": self.dialect,
            "metric_query": self.metric_query,
            "sample_query": self.sample_query,
            "metric_names": list(self.metric_names),
            "parameters": list(self.parameters),
        }


class SqlCompiler:
    """One plan to one engine's SQL, or a refusal that says why."""

    def __init__(self, target: SqlDialect | str) -> None:
        self.dialect = dialect(target) if isinstance(target, str) else target

    # -- entry point -------------------------------------------------------

    def compile(self, plan: ControlPlan, *, table: str = "") -> CompiledControl:
        self._check_capabilities(plan)
        source = self.dialect.qualify(table or plan.scope.binding or plan.scope.dataset)
        where = self._where(plan)
        selects, names = self._metric_selects(plan)
        query = f"SELECT {', '.join(selects)}\nFROM {source}"
        if where:
            query += f"\nWHERE {where}"
        if plan.scope.segment_by:
            grouping = ", ".join(self.dialect.quote(c) for c in plan.scope.segment_by)
            query = (
                f"SELECT {grouping}, {', '.join(selects)}\nFROM {source}"
                + (f"\nWHERE {where}" if where else "")
                + f"\nGROUP BY {grouping}"
            )
            names = tuple(plan.scope.segment_by) + names
        return CompiledControl(
            plan_id=plan.plan_id,
            dialect=self.dialect.name,
            metric_query=query,
            sample_query=self._samples(plan, source, where),
            metric_names=names,
            parameters=tuple(sorted(plan.parameters())),
        )

    def _check_capabilities(self, plan: ControlPlan) -> None:
        """Refuse before compiling, so the message names the whole gap.

        Discovering a missing capability halfway through emitting SQL produces
        an error about a fragment; checking up front produces one about the
        control, which is what the author is looking at.
        """
        missing = self.dialect.missing(plan.requires)
        if missing:
            raise PqlUnsupportedError(
                f"{self.dialect.name} cannot run this control: it needs "
                f"{', '.join(sorted(missing))}",
                remedy=(
                    f"Run it on an engine that has {', '.join(sorted(missing))}, or "
                    f"express the control differently. Prama will not substitute "
                    f"something close: the same control would then mean two different "
                    f"things on two engines, and nothing would notice."
                ),
                context={"dialect": self.dialect.name, "missing": sorted(missing)},
            )

    # -- pieces ------------------------------------------------------------

    def _where(self, plan: ControlPlan) -> str:
        return self.expression(plan.scope.filter) if plan.scope.filter is not None else ""

    def _metric_selects(self, plan: ControlPlan) -> tuple[list[str], tuple[str, ...]]:
        selects: list[str] = []
        names: list[str] = []
        for metric in plan.metrics:
            selects.append(f"{self._metric(plan, metric)} AS {self.dialect.quote(metric.name)}")
            names.append(metric.name)
        return selects, tuple(names)

    def _metric(self, plan: ControlPlan, metric: Metric) -> str:
        if metric.aggregate is MetricAggregate.COUNT:
            return "COUNT(*)"
        if metric.aggregate is MetricAggregate.COUNT_IF:
            if metric.applies_unknown_policy:
                return self.dialect.count_if(self._violation_condition(plan))
            # An ordinary counted condition: an unknown is not a match, which
            # is SQL's own rule and the right one here — a row whose key we
            # cannot evaluate is not thereby a null key.
            condition = self.expression(metric.expression)
            false = self.dialect.boolean(False)
            return self.dialect.count_if(f"COALESCE({condition}, {false})")
        if metric.aggregate is MetricAggregate.COUNT_DISTINCT:
            expression = metric.expression
            parts = (
                [self.expression(a) for a in expression.args]
                if expression is not None and expression.kind == "list"
                else [self.expression(expression)]
                if expression is not None
                else ["*"]
            )
            # Only rows whose key is entirely present are counted. A key with
            # a missing part identifies nothing, so it is not a distinct
            # anything — it is counted as a null key instead, and the two
            # together account for every row.
            present = " AND ".join(f"{p} IS NOT NULL" for p in parts) if parts != ["*"] else ""
            return self.dialect.count_distinct(parts, where=present)
        if metric.aggregate is MetricAggregate.SUM and metric.expression is None:
            # A set-level violation count the strategy fills in; for a unique
            # key it is derived from the counts rather than summed per row.
            return "0"
        aggregate = metric.aggregate.value.upper()
        inner = self.expression(metric.expression) if metric.expression else "*"
        return f"{aggregate}({inner})"

    def _violation_condition(self, plan: ControlPlan) -> str:
        """When a row counts against the control.

        The predicate is stated positively — true means the row is fine — so a
        violation is its negation. The interesting part is the unknown: by
        default a row whose predicate cannot be evaluated is a violation, which
        is the inversion of SQL's own default and the reason
        ``COALESCE`` appears rather than a bare ``NOT``.
        """
        if plan.predicate is None:
            return self.dialect.boolean(False)
        predicate = self.expression(plan.predicate)
        false = self.dialect.boolean(False)
        if plan.unknown_is_violation:
            return f"NOT COALESCE({predicate}, {false})"
        return f"COALESCE(NOT ({predicate}), {false})"

    def _samples(self, plan: ControlPlan, source: str, where: str) -> str:
        """Rows to keep as evidence. Bounded, and only of failing rows."""
        if plan.evidence.level == "counts" or plan.predicate is None:
            return ""
        columns = sorted(plan.columns())
        projection = ", ".join(self.dialect.quote(c) for c in columns) if columns else "*"
        condition = self._violation_condition(plan)
        clause = f"({where}) AND ({condition})" if where else condition
        return self.dialect.limit(
            f"SELECT {projection}\nFROM {source}\nWHERE {clause}", plan.evidence.max_samples
        )

    # -- expressions -------------------------------------------------------

    def expression(self, node: Expr | None) -> str:
        if node is None:
            return self.dialect.boolean(True)
        if node.kind == "col":
            return self.dialect.quote(node.name)
        if node.kind == "lit":
            return self.dialect.literal(node.value)
        if node.kind == "param":
            # Named, not positional: a control with three parameters bound by
            # position is one edit away from silently checking the wrong dates.
            return f":{node.name}"
        if node.kind == "list":
            return "(" + ", ".join(self.expression(a) for a in node.args) + ")"
        if node.kind == "call":
            return self._call(node)
        return self._operation(node)

    def _call(self, node: Expr) -> str:
        name = node.name.upper()
        arguments = [self.expression(a) for a in node.args]
        if name == "LENGTH":
            return self.dialect.length(arguments[0])
        return f"{name}({', '.join(arguments)})"

    def _operation(self, node: Expr) -> str:
        operator = node.name
        arguments = [self.expression(a) for a in node.args]
        if operator in ("-", "+") and len(arguments) == 1:
            # A sign, not a subtraction. Joining a single operand with an infix
            # separator yields the operand alone, which silently drops the sign
            # — and every engine agrees on the wrong answer, so nothing notices.
            return f"({operator}{arguments[0]})"
        if operator in INFIX:
            if len(arguments) < 2:
                raise PqlUnsupportedError(
                    f"{operator} needs two operands and was given {len(arguments)}",
                    remedy="This is a defect in the compiler rather than in the control.",
                    context={"operator": operator, "operands": len(arguments)},
                )
            return "(" + f" {operator} ".join(arguments) + ")"
        if operator == "NOT":
            return f"NOT ({arguments[0]})"
        if operator == "IS NULL":
            return f"({arguments[0]} IS NULL)"
        if operator == "IS NOT NULL":
            return f"({arguments[0]} IS NOT NULL)"
        if operator in ("IN", "NOT IN"):
            return f"({arguments[0]} {operator} {arguments[1]})"
        if operator in ("BETWEEN", "NOT BETWEEN"):
            return f"({arguments[0]} {operator} {arguments[1]} AND {arguments[2]})"
        if operator in ("MATCHES", "NOT MATCHES"):
            return self._regex(node, arguments, negated=operator.startswith("NOT"))
        if operator == "IN CODELIST":
            # Resolved into a literal set before compilation; reaching here
            # means the codelist was never bound, and guessing would be worse
            # than saying so.
            raise PqlUnsupportedError(
                f"the codelist {node.args[1].value!r} has not been resolved",
                remedy=(
                    "Codelists are expanded before compilation. Register the codelist, "
                    "or replace it with an explicit set."
                ),
                context={"codelist": node.args[1].value},
            )
        raise PqlUnsupportedError(
            f"{operator} has no SQL form on {self.dialect.name}",
            remedy=(
                "Express the control differently, or run it on the local engine, "
                "which evaluates anything the language can express."
            ),
            context={"operator": operator, "dialect": self.dialect.name},
        )

    def _regex(self, node: Expr, arguments: list[str], *, negated: bool) -> str:
        pattern = node.args[1].value
        rendered = self.dialect.regex_match(arguments[0], str(pattern))
        if isinstance(rendered, Unsupported):
            raise PqlUnsupportedError(
                rendered.detail,
                remedy=rendered.remedy,
                context={"dialect": self.dialect.name, "capability": rendered.capability},
            )
        return f"NOT ({rendered})" if negated else f"({rendered})"


def compile_for(plan: ControlPlan, target: str, *, table: str = "") -> CompiledControl:
    return SqlCompiler(target).compile(plan, table=table)
