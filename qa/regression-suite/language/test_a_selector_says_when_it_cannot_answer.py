"""A selector that cannot answer says so, instead of matching nothing.

QA round 4, `PQL-366`, `PQL-369`, `PQL-372`, `PQL-373`. Selector expansion
(`CHECK EVERY ATTRIBUTE WHERE …`) resolved every kind of internal trouble to
"no match" — the exact inverse of the failure this round found in the rest of
the language stack, where trouble escaped as a bare Python exception. Here it
vanished.

`PQL-366` is the highest-value case in the cluster and the reason this file
exists. `facts.get(name)` returns `None` for a typo, every comparison against
`None` is `False`, so `WHERE is_cdee` expanded to **zero controls with no
diagnostic anywhere**. What that produces is not an error, it is *an estate that
looks covered and covers nothing* — the declaration is on the record, the
coverage report counts it, and no control was ever generated.

`PQL-369`: `tags = 'pii'` compares a list with a string. Never equal, so it
matched nothing — while `tags IN ('pii')`, the same intent spelled differently,
matched. And `criticality > 3` raised `TypeError`, which was caught and turned
into `False`, so a string-versus-integer comparison read as "no attribute is
that critical".

`PQL-372`/`PQL-373` are one defect seen twice. `_truth` required the value to be
literally `True`; `_is_true`, used by the `NOT` branch, also accepted the string
`"true"`. So for a flag that arrived from a warehouse as text, `WHERE is_cde`
and `WHERE NOT is_cde` **both excluded the attribute** — it was in neither half
of a partition, which is the one thing a partition may not do.

**What a careless version of this test would assert.** `len(expanded) == 0` for
the typo — which passes today, for the wrong reason. A silent failure and a
correct "matched nothing" are indistinguishable by count, and that
indistinguishability *is* the defect. Every assertion here is on a refusal, or
on the two halves of a partition summing to the whole.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.pql.expand import Attribute, AttributeCatalogue, Expander
from prama.pql.parser import parse_control

ESTATE = AttributeCatalogue(
    attributes=(
        Attribute(
            dataset="positions_eod",
            name="isin",
            is_cde=True,
            tags=("pii", "reference"),
            domain="settlement",
            criticality="high",
        ),
        Attribute(
            dataset="positions_eod",
            name="ccy",
            is_cde=False,
            domain="settlement",
            criticality="low",
        ),
    )
)


def expand(where: str, catalogue: AttributeCatalogue = ESTATE) -> list:
    control = parse_control(f"CHECK EVERY ATTRIBUTE WHERE {where} IS NOT NULL BECAUSE 'x'")
    return Expander(catalogue).expand(control)


# -- PQL-366: a typo is a refusal, not an empty estate ----------------------


def test_a_misspelled_fact_name_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        expand("is_cdee")

    assert "is_cdee" in str(caught.value), "the refusal does not name the unknown fact"
    assert caught.value.remedy


def test_the_refusal_suggests_the_name_that_was_meant() -> None:
    """A typo deserves the correction, not just the rejection.

    The available names are known exactly — the selector is evaluated against a
    fixed mapping — so there is no reason to make somebody diff two lists.
    """
    with pytest.raises(ValidationError) as caught:
        expand("is_cdee")
    assert "is_cde" in (caught.value.remedy or ""), f"no suggestion offered: {caught.value.remedy}"


def test_a_selector_that_genuinely_matches_nothing_is_still_allowed() -> None:
    """The counterfactual, and the distinction the whole file is about.

    A domain with no CDEs yet is a legitimate empty expansion. If the repair
    refused that too, it would have replaced a silent wrong answer with a loud
    wrong answer.
    """
    assert expand("domain = 'Nowhere'") == []


def test_a_correct_selector_still_expands() -> None:
    assert len(expand("is_cde")) == 1
    assert len(expand("domain = 'settlement'")) == 2


# -- PQL-369: a comparison that cannot be true says so ----------------------


def test_comparing_a_list_with_a_string_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        expand("tags = 'pii'")
    assert "IN" in (caught.value.remedy or ""), (
        "the refusal does not point at the spelling that works"
    )


def test_the_spelling_that_works_still_works() -> None:
    """`IN` is the intent `=` was reaching for, and must be untouched."""
    assert len(expand("tags IN ('pii')")) == 1


def test_an_unorderable_comparison_is_refused_rather_than_false() -> None:
    """`criticality` is text; `> 3` cannot be answered, and False is an answer."""
    with pytest.raises(ValidationError) as caught:
        expand("criticality > 3")
    assert "str" in str(caught.value) and "int" in str(caught.value), (
        f"the refusal does not say which types could not be ordered: {caught.value}"
    )


def test_an_orderable_comparison_still_evaluates() -> None:
    """The counterfactual: text against text is a real comparison."""
    assert len(expand("criticality = 'high'")) == 1


# -- PQL-372 / PQL-373: a predicate and its negation partition the estate ---


@pytest.mark.parametrize("stored", [True, "true", "True"], ids=["bool", "lower", "capitalised"])
def test_a_flag_and_its_negation_cover_every_attribute(stored: object) -> None:
    """The property, not the pair of behaviours.

    Asserting `WHERE is_cde` matches is half the story; the defect was that
    *both* halves excluded the same attribute. Stated as a partition, it cannot
    be satisfied by fixing one side.
    """
    catalogue = AttributeCatalogue(
        attributes=(
            Attribute(dataset="d", name="isin", is_cde=stored),  # type: ignore[arg-type]
            Attribute(dataset="d", name="ccy", is_cde=False),
        )
    )

    matched = len(expand("is_cde", catalogue))
    negated = len(expand("NOT is_cde", catalogue))

    assert matched + negated == 2, (
        f"is_cde stored as {stored!r} matched {matched} and NOT is_cde matched "
        f"{negated}, of 2 attributes. An attribute in neither half of a partition "
        "is excluded from a control whichever way the selector is written."
    )
    assert matched == 1, f"the attribute whose flag is {stored!r} was not recognised as a CDE"
