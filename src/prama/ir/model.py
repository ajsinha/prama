"""The Intermediate Representation: what a control means, engine-neutrally.

The IR is the portability contract. A control is parsed once into PQL, checked
once, and lowered once into this; every backend compiles *from here*, and the
conformance suite asserts that they all agree. Without a common artefact in the
middle, "the same control on two engines" degrades into two implementations that
happen to agree on the cases anybody tested.

Three properties are load-bearing.

**It is content-addressed.** The identifier of an IR node is a hash of its
meaning, so two controls that say the same thing in different words have the
same id, a control that has been edited has a different one, and an evidence
record can name exactly what produced it. Nothing about the hash depends on
where the control was written or by whom.

**It is closed.** Everything the executor needs is here — scope, metric,
threshold, evidence policy, parameters. A backend never reaches back to the AST,
because a backend that could would eventually diverge from the one that did not.

**It states its own requirements.** Each node declares the capabilities it needs
(regex, sampling, exact snapshot). A backend that lacks one refuses the control
at authoring time rather than degrading quietly at three in the morning.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from typing import Any

from prama.core.pjson import canonical, dumps

#: Bumped when the meaning of an existing field changes, never for an addition.
#: An evidence record names the version it was produced under, so a control
#: replayed years later is interpreted the way it was when it ran.
IR_VERSION = "1.0"


class MetricAggregate(enum.Enum):
    """How a metric is computed over the scope."""

    COUNT = "count"
    COUNT_IF = "count_if"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    AVG = "avg"
    APPROX_COUNT_DISTINCT = "approx_count_distinct"


class Comparator(enum.Enum):
    LE = "<="
    LT = "<"
    GE = ">="
    GT = ">"
    EQ = "="
    NE = "<>"

    def holds(self, left: float, right: float) -> bool:
        return {
            Comparator.LE: left <= right,
            Comparator.LT: left < right,
            Comparator.GE: left >= right,
            Comparator.GT: left > right,
            Comparator.EQ: left == right,
            Comparator.NE: left != right,
        }[self]


class Verdict(enum.Enum):
    """The outcome of a control.

    ``INDETERMINATE`` is first-class and is never quietly turned into a pass.
    A sample too small to support the declared confidence has not shown that
    the data is good; it has shown that we did not look hard enough, and those
    are different things to put in front of a regulator.
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"
    INDETERMINATE = "indeterminate"

    @property
    def is_actionable(self) -> bool:
        return self in (Verdict.FAIL, Verdict.ERROR, Verdict.INDETERMINATE)


@dataclasses.dataclass(frozen=True, slots=True)
class IrNode:
    """Anything that participates in the content hash."""

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @property
    def requires(self) -> frozenset[str]:
        """Backend capabilities this node needs to be expressible."""
        return frozenset()


@dataclasses.dataclass(frozen=True, slots=True)
class Expr(IrNode):
    """A typed expression over one row of the scope."""

    #: ``col``, ``lit``, ``param``, ``op``, ``call``, ``list``.
    kind: str = "lit"
    #: Column name, operator symbol, or function name, by kind.
    name: str = ""
    value: Any = None
    args: tuple[Expr, ...] = ()
    #: ``text``, ``number``, ``boolean``, ``null``, ``pattern``, ``unknown``.
    type_name: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.name:
            out["name"] = self.name
        if self.value is not None or self.kind == "lit":
            out["value"] = self.value
        if self.args:
            out["args"] = [a.to_dict() for a in self.args]
        if self.type_name != "unknown":
            out["type"] = self.type_name
        return out

    @property
    def requires(self) -> frozenset[str]:
        needed: set[str] = set()
        if self.kind == "op" and self.name in ("MATCHES", "NOT MATCHES"):
            needed.add("pushdown.regex")
        if self.kind == "call" and self.name.upper() in ("APPROX_COUNT_DISTINCT",):
            needed.add("pushdown.approx_distinct")
        for arg in self.args:
            needed |= arg.requires
        return frozenset(needed)

    def columns(self) -> frozenset[str]:
        """Every column this expression reads. Used for pruning and for lineage."""
        found = {self.name} if self.kind == "col" else set()
        for arg in self.args:
            found |= arg.columns()
        return frozenset(found)

    def parameters(self) -> frozenset[str]:
        found = {self.name} if self.kind == "param" else set()
        for arg in self.args:
            found |= arg.parameters()
        return frozenset(found)

    # -- constructors, so callers do not build raw kinds -------------------

    @classmethod
    def column(cls, name: str, type_name: str = "unknown") -> Expr:
        return cls(kind="col", name=name, type_name=type_name)

    @classmethod
    def literal(cls, value: Any, type_name: str = "text") -> Expr:
        return cls(kind="lit", value=value, type_name=type_name)

    @classmethod
    def parameter(cls, name: str) -> Expr:
        return cls(kind="param", name=name)

    @classmethod
    def operation(cls, operator: str, *args: Expr, type_name: str = "boolean") -> Expr:
        return cls(kind="op", name=operator, args=args, type_name=type_name)

    @classmethod
    def call(cls, function: str, *args: Expr, type_name: str = "unknown") -> Expr:
        return cls(kind="call", name=function, args=args, type_name=type_name)

    @classmethod
    def values(cls, *args: Expr) -> Expr:
        return cls(kind="list", args=args, type_name="list")


@dataclasses.dataclass(frozen=True, slots=True)
class Scope(IrNode):
    """Which records a control is about."""

    dataset: str = ""
    #: Where the dataset physically is, when one binding has been chosen. Part
    #: of the hash: the same control against two bindings is two controls, and
    #: conflating them would let evidence from one be replayed against the other.
    binding: str = ""
    filter: Expr | None = None
    segment_by: tuple[str, ...] = ()
    #: Parameter name holding the run's business date, if the scope is dated.
    as_of: str = ""
    window: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "binding": self.binding,
            "filter": self.filter.to_dict() if self.filter else None,
            "segment_by": list(self.segment_by),
            "temporal": {"as_of": self.as_of, "window": self.window},
        }

    @property
    def requires(self) -> frozenset[str]:
        base = self.filter.requires if self.filter else frozenset()
        return base | (frozenset({"pushdown.filter"}) if self.filter else frozenset())

    def columns(self) -> frozenset[str]:
        return (self.filter.columns() if self.filter else frozenset()) | frozenset(self.segment_by)


@dataclasses.dataclass(frozen=True, slots=True)
class Metric(IrNode):
    """A named quantity the control computes.

    Metrics, not just a verdict. The verdict answers "is it broken today"; the
    metrics answer "is it getting worse", and a platform that keeps only the
    first can never tell anybody the second.
    """

    name: str = ""
    aggregate: MetricAggregate = MetricAggregate.COUNT
    expression: Expr | None = None
    #: Whether an unknown counts toward this metric. True for the violation
    #: count, where the control's unknown policy decides; false for every other
    #: counted condition, where an unknown simply is not a match.
    #:
    #: Stated rather than inferred from the metric's name. A backend that
    #: guessed "the one called violating_rows is special" would apply the
    #: policy to the wrong metric the first time another counted condition was
    #: added — which is exactly what happened with the null-key count.
    applies_unknown_policy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agg": self.aggregate.value,
            "expr": self.expression.to_dict() if self.expression else None,
            "unknown_policy": self.applies_unknown_policy,
        }

    @property
    def requires(self) -> frozenset[str]:
        needed = self.expression.requires if self.expression else frozenset()
        if self.aggregate is MetricAggregate.APPROX_COUNT_DISTINCT:
            needed = needed | {"pushdown.approx_distinct"}
        return frozenset(needed)


@dataclasses.dataclass(frozen=True, slots=True)
class Threshold(IrNode):
    """When the metrics mean failure."""

    metric: str = "violating_rows"
    comparator: Comparator = Comparator.LE
    value: float = 0.0
    #: When set, the metric is divided by this one before comparing — so a rate
    #: threshold is expressed without a second pass over the data.
    relative_to: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "op": self.comparator.value,
            "value": self.value,
            "relative_to": self.relative_to,
        }

    def evaluate(self, metrics: dict[str, float]) -> Verdict:
        """Apply the threshold to computed metrics.

        A missing metric is indeterminate rather than a pass. The control did
        not demonstrate anything, and saying so is the honest answer.
        """
        if self.metric not in metrics:
            return Verdict.INDETERMINATE
        observed = float(metrics[self.metric])
        if self.relative_to:
            denominator = float(metrics.get(self.relative_to, 0.0))
            if denominator == 0:
                # No rows to judge. Not a pass and not a failure: an empty
                # scope is a fact about the scope, and calling it a pass is how
                # a broken feed reports green.
                return Verdict.INDETERMINATE
            observed /= denominator
        return Verdict.PASS if self.comparator.holds(observed, self.value) else Verdict.FAIL


@dataclasses.dataclass(frozen=True, slots=True)
class EvidencePolicy(IrNode):
    level: str = "samples"
    max_samples: int = 50
    masking: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "max_samples": self.max_samples, "masking": self.masking}


@dataclasses.dataclass(frozen=True, slots=True)
class Provenance(IrNode):
    """Where a control came from. Outside the content hash, deliberately.

    Two controls that mean the same thing must hash the same however they were
    authored — otherwise the hash identifies the paperwork rather than the
    meaning, and deduplication, caching and "has this actually changed" all
    stop working.
    """

    source: str = "declaration"
    declared_by: str = ""
    pql_hash: str = ""
    authored_by: str = ""
    approved_by: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "declared_by": self.declared_by,
            "pql_hash": self.pql_hash,
            "authored_by": self.authored_by,
            "approved_by": self.approved_by,
            "version": self.version,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ControlPlan(IrNode):
    """One control, lowered. The artefact every backend compiles from."""

    scope: Scope = dataclasses.field(default_factory=Scope)
    #: The row-level condition that must hold. A row for which it is false —
    #: or, unless ``unknown_is_violation`` is off, unknown — is a violation.
    predicate: Expr | None = None
    metrics: tuple[Metric, ...] = ()
    threshold: Threshold = dataclasses.field(default_factory=Threshold)
    evidence: EvidencePolicy = dataclasses.field(default_factory=EvidencePolicy)
    unknown_is_violation: bool = True
    severity: str = "major"
    dimensions: tuple[str, ...] = ()
    because: str = ""
    #: The generated plain-language sentence, carried so that a finding can be
    #: explained without re-deriving it from an AST the executor never sees.
    description: str = ""
    #: Kind of assertion, for backends that need a strategy rather than a
    #: predicate: ``predicate``, ``unique_key``, ``row_count``, ``reference``,
    #: ``freshness``, ``functional_dependency``.
    assertion_kind: str = "predicate"
    #: Assertion-specific detail, e.g. the key columns of a unique key.
    detail: dict[str, Any] = dataclasses.field(default_factory=dict)
    provenance: Provenance = dataclasses.field(default_factory=Provenance)

    # -- identity ----------------------------------------------------------

    def meaning(self) -> dict[str, Any]:
        """Everything that decides what this control does. Hashed.

        Provenance, description and the justification are excluded: they say
        who wrote it and why, not what it does. Including them would make an
        edited comment look like a changed control, and every cached result
        would be discarded for nothing.
        """
        return {
            "ir_version": IR_VERSION,
            "assertion_kind": self.assertion_kind,
            "predicate": self.predicate.to_dict() if self.predicate else None,
            "unknown_policy": "violation" if self.unknown_is_violation else "pass",
            "scope": self.scope.to_dict(),
            "metrics": [m.to_dict() for m in self.metrics],
            "threshold": self.threshold.to_dict(),
            "detail": self.detail,
            # Evidence level changes what is *kept*, not what is *computed*, so
            # it stays out: two runs differing only in sampling depth are the
            # same control and should share a plan id.
        }

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(canonical(self.meaning())).hexdigest()

    @property
    def plan_id(self) -> str:
        """The identifier an evidence record names."""
        return f"ir:sha256:{self.content_hash}"

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.meaning(),
            "id": self.plan_id,
            "evidence": self.evidence.to_dict(),
            "severity": self.severity,
            "dimensions": list(self.dimensions),
            "because": self.because,
            "description": self.description,
            "provenance": self.provenance.to_dict(),
        }

    def to_json(self, *, indent: bool = True) -> str:
        return dumps(self.to_dict(), sort_keys=True, indent=indent)

    # -- requirements ------------------------------------------------------

    @property
    def requires(self) -> frozenset[str]:
        needed = set(self.scope.requires)
        if self.predicate is not None:
            needed |= self.predicate.requires
        for metric in self.metrics:
            needed |= metric.requires
        if self.assertion_kind in ("unique_key", "functional_dependency"):
            needed.add("pushdown.aggregation")
        if self.scope.segment_by:
            needed.add("pushdown.aggregation")
        return frozenset(needed)

    def columns(self) -> frozenset[str]:
        """Every column touched, so a backend can project only what it needs."""
        found = set(self.scope.columns())
        if self.predicate is not None:
            found |= self.predicate.columns()
        for metric in self.metrics:
            if metric.expression is not None:
                found |= metric.expression.columns()
        for key in ("key_columns", "determinant", "dependent"):
            found |= set(self.detail.get(key, ()))
        return frozenset(found)

    def parameters(self) -> frozenset[str]:
        """Every value the run must supply. Checked before execution."""
        found: set[str] = set()
        if self.scope.filter is not None:
            found |= self.scope.filter.parameters()
        if self.predicate is not None:
            found |= self.predicate.parameters()
        if self.scope.as_of:
            found.add(self.scope.as_of)
        return frozenset(found)

    def metric(self, name: str) -> Metric | None:
        return next((m for m in self.metrics if m.name == name), None)
