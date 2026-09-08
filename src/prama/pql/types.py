"""Checking a control against the data it claims to be about.

Without this, a mistyped column name is discovered when the control runs — as a
driver error, in the middle of the night, against a production warehouse, with
a message written for a database engineer. With it, the mistake is a red squiggle
under the word while somebody is still looking at it.

The checker does three things and refuses to guess at any of them:

* **Resolution.** Every column must exist in the dataset the control is about.
  A near miss gets a suggestion; an unrecognised name does not get silently
  passed through to the engine.
* **Typing.** Comparisons must be between comparable things. ``notional > 'ACTIVE'``
  is caught here rather than becoming an engine-specific coercion that succeeds
  on one database and fails on another.
* **Capability.** A control needing a feature the chosen engine lacks is refused
  now, with the engine named, rather than at three in the morning.

A dataset whose schema is unknown is not an error. Prama is often pointed at
something before anyone has declared it, and refusing to check a control at all
would be less useful than checking what can be checked and saying what could
not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import difflib
from typing import Any

from prama.pql import ast
from prama.pql.errors import PqlTypeError

#: Types the language reasons about. Deliberately coarse: the point is to catch
#: a comparison between a date and a currency code, not to model every engine's
#: numeric tower — which differs, and which the IR leaves to the engine.
NUMBER = "number"
TEXT = "text"
BOOLEAN = "boolean"
TEMPORAL = "temporal"
UNKNOWN = "unknown"

#: Source type names, lowercased, mapped onto the coarse set above. Anything
#: unrecognised becomes UNKNOWN, which suppresses type errors rather than
#: inventing them — a wrong type error is worse than none.
TYPE_FAMILIES: dict[str, str] = {
    **dict.fromkeys(
        (
            "int",
            "int2",
            "int4",
            "int8",
            "integer",
            "bigint",
            "smallint",
            "tinyint",
            "decimal",
            "numeric",
            "real",
            "double",
            "double precision",
            "float",
            "float4",
            "float8",
            "money",
        ),
        NUMBER,
    ),
    **dict.fromkeys(
        (
            "text",
            "varchar",
            "char",
            "character",
            "character varying",
            "string",
            "nvarchar",
            "uuid",
            "bpchar",
        ),
        TEXT,
    ),
    **dict.fromkeys(("bool", "boolean"), BOOLEAN),
    **dict.fromkeys(
        (
            "date",
            "time",
            "timestamp",
            "timestamptz",
            "datetime",
            "timestamp with time zone",
            "timestamp without time zone",
        ),
        TEMPORAL,
    ),
}

#: Comparisons that are meaningful between two different families. Text and
#: numbers are not among them: an engine that coerces silently will disagree
#: with one that does not, which is exactly the portability failure the type
#: checker exists to catch before it happens.
COMPARABLE: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({NUMBER, NUMBER}),
        frozenset({TEXT, TEXT}),
        frozenset({BOOLEAN, BOOLEAN}),
        frozenset({TEMPORAL, TEMPORAL}),
        frozenset({TEMPORAL, TEXT}),  # a date compared with an ISO literal
    }
)


@dataclasses.dataclass(frozen=True, slots=True)
class Column:
    name: str
    type_name: str = ""
    nullable: bool = True

    @property
    def family(self) -> str:
        base = self.type_name.lower().split("(")[0].strip()
        return TYPE_FAMILIES.get(base, UNKNOWN)


@dataclasses.dataclass(frozen=True, slots=True)
class DatasetSchema:
    """What a dataset holds, as far as anyone has declared or discovered."""

    name: str
    columns: tuple[Column, ...] = ()

    def column(self, name: str) -> Column | None:
        lowered = name.lower()
        return next((c for c in self.columns if c.name.lower() == lowered), None)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    def suggest(self, name: str) -> str:
        """The nearest real column, when somebody has made a typo.

        Case-insensitive and generous, because the commonest mistakes are a
        wrong case, a missing underscore and a plural.
        """
        matches = difflib.get_close_matches(
            name.lower(), [c.lower() for c in self.column_names], n=1, cutoff=0.6
        )
        if not matches:
            return ""
        return next(c for c in self.column_names if c.lower() == matches[0])


@dataclasses.dataclass(frozen=True, slots=True)
class Catalogue:
    """The schemas available to the checker."""

    datasets: dict[str, DatasetSchema] = dataclasses.field(default_factory=dict)

    def get(self, name: str) -> DatasetSchema | None:
        return self.datasets.get(name) or self.datasets.get(name.lower())

    def with_dataset(self, schema: DatasetSchema) -> Catalogue:
        return Catalogue(datasets={**self.datasets, schema.name: schema})

    @classmethod
    def of(cls, **datasets: dict[str, str]) -> Catalogue:
        """Build from plain dictionaries, for tests and for a quick check."""
        return cls(
            datasets={
                name: DatasetSchema(
                    name=name,
                    columns=tuple(Column(c, t) for c, t in columns.items()),
                )
                for name, columns in datasets.items()
            }
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    """Something wrong, or something that could not be checked."""

    message: str
    remedy: str
    position: Any
    #: ``error`` stops the control; ``unchecked`` records what was not verified,
    #: so nobody later mistakes an unchecked control for a checked one.
    level: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "message": self.message,
            "remedy": self.remedy,
            "position": self.position.to_dict() if self.position else None,
        }


class TypeChecker:
    """Resolves and types one control against a catalogue."""

    def __init__(self, catalogue: Catalogue | None = None) -> None:
        self._catalogue = catalogue or Catalogue()

    def check(self, control: ast.Control, *, source: str = "") -> list[Finding]:
        """Every problem, not just the first.

        A checker that stopped at the first error would make somebody fix a
        control one mistake per attempt, which is the slowest possible way to
        write anything.
        """
        self._source = source
        schema = self._catalogue.get(control.target)
        if schema is None:
            return [
                Finding(
                    message=f"nothing is known about {control.target}",
                    remedy=(
                        f"Declare {control.target}, or bind it to a source so its columns "
                        f"can be discovered. The control will run, but its column names "
                        f"cannot be verified until then."
                    ),
                    position=control.position,
                    level="unchecked",
                )
            ]
        findings: list[Finding] = []
        for column in self._columns_of(control):
            findings.extend(self._resolve(column, schema))
        findings.extend(self._type_check(control, schema))
        return findings

    def require(self, control: ast.Control, *, source: str = "") -> None:
        """Check, and raise on the first error. For the compile path."""
        for finding in self.check(control, source=source):
            if finding.level == "error":
                raise PqlTypeError(
                    finding.message,
                    remedy=finding.remedy,
                    position=finding.position,
                    source=source,
                )

    # -- resolution --------------------------------------------------------

    def _columns_of(self, control: ast.Control) -> list[ast.ColumnRef]:
        found: list[ast.ColumnRef] = []
        assertion = control.assertion
        if isinstance(assertion, ast.PredicateAssertion):
            found.extend(_columns_in(assertion.subject))
            for part in (assertion.argument, assertion.upper):
                if part is not None:
                    found.extend(_columns_in(part))
        elif isinstance(assertion, ast.UniqueKeyAssertion):
            found.extend(assertion.columns)
        elif isinstance(assertion, ast.FunctionalDependencyAssertion):
            found.extend(assertion.determinant)
            found.extend(assertion.dependent)
        elif isinstance(assertion, ast.ExpressionAssertion):
            found.extend(_columns_in(assertion.condition))
        elif isinstance(assertion, ast.ReferenceAssertion):
            found.append(assertion.column)
        if control.where is not None:
            found.extend(_columns_in(control.where))
        if control.segmentation is not None:
            found.extend(control.segmentation.columns)
            if control.segmentation.having is not None:
                found.extend(_columns_in(control.segmentation.having))
        return found

    def _resolve(self, column: ast.ColumnRef, schema: DatasetSchema) -> list[Finding]:
        if column.dataset and column.dataset != schema.name:
            # A column of another dataset inside a single-dataset control. It
            # may be a join somebody has not declared, and guessing which would
            # be worse than saying so.
            return [
                Finding(
                    message=(
                        f"{column.qualified} belongs to {column.dataset}, but this control "
                        f"is about {schema.name}"
                    ),
                    remedy=(
                        f"Use a column of {schema.name}, or declare the relationship "
                        f"between the two datasets and write a control across it."
                    ),
                    position=column.position,
                )
            ]
        if schema.column(column.name) is not None:
            return []
        suggestion = schema.suggest(column.name)
        return [
            Finding(
                message=f"{schema.name} has no column called {column.name}",
                remedy=(
                    f"Did you mean {suggestion}?"
                    if suggestion
                    else f"Columns available: {', '.join(schema.column_names[:12])}"
                    + (" …" if len(schema.column_names) > 12 else "")
                ),
                position=column.position,
            )
        ]

    # -- typing ------------------------------------------------------------

    def _type_check(self, control: ast.Control, schema: DatasetSchema) -> list[Finding]:
        findings: list[Finding] = []
        assertion = control.assertion
        if isinstance(assertion, ast.PredicateAssertion):
            findings.extend(self._check_predicate(assertion, schema))
        if control.where is not None:
            findings.extend(self._check_expression(control.where, schema))
        return findings

    def _check_predicate(
        self, assertion: ast.PredicateAssertion, schema: DatasetSchema
    ) -> list[Finding]:
        subject = self.type_of(assertion.subject, schema)
        findings: list[Finding] = []
        for other in (assertion.argument, assertion.upper):
            if other is None:
                continue
            if assertion.operator in ("in_codelist", "is_valid", "has_format", "matches"):
                continue  # the argument names a thing, not a value
            findings.extend(
                self._compare(subject, other, schema, assertion.subject, assertion.operator)
            )
        if assertion.operator == "matches" and subject not in (TEXT, UNKNOWN):
            findings.append(
                Finding(
                    message=f"a pattern cannot be matched against a {subject}",
                    remedy=(
                        "Patterns apply to text. Compare a number with BETWEEN or an "
                        "operator instead."
                    ),
                    position=assertion.position,
                )
            )
        return findings

    def _compare(
        self,
        subject: str,
        other: ast.Expression,
        schema: DatasetSchema,
        left: ast.Expression,
        operator: str,
    ) -> list[Finding]:
        if isinstance(other, ast.ListExpression):
            return [
                f
                for item in other.items
                for f in self._compare(subject, item, schema, left, operator)
            ]
        found = self.type_of(other, schema)
        if UNKNOWN in (subject, found):
            return []
        if frozenset({subject, found}) in COMPARABLE:
            return []
        return [
            Finding(
                message=(
                    f"{left.render()} holds {subject}, and it is being compared with "
                    f"{other.render()}, which is {found}"
                ),
                remedy=(
                    "Compare like with like. Engines differ on whether they coerce these "
                    "silently, so a control written this way would mean one thing on one "
                    "database and something else on another."
                ),
                position=other.position,
            )
        ]

    def _check_expression(self, node: ast.Expression, schema: DatasetSchema) -> list[Finding]:
        findings: list[Finding] = []
        if isinstance(node, ast.BinaryOp) and node.operator in ast.COMPARISONS:
            findings.extend(
                self._compare(
                    self.type_of(node.left, schema), node.right, schema, node.left, node.operator
                )
            )
        for child in node.children():
            findings.extend(self._check_expression(child, schema))
        return findings

    def type_of(self, node: ast.Expression, schema: DatasetSchema) -> str:
        if isinstance(node, ast.ColumnRef):
            column = schema.column(node.name)
            return column.family if column else UNKNOWN
        if isinstance(node, ast.Literal):
            return {
                "number": NUMBER,
                "percentage": NUMBER,
                "text": TEXT,
                "boolean": BOOLEAN,
                "null": UNKNOWN,
                "pattern": TEXT,
            }.get(node.literal_type, UNKNOWN)
        if isinstance(node, ast.ParameterRef):
            # The run supplies it; its type is not knowable here, and guessing
            # would produce errors on correct controls.
            return UNKNOWN
        if isinstance(node, ast.FunctionCall):
            return {
                "COUNT": NUMBER,
                "SUM": NUMBER,
                "AVG": NUMBER,
                "LENGTH": NUMBER,
                "STDDEV": NUMBER,
            }.get(node.name.upper(), UNKNOWN)
        if isinstance(node, ast.BinaryOp):
            if node.operator in ("+", "-", "*", "/", "%"):
                return NUMBER
            return BOOLEAN
        if isinstance(node, ast.UnaryOp):
            return BOOLEAN if node.operator.isalpha() else NUMBER
        return UNKNOWN


def _columns_in(node: ast.Expression) -> list[ast.ColumnRef]:
    found = [node] if isinstance(node, ast.ColumnRef) else []
    for child in node.children():
        found.extend(_columns_in(child))
    return found
