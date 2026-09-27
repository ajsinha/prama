"""The shape of a control, after parsing and before anything is decided.

Two properties are worth more than any others here.

**Every node knows where it came from.** A type error on a column reference has
to point at that column, not at the control containing it — and a rendered
control has to be able to highlight the clause a finding came from.

**Every node carries its justification.** ``BECAUSE`` is not a comment. A
control that cannot say why it exists is a control nobody will maintain, and
when it fires at 3am the sentence explaining what the business declared is the
most useful thing on the screen. The parser requires it on anything generated
from a declaration and the renderer puts it first.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from decimal import Decimal
from typing import Any, Final

from prama.pql.errors import Position


def exact(value: Any, *, scale: int = 1) -> str:
    """A number as text that re-reads as the same number.

    Replaces `:g`, which keeps six significant figures: `1234567` rendered as
    `1.23457e+06` and re-read as 1234570 (QA C22). *scale* is exact too, so a
    rate of 0.001234567 is 0.1234567%, not whatever `* 100` in binary gives.
    """
    number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    number *= scale
    if number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")


#: A dataset name the parser reads bare. Anything else (a schema-qualified
#: `stg.trades`) must be written quoted, or the rendered text does not re-read.
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def quote_dataset(name: str) -> str:
    """*name* as PQL text: bare when it can be, quoted when it must be.

    Rendering dropped the quotes, so `CHECK "stg.trades".notional IS NOT NULL`
    came back as `stg.trades.notional`, which the parser refuses: a control over
    a schema-qualified dataset did not survive a format round trip (Q-124).
    """
    return name if not name or _PLAIN.fullmatch(name) else '"' + name.replace('"', '""') + '"'


class Severity(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return list(Severity).index(self)


class Dimension(enum.Enum):
    """The quality dimensions a finding can belong to."""

    COMPLETENESS = "completeness"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"
    CONSISTENCY = "consistency"
    ACCURACY = "accuracy"
    TIMELINESS = "timeliness"
    INTEGRITY = "integrity"
    CONFORMITY = "conformity"


class UnknownPolicy(enum.Enum):
    """What an expression evaluating to UNKNOWN means for the assertion.

    SQL's default is that unknown is not a violation, and that default is the
    most reliable source of false confidence in production data quality suites:
    a rule over a column that is entirely null passes, silently, for years. PQL
    inverts it. ``TREAT UNKNOWN AS PASS`` restores the SQL behaviour where a
    business genuinely means it, and the choice is then recorded in the control.
    """

    VIOLATION = "violation"
    PASS = "pass"


class EvidenceLevel(enum.Enum):
    COUNTS = "counts"
    SAMPLES = "samples"
    FULL = "full"


class FailAction(enum.Enum):
    ALERT = "alert"
    BLOCK = "block"
    QUARANTINE = "quarantine"
    TAG = "tag"


@dataclasses.dataclass(frozen=True, slots=True)
class Node:
    """Base for everything with a place in the source.

    ``position`` is excluded from equality. Where a node sits in the text is
    metadata for error messages, not part of what it means — and excluding it
    makes ``parse(render(x)) == x`` a property that can actually be asserted,
    which is the only real test a formatter has. Comparing rendered strings
    instead would have missed the parenthesisation bug that prompted this,
    where the text was stable and the meaning was not.
    """

    position: Position = dataclasses.field(
        default_factory=Position, kw_only=True, compare=False, repr=False
    )


# -- expressions -----------------------------------------------------------


#: **The one ordering.** Loosest first, tightest last. `parser.PRECEDENCE`
#: derives from this and so does `BINDING` below, because the two used to be
#: written out separately and a comment asked them to agree.
#:
#: They did not. `PRECEDENCE` listed `!=` and `BINDING` did not, so
#: `BINDING.get(op, ATOM_BINDING)` scored it 100 — tighter than multiplication —
#: and a `!=` comparison would never have been bracketed. Unreachable today
#: because the parser normalises the alias away before a node exists, which is
#: exactly the kind of "harmless" drift that stops being harmless when somebody
#: adds an operator. QA `PQL-198`, `PQL-199`.
PRECEDENCE_LEVELS: tuple[tuple[str, ...], ...] = (
    ("OR",),
    ("AND",),
    ("NOT",),
    ("=", "<>", ">", ">=", "<", "<="),
    ("+", "-", "||"),
    ("*", "/", "%"),
)

#: Surface spellings the parser accepts and normalises before building a node.
#: They belong to what is **read** and not to what is **rendered**, which is the
#: asymmetry that made a missing `BINDING` entry look like an oversight. Declared
#: here so the answer is in the table rather than in the parser's control flow.
OPERATOR_ALIASES: dict[str, str] = {"!=": "<>"}

#: Keyword predicates bind at the comparison level, so `a = 1 AND b IN (…)`
#: groups the way a reader expects. They never appear in `PRECEDENCE` — the
#: parser reaches them by keyword, not by the binary-operator loop — which is why
#: `BINDING` is larger than the ordering above and not a copy of it.
_KEYWORD_PREDICATES: tuple[str, ...] = (
    "IN",
    "NOT IN",
    "BETWEEN",
    "NOT BETWEEN",
    "MATCHES",
    "NOT MATCHES",
    "LIKE",
    "NOT LIKE",
    "ILIKE",
    "NOT ILIKE",
    "IS NULL",
    "IS NOT NULL",
)

_COMPARISON_LEVEL: Final = next(
    index for index, level in enumerate(PRECEDENCE_LEVELS, start=1) if "=" in level
)

#: How tightly each operator binds when rendering. Higher binds tighter.
#: Derived from `PRECEDENCE_LEVELS`, so it cannot disagree with the parser.
BINDING: dict[str, int] = {
    **{
        operator: level
        for level, operators in enumerate(PRECEDENCE_LEVELS, start=1)
        for operator in operators
    },
    **dict.fromkeys(_KEYWORD_PREDICATES, _COMPARISON_LEVEL),
}

#: A value binds tighter than any operator, so it never needs bracketing.
ATOM_BINDING = 100


@dataclasses.dataclass(frozen=True, slots=True)
class Expression(Node):
    """Anything that has a value for a row."""

    def children(self) -> tuple[Expression, ...]:
        return ()

    def render(self) -> str:
        raise NotImplementedError

    @property
    def binding(self) -> int:
        return ATOM_BINDING

    def render_within(self, parent: int, *, right: bool = False) -> str:
        """Render, bracketing only where the meaning would otherwise change.

        Brackets everywhere would be safe and unreadable; brackets nowhere
        silently rewrites the control. The rule is the ordinary one: bracket a
        child that binds more loosely than its parent, and a right operand that
        binds equally, since every operator here is left-associative.
        """
        text = self.render()
        if self.binding < parent or (right and self.binding == parent):
            return f"({text})"
        return text


@dataclasses.dataclass(frozen=True, slots=True)
class Literal(Expression):
    value: Any = None
    #: ``number``, ``text``, ``boolean``, ``null``, ``percentage``, ``pattern``.
    literal_type: str = "text"

    def render(self) -> str:
        if self.literal_type == "text":
            escaped = str(self.value).replace("'", "''")
            return f"'{escaped}'"
        if self.literal_type == "null":
            return "NULL"
        if self.literal_type == "percentage":
            return f"{exact(self.value, scale=100)}%"
        if self.literal_type == "boolean":
            return "TRUE" if self.value else "FALSE"
        if self.literal_type == "pattern":
            return f"/{self.value}/"
        return str(self.value)


@dataclasses.dataclass(frozen=True, slots=True)
class ColumnRef(Expression):
    """A column, optionally qualified by its dataset."""

    name: str = ""
    dataset: str = ""

    @property
    def qualified(self) -> str:
        return f"{self.dataset}.{self.name}" if self.dataset else self.name

    def render(self) -> str:
        return f"{quote_dataset(self.dataset)}.{self.name}" if self.dataset else self.name


@dataclasses.dataclass(frozen=True, slots=True)
class SelectedAttribute(Expression):
    """Stands for whichever attribute a selector matched.

    A control written against a selector has no column until it is expanded, and
    expansion replaces this with the real one. A placeholder rather than an
    empty column name, so a control that somehow reaches execution unexpanded
    fails loudly instead of querying a column called "".
    """

    def render(self) -> str:
        return "ATTRIBUTE"


@dataclasses.dataclass(frozen=True, slots=True)
class ParameterRef(Expression):
    """A value supplied by the run rather than written in the control.

    The whole reason ``CURRENT_DATE`` is refused inside an expression: a
    control that reads the clock is not reproducible, and an evidence record
    that cannot be reproduced is an assertion rather than a finding.
    """

    name: str = ""

    def render(self) -> str:
        return f"${self.name}"


@dataclasses.dataclass(frozen=True, slots=True)
class UnaryOp(Expression):
    operator: str = ""
    operand: Expression = dataclasses.field(default_factory=lambda: Literal(value=None))

    def children(self) -> tuple[Expression, ...]:
        return (self.operand,)

    @property
    def binding(self) -> int:
        return BINDING.get(self.operator, ATOM_BINDING)

    def render(self) -> str:
        # IS NULL follows its operand; NOT and the signs precede it.
        if self.operator.startswith("IS "):
            return f"{self.operand.render_within(self.binding)} {self.operator}"
        joiner = " " if self.operator[0].isalpha() else ""
        return f"{self.operator}{joiner}{self.operand.render_within(self.binding)}"


@dataclasses.dataclass(frozen=True, slots=True)
class BinaryOp(Expression):
    operator: str = ""
    left: Expression = dataclasses.field(default_factory=lambda: Literal(value=None))
    right: Expression = dataclasses.field(default_factory=lambda: Literal(value=None))

    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    @property
    def binding(self) -> int:
        return BINDING.get(self.operator, ATOM_BINDING)

    def render(self) -> str:
        if (
            isinstance(self.left, BinaryOp)
            and self.left.operator == self.operator
            and not self.operator.endswith("BETWEEN")
        ):
            # A left-leaning run of one operator, walked iteratively: rendering
            # a generated thousand-term OR recursed to a `RecursionError`
            # (QA C20). Same text as the recursive form: every operator here
            # is left-associative, so only right operands may need brackets.
            rights: list[Expression] = []
            node: Expression = self
            while isinstance(node, BinaryOp) and node.operator == self.operator:
                rights.append(node.right)
                node = node.left
            parts = [node.render_within(self.binding)]
            parts += [r.render_within(self.binding, right=True) for r in reversed(rights)]
            return f" {self.operator} ".join(parts)
        left = self.left.render_within(self.binding)
        if self.operator.endswith("BETWEEN") and isinstance(self.right, ListExpression):
            lower, upper = self.right.items
            # The bounds bind tighter than AND, or the rendered text reads as
            # BETWEEN (lower AND upper) and stops being this control.
            bound = BINDING["AND"] + 1
            return (
                f"{left} {self.operator} "
                f"{lower.render_within(bound)} AND {upper.render_within(bound)}"
            )
        return f"{left} {self.operator} {self.right.render_within(self.binding, right=True)}"


@dataclasses.dataclass(frozen=True, slots=True)
class FunctionCall(Expression):
    name: str = ""
    arguments: tuple[Expression, ...] = ()
    distinct: bool = False

    def children(self) -> tuple[Expression, ...]:
        return self.arguments

    def render(self) -> str:
        inner = ", ".join(a.render() for a in self.arguments) or ("*" if not self.arguments else "")
        prefix = "DISTINCT " if self.distinct else ""
        return f"{self.name}({prefix}{inner})"


@dataclasses.dataclass(frozen=True, slots=True)
class ListExpression(Expression):
    """A parenthesised set, as in ``IN ('GBP', 'USD')``."""

    items: tuple[Expression, ...] = ()

    def children(self) -> tuple[Expression, ...]:
        return self.items

    def render(self) -> str:
        return "(" + ", ".join(item.render() for item in self.items) + ")"


# -- assertions ------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Assertion(Node):
    """What a control claims. Subclasses are the catalogue."""

    def render(self) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        """Plain language, for the reader who does not write PQL."""
        raise NotImplementedError

    @property
    def considers_unknowns(self) -> bool:
        """Whether an UNKNOWN row value can arise for this assertion.

        Only row predicates can produce one. Saying "a row whose value cannot be
        determined counts as a violation" underneath a row-count check is noise,
        and noise in a generated description is what teaches people to stop
        reading generated descriptions.
        """
        return False

    @property
    def is_structural(self) -> bool:
        """Whether "no violations" is implied rather than worth stating.

        A declared unique key that tolerated duplicates would not be a key, so
        spelling the threshold out adds nothing.
        """
        return False

    def render_head(self, target: str) -> str:
        """``<target> <assertion>``, as it is written after CHECK.

        An assertion about a column folds the column into the target —
        ``CHECK positions.lei IS NOT NULL``, not ``CHECK positions positions.lei
        IS NOT NULL``. Rendering the two independently and concatenating them
        emits the dataset twice, which does not parse; getting this wrong breaks
        round-tripping, and a formatter whose output will not re-read is worse
        than no formatter.
        """
        return f"{quote_dataset(target)} {self.render()}"

    def render_selected(self) -> str:
        """The assertion after a selector, which has already named the subject.

        ``EVERY ATTRIBUTE WHERE is_cde IS NOT NULL`` — not ``… is_cde ATTRIBUTE
        IS NOT NULL``. Rendering the placeholder here would emit text that does
        not re-parse, which for a formatter is the same as being wrong.
        """
        return self.render()


#: Comparison predicates, whose operator *is* the symbol.
COMPARISONS: frozenset[str] = frozenset({"=", "<>", ">", ">=", "<", "<="})

#: How a comparison reads aloud. "greater than" beats ">" in a sentence meant
#: for somebody who has never seen the control.
_COMPARISON_WORDS: dict[str, str] = {
    "=": "equal to",
    "<>": "different from",
    ">": "greater than",
    ">=": "at least",
    "<": "less than",
    "<=": "at most",
}


@dataclasses.dataclass(frozen=True, slots=True)
class PredicateAssertion(Assertion):
    """A per-row claim: ``IS NOT NULL``, ``IN``, ``MATCHES``, ``BETWEEN``…

    One node rather than a class per predicate, because the catalogue is a list
    of operators over the same shape — subject, optional argument, optional
    upper bound — and thirty near-identical classes would obscure that.
    """

    subject: Expression = dataclasses.field(default_factory=lambda: Literal(value=None))
    operator: str = "is_not_null"
    argument: Expression | None = None
    upper: Expression | None = None
    negated: bool = False

    def render(self) -> str:
        return f"{self.subject.render()} {self._clause()}"

    def render_head(self, target: str) -> str:
        if isinstance(self.subject, ColumnRef) and self.subject.dataset in (target, ""):
            return f"{quote_dataset(target)}.{self.subject.name} {self._clause()}"
        return f"{quote_dataset(target)} {self.render()}"

    def render_selected(self) -> str:
        return self._clause()

    def describe(self) -> str:
        return f"every {_bare(self.subject)} {self._plain()}"

    @property
    def considers_unknowns(self) -> bool:
        return True

    def _clause(self) -> str:
        argument = self.argument.render() if self.argument else ""
        upper = self.upper.render() if self.upper else ""
        negation = "NOT " if self.negated else ""
        if self.operator in COMPARISONS:
            return f"{self.operator} {argument}"
        return {
            "is_null": "IS NULL",
            "is_not_null": "IS NOT NULL",
            "is_unique": "IS UNIQUE",
            "in": f"{negation}IN {argument}",
            "in_codelist": f"IN CODELIST {argument}",
            "between": f"{negation}BETWEEN {argument} AND {upper}",
            "matches": f"{negation}MATCHES {argument}",
            "is_valid": f"IS VALID {argument}",
            "has_length_between": f"HAS LENGTH BETWEEN {argument} AND {upper}",
            "has_format": f"HAS FORMAT {argument}",
            "is_of_type": f"IS OF TYPE {argument}",
        }[self.operator]

    def _plain(self) -> str:
        argument = self.argument.render() if self.argument else ""
        upper = self.upper.render() if self.upper else ""
        negation = "not " if self.negated else ""
        if self.operator in COMPARISONS:
            return f"is {_COMPARISON_WORDS[self.operator]} {argument}"
        return {
            "is_null": "is empty",
            "is_not_null": "has a value",
            "is_unique": "is different from every other",
            "in": f"is not one of {argument}" if self.negated else f"is one of {argument}",
            "in_codelist": f"is a code in the {_unquoted(argument)} list",
            "between": f"is {negation}between {argument} and {upper}",
            "matches": (
                f"does not look like {argument}" if self.negated else f"looks like {argument}"
            ),
            "is_valid": f"is a well-formed {_unquoted(argument)}",
            "has_length_between": f"is between {argument} and {upper} characters long",
            "has_format": f"is written in the {_unquoted(argument)} format",
            "is_of_type": f"holds a {_unquoted(argument)}",
        }[self.operator]


@dataclasses.dataclass(frozen=True, slots=True)
class UniqueKeyAssertion(Assertion):
    """``HAS UNIQUE KEY (a, b, c)`` — the declared grain, made enforceable."""

    columns: tuple[ColumnRef, ...] = ()

    def render(self) -> str:
        return f"HAS UNIQUE KEY ({', '.join(c.render() for c in self.columns)})"

    def describe(self) -> str:
        names = ", ".join(c.name for c in self.columns)
        return f"there is at most one row for each combination of {names}"

    @property
    def is_structural(self) -> bool:
        return True


@dataclasses.dataclass(frozen=True, slots=True)
class RowCountAssertion(Assertion):
    minimum: int | None = None
    maximum: int | None = None

    def render(self) -> str:
        if self.minimum is not None and self.maximum is not None:
            return f"HAS ROW COUNT BETWEEN {self.minimum} AND {self.maximum}"
        if self.minimum is not None:
            return f"HAS ROW COUNT AT LEAST {self.minimum}"
        return f"HAS ROW COUNT AT MOST {self.maximum}"

    def describe(self) -> str:
        if self.minimum is not None and self.maximum is not None:
            return f"the row count is between {self.minimum:,} and {self.maximum:,}"
        if self.minimum is not None:
            return f"there are at least {self.minimum:,} rows"
        return f"there are at most {self.maximum or 0:,} rows"

    @property
    def is_structural(self) -> bool:
        return True


@dataclasses.dataclass(frozen=True, slots=True)
class DelegateAssertion(Assertion):
    """``USING DELEGATE 'acme.settlement_cycle' (market = 'US')`` — a registered check.

    A delegate is Python a bank wrote, registered under a name, vetted before it
    is imported, and hashed into the evidence of every run. It *measures*: it
    returns how many rows (or findings) it scanned and how many violate. The
    threshold, the verdict and the evidence stay here, in the deterministic
    engine, exactly as for every other assertion (``prama.delegates``).

    The name may pin a version, ``'acme.settlement_cycle@2'``; a host whose
    installed delegate is another version refuses rather than running it.
    """

    delegate: str = ""
    parameters: tuple[tuple[str, Literal], ...] = ()

    def render(self) -> str:
        text = f"USING DELEGATE {Literal(value=self.delegate).render()}"
        if self.parameters:
            text += " (" + ", ".join(f"{k} = {v.render()}" for k, v in self.parameters) + ")"
        return text

    def describe(self) -> str:
        said = f"the registered check {self.delegate} finds no violations"
        if self.parameters:
            said += " (" + ", ".join(f"{k} {v.render()}" for k, v in self.parameters) + ")"
        return said

    def arguments(self) -> dict[str, Any]:
        return {name: literal.value for name, literal in self.parameters}


@dataclasses.dataclass(frozen=True, slots=True)
class ReferenceAssertion(Assertion):
    """``a.x REFERENCES b.y`` — referential integrity across datasets."""

    column: ColumnRef = dataclasses.field(default_factory=ColumnRef)
    target_dataset: str = ""
    target_column: str = ""

    def render(self) -> str:
        return f"{self.column.render()} REFERENCES {self.target_dataset}.{self.target_column}"

    def render_head(self, target: str) -> str:
        return (
            f"{quote_dataset(target)}.{self.column.name} REFERENCES "
            f"{quote_dataset(self.target_dataset)}.{self.target_column}"
        )

    def describe(self) -> str:
        return f"every {self.column.name} exists in {self.target_dataset}.{self.target_column}"

    @property
    def considers_unknowns(self) -> bool:
        return True


@dataclasses.dataclass(frozen=True, slots=True)
class FreshnessAssertion(Assertion):
    """``IS FRESH WITHIN 30 MINUTES OF '06:30' CALENDAR 'TARGET2'``."""

    tolerance_minutes: int = 0
    due_time: str = ""
    calendar: str = ""
    column: ColumnRef | None = None

    def render(self) -> str:
        parts = [f"IS FRESH WITHIN {self.tolerance_minutes} MINUTES"]
        if self.due_time:
            parts.append(f"OF '{self.due_time}'")
        if self.calendar:
            parts.append(f"CALENDAR '{self.calendar}'")
        return " ".join(parts)

    @property
    def is_structural(self) -> bool:
        return True

    def describe(self) -> str:
        window = (
            "on time"
            if self.tolerance_minutes == 0
            else f"within {self.tolerance_minutes} minutes of {self.due_time}"
        )
        calendar = f" on {self.calendar} business days" if self.calendar else ""
        return f"the data arrives {window}{calendar}"


@dataclasses.dataclass(frozen=True, slots=True)
class ExpressionAssertion(Assertion):
    """``SATISFIES <expression>`` — an arbitrary per-row condition."""

    condition: Expression = dataclasses.field(default_factory=lambda: Literal(value=True))
    #: ``pql`` or ``excel``. Which surface the author wrote it in, so the
    #: control renders back as what they typed rather than as a translation
    #: they would not recognise — ``parse(render(x)) == x`` has to hold for
    #: both syntaxes, and it cannot if the Excel form is lost on the way in.
    source_syntax: str = "pql"
    #: The formula as written, when the syntax is Excel.
    source: str = ""

    def render(self) -> str:
        if self.source_syntax == "excel" and self.source:
            escaped = self.source.replace("'", "''")
            return f"SATISFIES EXCEL '{escaped}'"
        return f"SATISFIES {self.condition.render()}"

    def describe(self) -> str:
        if self.source_syntax == "excel" and self.source:
            return f"every row satisfies the formula {self.source}"
        return f"every row satisfies {self.condition.render()}"

    @property
    def considers_unknowns(self) -> bool:
        return True


@dataclasses.dataclass(frozen=True, slots=True)
class FunctionalDependencyAssertion(Assertion):
    """``SATISFIES a DETERMINES b`` — one value of *a* implies one of *b*."""

    determinant: tuple[ColumnRef, ...] = ()
    dependent: tuple[ColumnRef, ...] = ()

    def render(self) -> str:
        left = ", ".join(c.render() for c in self.determinant)
        right = ", ".join(c.render() for c in self.dependent)
        return f"SATISFIES {left} DETERMINES {right}"

    def describe(self) -> str:
        left = " and ".join(c.name for c in self.determinant)
        right = " and ".join(c.name for c in self.dependent)
        return f"each {left} always has the same {right}"

    @property
    def is_structural(self) -> bool:
        return True


# -- controls --------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Segmentation(Node):
    """``FOR EACH legal_entity HAVING COUNT(*) > 100``.

    The clause that keeps a finding from being averaged away. Segmenting by
    entity turns "0.4% of LEIs are missing" into "every LEI is missing for one
    entity", which is a different conversation.
    """

    columns: tuple[ColumnRef, ...] = ()
    having: Expression | None = None

    def render(self) -> str:
        clause = f"FOR EACH {', '.join(c.render() for c in self.columns)}"
        return f"{clause} HAVING {self.having.render()}" if self.having else clause


@dataclasses.dataclass(frozen=True, slots=True)
class Threshold(Node):
    """When the metric is bad enough to fail.

    Defaults to zero violations for structural assertions, which is the only
    honest default: a declared unique key that tolerates duplicates was not a
    key. Anything looser has to be written down, and then it is a decision
    somebody made rather than one nobody noticed.
    """

    #: ``rows``, ``rate``, ``percent``, ``amount``, ``sigma``.
    unit: str = "rows"
    value: float = 0.0
    currency: str = ""
    comparator: str = "<="

    def render(self) -> str:
        if self.unit == "rows":
            return f"AT MOST {exact(self.value)} ROWS"
        if self.unit in ("rate", "percent"):
            return f"BELOW {exact(self.value, scale=100)}%"
        if self.unit == "amount":
            return f"WITHIN {exact(self.value)} {self.currency}".rstrip()
        return f"WITHIN {exact(self.value)} SIGMA"

    def describe(self) -> str:
        if self.unit == "rows":
            return (
                "no violations are allowed"
                if self.value == 0
                else f"up to {exact(self.value)} violating rows are tolerated"
            )
        if self.unit in ("rate", "percent"):
            return f"up to {exact(self.value, scale=100)}% of rows may violate it"
        if self.unit == "amount":
            return f"differences up to {exact(self.value)} {self.currency} are tolerated".rstrip()
        return f"a departure beyond {exact(self.value)} standard deviations is a failure"

    @property
    def is_strict(self) -> bool:
        return self.value == 0


@dataclasses.dataclass(frozen=True, slots=True)
class EvidenceSpec(Node):
    level: EvidenceLevel = EvidenceLevel.SAMPLES
    max_samples: int = 50

    def render(self) -> str:
        if self.level is EvidenceLevel.SAMPLES:
            return f"EVIDENCE samples ({self.max_samples})"
        return f"EVIDENCE {self.level.value}"


@dataclasses.dataclass(frozen=True, slots=True)
class Selector(Node):
    """Which assets a control applies to, named by meaning rather than by name.

    The most consequential feature in the language, and the reason a bank's
    control estate can be declared rather than typed: "every attribute that is
    a CDE in Credit Risk" is a sentence somebody can approve, and it stays true
    as the estate changes. A hundred hand-written controls do not.
    """

    #: ``attribute`` — matched on declared metadata; ``concept`` — matched on
    #: the concept property an attribute is mapped to.
    kind: str = "attribute"
    where: Expression | None = None
    concept: str = ""
    concept_property: str = ""

    def render(self) -> str:
        if self.kind == "concept":
            return f"CONCEPT {self.concept}.{self.concept_property}"
        clause = "EVERY ATTRIBUTE"
        return f"{clause} WHERE {self.where.render()}" if self.where else clause

    def describe(self) -> str:
        if self.kind == "concept":
            return f"every attribute mapped to {self.concept}.{self.concept_property}"
        if self.where is None:
            return "every declared attribute"
        return f"every attribute where {self.where.render()}"


@dataclasses.dataclass(frozen=True, slots=True)
class Control(Node):
    """One CHECK, with everything that qualifies it."""

    target: str = ""
    assertion: Assertion = dataclasses.field(default_factory=Assertion)
    name: str = ""
    where: Expression | None = None
    segmentation: Segmentation | None = None
    threshold: Threshold = dataclasses.field(default_factory=Threshold)
    severity: Severity = Severity.MAJOR
    dimensions: tuple[Dimension, ...] = ()
    #: Why this control exists, in the business's own words. Not a comment: the
    #: most useful sentence on the screen when it fires at three in the morning.
    because: str = ""
    unknown_policy: UnknownPolicy = UnknownPolicy.VIOLATION
    evidence: EvidenceSpec = dataclasses.field(default_factory=EvidenceSpec)
    on_fail: FailAction = FailAction.ALERT
    owner: str = ""
    schedule: str = ""
    #: Set when the control was written against a selector rather than a named
    #: dataset. Cleared by expansion — an expanded control is a concrete
    #: control and must render as one, or its text will not re-parse.
    selector: Selector | None = None
    #: The selector that produced this control, once expanded. Provenance
    #: rather than structure: an expanded control has to be able to say which
    #: declaration it came from, which is the difference between a generated
    #: estate somebody owns and one nobody recognises.
    #:
    #: Excluded from equality for the same reason as ``position``. It is not
    #: part of what the control does, and including it would break
    #: ``parse(render(x)) == x`` for every expanded control — the property that
    #: makes an estate exportable and reviewable.
    derived_from: str = dataclasses.field(default="", compare=False)

    @property
    def is_template(self) -> bool:
        """Whether this control still needs expanding before it can run."""
        return self.selector is not None

    def render(self) -> str:
        """Back to PQL, canonically. The formatter's output, and diff-stable."""
        if self.selector is not None:
            lines = [f"CHECK {self.selector.render()} {self.assertion.render_selected()}"]
        else:
            lines = [f"CHECK {self.assertion.render_head(self.target)}"]
        if self.where is not None:
            lines.append(f"  WHERE {self.where.render()}")
        if self.segmentation is not None:
            lines.append(f"  {self.segmentation.render()}")
        if not self.threshold.is_strict or self.threshold.unit != "rows":
            lines.append(f"  {self.threshold.render()}")
        lines.append(f"  SEVERITY {self.severity.value}")
        if self.dimensions:
            lines.append(f"  DIMENSION {', '.join(d.value for d in self.dimensions)}")
        if self.unknown_policy is UnknownPolicy.PASS:
            lines.append("  TREAT UNKNOWN AS PASS")
        if self.evidence.level is not EvidenceLevel.SAMPLES or self.evidence.max_samples != 50:
            lines.append(f"  {self.evidence.render()}")
        if self.on_fail is not FailAction.ALERT:
            lines.append(f"  ON FAIL {self.on_fail.value}")
        if self.owner:
            lines.append(f"  OWNER '{self.owner}'")
        if self.because:
            escaped = self.because.replace("'", "''")
            lines.append(f"  BECAUSE '{escaped}'")
        return "\n".join(lines)

    def describe(self) -> str:
        """The control as a sentence, for somebody who does not read PQL.

        Generated rather than written, so it cannot drift from what the control
        actually does — which is the failure mode of every hand-written control
        description in every catalogue.
        """
        if self.selector is not None:
            sentence = [f"For {self.selector.describe()}, {self.assertion.describe()}"]
        else:
            sentence = [f"In {self.target}, {self.assertion.describe()}"]
        if self.where is not None:
            sentence.append(f", considering only rows where {self.where.render()}")
        if self.segmentation is not None:
            names = " and ".join(c.name for c in self.segmentation.columns)
            sentence.append(f", checked separately for each {names}")
        sentence.append(".")
        if not (self.assertion.is_structural and self.threshold.is_strict):
            sentence.append(f" {self.threshold.describe().capitalize()}.")
        sentence.append(f" A failure is {self.severity.value}")
        if self.assertion.considers_unknowns and self.unknown_policy is UnknownPolicy.PASS:
            # Only the departure from the default is worth a sentence. Stating
            # the default on every control trains people to skip the line, and
            # then they skip it on the one control where it was changed.
            sentence.append(", and a row whose value cannot be determined is allowed to pass")
        sentence.append(".")
        if self.because:
            # The declaration is written by a person and rarely ends in a full
            # stop; the sentence around it should still finish properly.
            reason = self.because.rstrip()
            if not reason.endswith((".", "!", "?")):
                reason += "."
            sentence.append(f" This exists because: {reason}")
        return "".join(sentence)


@dataclasses.dataclass(frozen=True, slots=True)
class Suite(Node):
    """A named group of controls, approved and versioned together."""

    name: str = ""
    controls: tuple[Control, ...] = ()

    def render(self) -> str:
        inner = "\n\n".join(_indent(c.render()) for c in self.controls)
        return f"SUITE {self.name} {{\n{inner}\n}}"


@dataclasses.dataclass(frozen=True, slots=True)
class Program(Node):
    """Everything one piece of PQL text declares."""

    controls: tuple[Control, ...] = ()
    suites: tuple[Suite, ...] = ()

    @property
    def all_controls(self) -> tuple[Control, ...]:
        return self.controls + tuple(c for s in self.suites for c in s.controls)

    def render(self) -> str:
        return "\n\n".join(
            [*(c.render() for c in self.controls), *(s.render() for s in self.suites)]
        )


def _indent(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())


def _bare(expression: Expression) -> str:
    """A column without its dataset, for a sentence that already named it."""
    if isinstance(expression, ColumnRef):
        return expression.name
    if isinstance(expression, SelectedAttribute):
        # The sentence has already said which attributes; naming the
        # placeholder again would read as shouting.
        return "one"
    return expression.render()


def _unquoted(rendered: str) -> str:
    """Drop the quotes from a named thing, for prose.

    ``is a code in the iso4217 list`` reads; ``is a code in 'iso4217'`` reads
    like a program. The quotes belong in the PQL, not in the sentence.
    """
    return rendered[1:-1] if rendered.startswith("'") and rendered.endswith("'") else rendered
