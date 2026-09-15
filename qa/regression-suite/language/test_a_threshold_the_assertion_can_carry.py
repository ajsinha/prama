"""A threshold the assertion cannot express is refused, not reinterpreted.

QA round 4, `PQL-150` (P1) and `PQL-151`. `Lowerer._threshold` special-cased
`rate`/`percent` and sent everything else to a `violating_rows` count.

`PQL-150`. `CHECK t.a IS NOT NULL WITHIN 100 USD` became
`Threshold(metric="violating_rows", value=100.0)` — the currency dropped, the
number kept. *"Within 100 US dollars of error"* and *"at most 100 bad rows"* are
not the same control, and nothing anywhere said so. **This is the kind of wrong
that reads correct in a diff**: the figure the author typed is right there in
the plan.

`PQL-151`. A rate threshold needs a `violating_rows` metric to be a rate *of*
anything, and a row-count assertion emits only `scanned_rows`. The triage
expected this to produce `INDETERMINATE`. Measured, it does not: the verdict
comes from the row-count path and is **identical with the clause and without
it**. The clause is silently discarded. That is worse than indeterminate,
because the author believes they constrained something and the run agrees with
them.

The parser's own module docstring already listed *"a threshold on an assertion
that has no rate"* among the things it refuses at authoring time. It did not.

**The first attempt at this repair was wrong, and the way it was wrong is the
useful part.** It asked whether the emitted metrics contained `violating_rows`.
They do not for `unique_key` or `functional_dependency` either — but
`backend/execute.py` *derives* one from the distinct counts for both. So the
check refused two legitimate assertion kinds, and three generated-equivalence
tests caught it. The emitted metrics were the wrong thing to ask; the answer
lives in two files and had to be named in one.

**What a careless version of this test would assert.** `threshold.value == 100`
for the currency case — which passes today, because the number survives; only
the meaning is wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.ir.lower import Lowerer
from prama.ir.model import KINDS_WITHOUT_VIOLATIONS
from prama.pql.parser import parse_control


def lower(pql: str):
    return Lowerer().control(parse_control(pql))


# -- PQL-150: a currency is not a row count ---------------------------------


def test_a_monetary_threshold_is_refused_rather_than_counted_as_rows() -> None:
    with pytest.raises(ValidationError) as caught:
        lower("CHECK t.a IS NOT NULL WITHIN 100 USD BECAUSE 'x'")

    message = str(caught.value)
    assert "USD" in message, f"the refusal does not name the currency: {message}"
    assert caught.value.remedy


def test_a_bare_number_is_still_a_row_count() -> None:
    """The counterfactual, and the behaviour that was always right.

    `WITHIN 100` with no unit reasonably means a hundred rows. Refusing every
    `amount` threshold would have taken the common spelling away with the
    broken one.
    """
    plan = lower("CHECK t.a IS NOT NULL WITHIN 100 BECAUSE 'x'")
    assert plan.threshold.value == 100.0
    assert plan.threshold.metric == "violating_rows"
    assert plan.threshold.relative_to == ""


# -- PQL-151: a rate needs something to be a rate of ------------------------


def test_a_rate_on_a_row_count_assertion_is_refused() -> None:
    with pytest.raises(ValidationError) as caught:
        lower("CHECK p HAS ROW COUNT AT LEAST 100 BELOW 2% BECAUSE 'x'")
    assert "rate" in str(caught.value).lower()
    assert caught.value.remedy


def test_the_same_assertion_without_a_rate_still_lowers() -> None:
    """The control. Refusing every row-count assertion would satisfy the above."""
    plan = lower("CHECK p HAS ROW COUNT AT LEAST 100 BECAUSE 'x'")
    assert plan.assertion_kind == "row_count"
    assert [m.name for m in plan.metrics] == ["scanned_rows"]


@pytest.mark.parametrize(
    "pql",
    [
        "CHECK t.a IS NOT NULL BELOW 2% BECAUSE 'x'",
        "CHECK t HAS UNIQUE KEY (a, b) BELOW 2% BECAUSE 'x'",
        "CHECK t SATISFIES account_id DETERMINES legal_entity_id BELOW 2% BECAUSE 'x'",
    ],
    ids=["predicate", "unique-key", "functional-dependency"],
)
def test_a_rate_is_still_allowed_where_violations_exist(pql: str) -> None:
    """The counterfactual that the first attempt at this repair failed.

    `unique_key` and `functional_dependency` emit no `violating_rows` either —
    `backend/execute.py` derives one. A check that looked only at the emitted
    metrics refused both, and three generated-equivalence tests caught it.
    """
    plan = lower(pql)
    assert plan.threshold.relative_to == "scanned_rows"


def test_the_set_of_kinds_without_violations_is_true() -> None:
    """The constant is a claim about the pipeline, so it is checked against it.

    `KINDS_WITHOUT_VIOLATIONS` is exactly the assertion kinds for which no
    `violating_rows` exists anywhere — not emitted by the lowerer, not derived
    by the executor. Written as a frozen set it would be a list somebody has to
    remember to update; asserted against what the pipeline actually produces, it
    cannot quietly become false.
    """
    from prama.backend.execute import _derive as derive_metrics

    samples = {
        "predicate": "CHECK t.a IS NOT NULL BECAUSE 'x'",
        "unique_key": "CHECK t HAS UNIQUE KEY (a, b) BECAUSE 'x'",
        "functional_dependency": (
            "CHECK t SATISFIES account_id DETERMINES legal_entity_id BECAUSE 'x'"
        ),
        "row_count": "CHECK t HAS ROW COUNT AT LEAST 1 BECAUSE 'x'",
    }

    without: set[str] = set()
    for kind, pql in samples.items():
        plan = lower(pql)
        assert plan.assertion_kind == kind, f"{pql!r} lowered to {plan.assertion_kind!r}"
        emitted = {m.name for m in plan.metrics}
        # Plausible counts for every metric the plan asks for, so derivation has
        # something to work from.
        metrics = dict.fromkeys(emitted, 4.0) | {"scanned_rows": 10.0}
        derived = set(derive_metrics(plan, dict(metrics)))
        if "violating_rows" not in (emitted | derived):
            without.add(kind)

    assert without == set(KINDS_WITHOUT_VIOLATIONS), (
        f"the pipeline produces no violating_rows for {sorted(without)}, and "
        f"KINDS_WITHOUT_VIOLATIONS says {sorted(KINDS_WITHOUT_VIOLATIONS)}"
    )


def test_the_generator_only_emits_thresholds_that_lower() -> None:
    """The generator chose assertion and threshold independently.

    It emitted `HAS ROW COUNT … BELOW n%` — the exact combination `PQL-151` is
    about — and the equivalence suite had been exercising it for as long as it
    has existed. It now consults the same constant the lowerer does, so the two
    cannot drift apart.
    """
    from prama.backend.generate import ControlGenerator

    for generated in ControlGenerator().many(300):
        lower(generated.pql)
