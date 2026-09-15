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

from prama.pql import ast, families
from prama.pql.errors import PqlTypeError
from prama.pql.functions import VOLATILE
from prama.pql.library import FUNCTIONS

#: Types the language reasons about. Deliberately coarse: the point is to catch
#: a comparison between a date and a currency code, not to model every engine's
#: numeric tower — which differs, and which the IR leaves to the engine.
# Re-exported from prama.pql.families, which has no dependencies. The
# catalogue and this module genuinely depend on each other — the checker
# consults the catalogue to type a call, and the catalogue declares its
# argument types in this vocabulary — so the names live in a leaf module both
# can import.
NUMBER = families.NUMBER
TEXT = families.TEXT
BOOLEAN = families.BOOLEAN
TEMPORAL = families.TEMPORAL
UNKNOWN = families.UNKNOWN

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
        # Function names are checked *before* the schema, because they do not
        # need one. A misspelled function is misspelled whether or not the
        # dataset has been declared, and holding the finding back until the
        # estate is described would mean the commonest mistake in a new control
        # is invisible for exactly as long as the control is new.
        findings: list[Finding] = self._function_check(control)
        schema = self._catalogue.get(control.target)
        if schema is None:
            return [
                *findings,
                Finding(
                    message=f"nothing is known about {control.target}",
                    remedy=(
                        f"Declare {control.target}, or bind it to a source so its columns "
                        f"can be discovered. The control will run, but its column names "
                        f"cannot be verified until then."
                    ),
                    position=control.position,
                    level="unchecked",
                ),
            ]
        for column in self._columns_of(control):
            findings.extend(self._resolve(column, schema))
        findings.extend(self._type_check(control, schema))
        return findings

    def _function_check(self, control: ast.Control) -> list[Finding]:
        """Every function call, against the catalogue.

        This check did not exist. An unrecognised name lowered, received a plan
        id, and compiled straight through to SQL — where it failed at execution
        or, worse, succeeded on an engine that happened to have a function of
        that name and meant something else.
        """
        findings: list[Finding] = []
        for expression in _expressions_of(control):
            for message, remedy, _name in check_calls(expression):
                findings.append(Finding(message=message, remedy=remedy, position=control.position))
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
            if assertion.operator == "has_length_between":
                # The bounds describe a *length*, not a value of the subject's
                # type, so comparing them with the subject is the wrong
                # question. Asking it flagged `CHECK t.isin HAS LENGTH BETWEEN
                # 12 AND 12` — one of the most ordinary controls in the language
                # — as comparing text with a number, twice, on every text
                # column, always. Checked positively below instead.
                # QA round 4, `PQL-092`.
                continue
            findings.extend(
                self._compare(subject, other, schema, assertion.subject, assertion.operator)
            )
        if assertion.operator == "has_length_between":
            # The check that was missing, and the half that made the defect
            # worth more than a false positive: exempting the comparison alone
            # would leave `CHECK t.notional HAS LENGTH BETWEEN 1 AND 3` — the
            # length of a *number* — passing clean, which it already did. The
            # old behaviour was not merely noisy, it was **inverted**: it
            # rejected the correct control and accepted the incorrect one.
            if subject not in (TEXT, UNKNOWN):
                findings.append(
                    Finding(
                        message=f"a length cannot be measured on a {subject}",
                        remedy=(
                            "HAS LENGTH BETWEEN counts characters, so it applies to text. "
                            "For a numeric range, write BETWEEN."
                        ),
                        position=assertion.position,
                    )
                )
            findings.extend(self._bounds_are_numbers(assertion, schema))
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

    def _bounds_are_numbers(
        self, assertion: ast.PredicateAssertion, schema: DatasetSchema
    ) -> list[Finding]:
        """A character count is a number, whatever the column holds."""
        findings: list[Finding] = []
        for bound in (assertion.argument, assertion.upper):
            if bound is None:
                continue
            found = self.type_of(bound, schema)
            if found in (NUMBER, UNKNOWN):
                continue
            findings.append(
                Finding(
                    message=f"a length bound must be a number, and {bound.render()} is {found}",
                    remedy="Write the number of characters, as in HAS LENGTH BETWEEN 12 AND 12.",
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
            # Aggregates are part of the language rather than the scalar
            # catalogue: they belong to a metric, not to a row expression.
            if _used_as_aggregate(node.name.upper(), len(node.arguments)):
                return _AGGREGATE_TYPES[node.name.upper()]
            declared = FUNCTIONS.find(node.name)
            return declared.returns if declared else UNKNOWN
        if isinstance(node, ast.BinaryOp):
            if node.operator in ("+", "-", "*", "/", "%"):
                return NUMBER
            return BOOLEAN
        if isinstance(node, ast.UnaryOp):
            return BOOLEAN if node.operator.isalpha() else NUMBER
        return UNKNOWN


#: Aggregates. Not in the function catalogue because they are not row
#: expressions: an aggregate belongs to a metric, and a catalogue entry
#: promises a per-row lowering it could not honour.
#:
#: `MIN` and `MAX`, not `MIN_AGG` and `MAX_AGG`. Those two spellings appeared
#: nowhere else in the codebase — no parser, lowering or backend ever produced
#: them — so a single-argument `MIN(notional)` missed this table entirely and
#: was checked against the *scalar* two-argument `MIN`, which reported
#: "MIN takes at least 2 argument(s), and was given 1" about a perfectly
#: ordinary aggregate (QA findings PQL-186 and PQL-187).
_AGGREGATE_TYPES: dict[str, str] = {
    "COUNT": NUMBER,
    "SUM": NUMBER,
    "AVG": NUMBER,
    "MIN": NUMBER,
    "MAX": NUMBER,
    "STDDEV": NUMBER,
}

#: The two names that are both an aggregate and a scalar function. `MIN(col)`
#: is the smallest value in a column; `MIN(a, b)` is the smaller of two. They
#: are told apart by arity, which is the only thing that distinguishes them and
#: is exactly how SQL does it.
_AGGREGATE_OR_SCALAR: frozenset[str] = frozenset({"MIN", "MAX"})


def _used_as_aggregate(name: str, argument_count: int) -> bool:
    """Whether this call is the aggregate rather than the scalar of that name."""
    if name not in _AGGREGATE_TYPES:
        return False
    if name in _AGGREGATE_OR_SCALAR:
        return argument_count == 1
    return True


def check_calls(node: ast.Expression) -> list[tuple[str, str, str]]:
    """Every function call problem in one expression.

    Returns ``(message, remedy, name)`` triples rather than raising, because a
    checker that stopped at the first mistake would make somebody fix an
    expression one error per attempt.

    This is the check that did not exist: an unrecognised name used to lower,
    receive a plan id and compile straight through to SQL, where it failed at
    execution — or worse, succeeded on an engine that happened to have a
    function of that name and meant something else.
    """
    problems: list[tuple[str, str, str]] = []
    for call in _calls_in(node):
        name = call.name.upper()
        if _used_as_aggregate(name, len(call.arguments)):
            continue
        declared = FUNCTIONS.find(name)
        if declared is None:
            if name in VOLATILE:
                problems.append(
                    (
                        f"{name} is refused: it returns {VOLATILE[name]}",
                        (
                            "A control has to replay — the same plan against the same "
                            "snapshot must give the same verdict, or the evidence is "
                            "not evidence. Pass the value in as a parameter, which is "
                            "recorded with the run."
                        ),
                        name,
                    )
                )
            else:
                problems.append(
                    (
                        f"there is no function called {name}",
                        "Available: " + ", ".join(FUNCTIONS.names()) + ".",
                        name,
                    )
                )
            continue
        if not declared.accepts(len(call.arguments)):
            problems.append(
                (
                    f"{name} takes {declared.arity_words()}, and was given {len(call.arguments)}",
                    declared.summary,
                    name,
                )
            )
    return problems


def _expressions_of(control: ast.Control) -> list[ast.Expression]:
    """Everywhere in a control an expression can hide."""
    found: list[ast.Expression] = []
    if control.where is not None:
        found.append(control.where)
    assertion = control.assertion
    for attribute in ("subject", "argument", "upper", "condition"):
        value = getattr(assertion, attribute, None)
        if isinstance(value, ast.Expression):
            found.append(value)
    return found


def _calls_in(node: ast.Expression) -> list[ast.FunctionCall]:
    found: list[ast.FunctionCall] = []
    stack: list[Any] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.FunctionCall):
            found.append(current)
            stack.extend(current.arguments)
        elif isinstance(current, ast.BinaryOp):
            stack.extend([current.left, current.right])
        elif isinstance(current, ast.UnaryOp):
            stack.append(current.operand)
        elif isinstance(current, ast.ListExpression):
            stack.extend(current.items)
    return found


def _columns_in(node: ast.Expression) -> list[ast.ColumnRef]:
    found = [node] if isinstance(node, ast.ColumnRef) else []
    for child in node.children():
        found.extend(_columns_in(child))
    return found
