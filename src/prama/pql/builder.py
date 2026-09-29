"""The no-code rule builder.

Prama is for business owners, not DBAs, and this is where that claim is tested:
a person who will never write PQL answers a handful of questions and gets a
control. The three things that make it honest rather than a toy:

* **It builds the AST, not a string.** The output is rendered by the same
  ``render()`` every other part of the product uses, so a control built here is
  indistinguishable from one typed in the studio.
* **It shows the PQL.** Always, never behind a toggle. A builder that hides its
  output produces controls nobody can review, and a control nobody reviews is a
  control nobody trusts at three in the morning.
* **It proves the round trip before offering the result.** ``parse(render(c))``
  must equal ``c``. If it does not, that is a defect in this module and it is
  reported as one — never emitted as PQL that will fail to re-read later, in
  somebody else's file, for no visible reason.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.core.errors import ValidationError
from prama.pql import parse_control
from prama.pql.ast import (
    ColumnRef,
    Control,
    Dimension,
    FreshnessAssertion,
    ListExpression,
    Literal,
    PredicateAssertion,
    ReferenceAssertion,
    RowCountAssertion,
    Severity,
    Threshold,
    UniqueKeyAssertion,
    UnknownPolicy,
)


@dataclasses.dataclass(frozen=True, slots=True)
class Question:
    """One thing the builder knows how to ask.

    The label is the sentence a business owner recognises. The fields are what
    that sentence needs, and nothing else is shown — a form that displays every
    input for every rule is how a no-code builder becomes harder than the
    language it replaces.
    """

    key: str
    label: str
    #: Which inputs this rule needs: ``column``, ``columns``, ``values``,
    #: ``pattern``, ``bounds``, ``counts``, ``reference``, ``freshness``.
    needs: tuple[str, ...]
    dimension: Dimension
    #: Why this rule is worth having, in one line, for the reader choosing.
    rationale: str = ""


QUESTIONS: tuple[Question, ...] = (
    Question(
        "not_null",
        "Every row must have a value in this column",
        ("column",),
        Dimension.COMPLETENESS,
        "The commonest defect there is, and the one that quietly breaks every sum.",
    ),
    Question(
        "in_list",
        "The value must be one of a fixed list",
        ("column", "values"),
        Dimension.VALIDITY,
        "For statuses, currencies and codes. Catches a new value nobody agreed to.",
    ),
    Question(
        "matches",
        "The value must match a pattern",
        ("column", "pattern"),
        Dimension.VALIDITY,
        "For identifiers with a shape — an ISIN, an account number, a postcode.",
    ),
    Question(
        "between",
        "The value must fall between two numbers",
        ("column", "bounds"),
        Dimension.VALIDITY,
        "For rates, weights and percentages that have a meaningful range.",
    ),
    Question(
        "unique_key",
        "No two rows may share these columns",
        ("columns",),
        Dimension.UNIQUENESS,
        "The declared grain, made enforceable. Catches duplicated deliveries.",
    ),
    Question(
        "row_count",
        "The number of rows must stay in a range",
        ("counts",),
        Dimension.COMPLETENESS,
        "Catches a truncated file, whose every surviving row is perfectly valid.",
    ),
    Question(
        "references",
        "Every value must exist in another dataset",
        ("column", "reference"),
        Dimension.INTEGRITY,
        "Referential integrity. Catches orphans a join would silently drop.",
    ),
    Question(
        "fresh",
        "The data must arrive on time",
        ("freshness",),
        Dimension.TIMELINESS,
        "Lateness is a defect nothing about the data itself reveals.",
    ),
)

QUESTIONS_BY_KEY: dict[str, Question] = {q.key: q for q in QUESTIONS}


def _column(dataset: str, name: str, *, what: str) -> ColumnRef:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError(
            f"this rule needs {what}",
            remedy="Name the column the rule is about.",
        )
    return ColumnRef(name=cleaned, dataset=dataset)


def _values(text: str) -> ListExpression:
    items = [part.strip() for part in text.split(",") if part.strip()]
    if not items:
        raise ValidationError(
            "a list rule needs at least one permitted value",
            remedy="List them comma-separated — for example: NEW, SETTLED, CANCELLED.",
        )
    if len(items) != len(set(items)):
        # Not fatal, but it is always a mistake and it makes the rendered
        # control read as though somebody meant something by the repetition.
        raise ValidationError(
            "the permitted values repeat",
            remedy="Each value should appear once.",
            context={"values": items},
        )
    return ListExpression(items=tuple(Literal(value=v, literal_type="text") for v in items))


def _number(text: str, *, what: str) -> float:
    try:
        return float(text.strip())
    except ValueError:
        raise ValidationError(
            f"{what} is not a number: {text.strip()!r}",
            remedy="Enter a plain number, without units or thousands separators.",
        ) from None


def build(
    *,
    dataset: str,
    rule: str,
    severity: str = "major",
    because: str = "",
    column: str = "",
    columns: str = "",
    values: str = "",
    pattern: str = "",
    lower: str = "",
    upper: str = "",
    minimum: str = "",
    maximum: str = "",
    reference_dataset: str = "",
    reference_column: str = "",
    tolerance_minutes: str = "0",
    due_time: str = "",
    calendar: str = "",
    tolerated_percent: str = "",
    unknown_is_violation: bool = True,
) -> Control:
    """Assemble a control from the answers.

    Raises :class:`ValidationError` with a remedy for anything the answers
    cannot support. Refusing here, with a sentence, beats emitting a control
    that parses and means something nobody asked for.
    """
    question = QUESTIONS_BY_KEY.get(rule)
    if question is None:
        raise ValidationError(
            f"unknown rule {rule!r}",
            remedy="Choose one of: " + ", ".join(QUESTIONS_BY_KEY),
        )
    if not dataset.strip():
        raise ValidationError(
            "a control needs a dataset", remedy="Choose the dataset the rule is about."
        )
    if not because.strip():
        # The one field the builder will not let you skip. It is what the alert
        # quotes at three in the morning, and a control with no reason is one
        # nobody can decide about when it fires.
        raise ValidationError(
            "a control needs a reason",
            remedy=(
                "Say why this rule exists, in the business's own words. It is what the "
                "alert quotes when the control fires, and the difference between an "
                "alert somebody can act on and one they cannot."
            ),
        )

    assertion: Any
    if rule == "not_null":
        assertion = PredicateAssertion(
            subject=_column(dataset, column, what="a column"), operator="is_not_null"
        )
    elif rule == "in_list":
        assertion = PredicateAssertion(
            subject=_column(dataset, column, what="a column"),
            operator="in",
            argument=_values(values),
        )
    elif rule == "matches":
        if not pattern.strip():
            raise ValidationError(
                "a pattern rule needs a pattern",
                remedy="Write it as a regular expression — for example ^[A-Z]{2}[0-9]{9}[0-9]$.",
            )
        assertion = PredicateAssertion(
            subject=_column(dataset, column, what="a column"),
            operator="matches",
            argument=Literal(value=pattern.strip(), literal_type="pattern"),
        )
    elif rule == "between":
        low = _number(lower, what="the lower bound")
        high = _number(upper, what="the upper bound")
        if low > high:
            raise ValidationError(
                f"the lower bound {low:g} is above the upper bound {high:g}",
                remedy=(
                    "Swap them. As written this rule can never pass, and a control that "
                    "cannot pass fires on every row for ever."
                ),
            )
        assertion = PredicateAssertion(
            subject=_column(dataset, column, what="a column"),
            operator="between",
            argument=Literal(value=low, literal_type="number"),
            upper=Literal(value=high, literal_type="number"),
        )
    elif rule == "unique_key":
        names = [part.strip() for part in columns.split(",") if part.strip()]
        if not names:
            raise ValidationError(
                "a uniqueness rule needs at least one column",
                remedy="Name the columns that together identify one row.",
            )
        assertion = UniqueKeyAssertion(
            columns=tuple(ColumnRef(name=name, dataset="") for name in names)
        )
    elif rule == "row_count":
        low_count = int(_number(minimum, what="the minimum")) if minimum.strip() else None
        high_count = int(_number(maximum, what="the maximum")) if maximum.strip() else None
        if low_count is None and high_count is None:
            raise ValidationError(
                "a row-count rule needs a minimum, a maximum, or both",
                remedy="State what a normal delivery looks like.",
            )
        if low_count is not None and high_count is not None and low_count > high_count:
            raise ValidationError(
                f"the minimum {low_count:,} is above the maximum {high_count:,}",
                remedy="Swap them; as written this rule can never pass.",
            )
        assertion = RowCountAssertion(minimum=low_count, maximum=high_count)
    elif rule == "references":
        if not reference_dataset.strip() or not reference_column.strip():
            raise ValidationError(
                "a reference rule needs the dataset and column it points at",
                remedy="Choose the dataset that holds the authoritative values.",
            )
        # Qualified with its own dataset, which is what the parser produces
        # when it reads this back. Leaving it bare renders identically and
        # compares unequal, and the round-trip check below catches it — which
        # is exactly what that check is for.
        assertion = ReferenceAssertion(
            column=_column(dataset, column, what="a column"),
            target_dataset=reference_dataset.strip(),
            target_column=reference_column.strip(),
        )
    else:  # fresh
        assertion = FreshnessAssertion(
            tolerance_minutes=int(_number(tolerance_minutes or "0", what="the tolerance")),
            due_time=due_time.strip(),
            calendar=calendar.strip(),
        )

    threshold = Threshold()
    if tolerated_percent.strip():
        fraction = _number(tolerated_percent, what="the tolerated percentage") / 100
        if not 0 <= fraction <= 1:
            raise ValidationError(
                f"a tolerance of {tolerated_percent.strip()}% is not a percentage",
                remedy="Enter a value between 0 and 100.",
            )
        # The comparator is left at the language's default. ``BELOW n%``
        # renders without one and re-reads as ``<=``, so building a ``<``
        # here produces a control that renders identically and compares
        # unequal — caught by the round-trip check below, which is what it is
        # for. The builder emits canonical PQL; it does not get to invent a
        # form the language cannot express.
        threshold = Threshold(unit="rate", value=fraction)

    return Control(
        target=dataset,
        assertion=assertion,
        threshold=threshold,
        severity=Severity(severity),
        dimensions=(question.dimension,),
        because=because.strip(),
        unknown_policy=(UnknownPolicy.VIOLATION if unknown_is_violation else UnknownPolicy.PASS),
    )


def render_and_verify(control: Control) -> str:
    """Render to PQL, and refuse to hand back anything that will not re-read.

    ``parse(render(c)) == c`` is the property the whole language rests on, and
    the builder is the one place that can break it silently: a person who never
    reads PQL would not notice that what was generated is not what re-parses.
    A failure here is a defect in this module, and it says so — rather than
    surfacing days later as a file that will not load.
    """
    text = control.render()
    try:
        reparsed = parse_control(text)
    except Exception as exc:
        raise ValidationError(
            "the builder produced PQL that does not parse",
            remedy=(
                "This is a defect in Prama, not in what you entered. Please report it "
                "with the text below."
            ),
            context={"pql": text, "error": str(exc)},
        ) from exc
    if reparsed != control:
        raise ValidationError(
            "the builder produced PQL that does not read back as what was built",
            remedy=(
                "This is a defect in Prama, not in what you entered. Please report it "
                "with the text below."
            ),
            context={"pql": text},
        )
    return text
