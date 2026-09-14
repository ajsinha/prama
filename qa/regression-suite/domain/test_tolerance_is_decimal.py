"""A break verdict must not depend on binary floating point.

QA round 4 triage, finding `Q-78`. `recon/classify.py` carries every amount as
`Decimal` — the matcher, the normaliser, the difference — and then:

    def _within_tolerance(self, difference: Decimal, magnitude: Decimal) -> bool:
        return self._tolerance.permits(float(difference), float(magnitude))

because `semantic/relationships.py::Tolerance` declares `absolute` and
`relative` as native `float`. The conversion happens at the exact instant the
break/no-break decision is made, and `permits` then computes
`relative * abs(magnitude)` in binary floating point.

**This is not a rounding nicety.** A one-basis-point tolerance on a position of
527,712.72 has an exact allowance of 52.771272. In float the same product is
52.771271999999996, so a difference of exactly the allowance — the boundary the
declaration draws — is reported as a **break**. An operations person is sent to
investigate a difference their own materiality rule permits.

The values below are not contrived: 1bp against a half-million-unit position is
an ordinary reconciliation, and the flip was found by sweeping realistic money
magnitudes rather than by choosing a number that misbehaves.

**What a careless version of this test would use.** `0.5`, `0.25`, `0.125` — any
allowance whose factors are exactly representable in binary. Those agree in both
arithmetics and pass before the fix and after it, proving nothing. So do round
magnitudes: `0.001 * 1_000_000` is exactly `1000.0` in float. The test needs a
product that binary floating point rounds *down*, because only then does an
exactly-on-tolerance difference cross the boundary.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.recon.classify import Classifier
from prama.semantic.relationships import Tolerance

#: (relative bound, magnitude, the exactly-on-tolerance difference). Every row
#: is a case where `float(rel) * float(mag)` is strictly below the exact product,
#: so the difference lands outside the allowance under float and inside it under
#: Decimal. Found by sweeping ordinary position sizes, not hand-picked.
ON_THE_BOUNDARY = [
    ("0.0001", "527712.72", "52.771272"),
    ("0.0001", "1053699.88", "105.369988"),
    ("0.0001", "1362497.14", "136.249714"),
    ("0.0001", "4616576.35", "461.657635"),
]

#: The careless choice, kept as a live check rather than a comment: these agree
#: in both arithmetics, so a fix that changed nothing would still pass here.
#: If this ever fails, the repair broke ordinary cases.
EXACTLY_REPRESENTABLE = [
    ("0.5", "100", "50"),
    ("0.25", "1000", "250"),
    ("0.125", "80000", "10000"),
]


@pytest.mark.parametrize("relative,magnitude,difference", ON_THE_BOUNDARY)
def test_a_difference_exactly_on_the_relative_allowance_is_not_a_break(
    relative: str, magnitude: str, difference: str
) -> None:
    """The declaration says "within 1bp"; a difference of exactly 1bp is within it.

    Driven through `Classifier`, not through `Tolerance.permits` directly. The
    first draft of this test constructed `Tolerance(relative=Decimal(...))` and
    called `permits` — and passed, because `Decimal * Decimal` is exact. It
    proved only that the arithmetic works when nobody converts, while the defect
    is a conversion in `_within_tolerance` that the test never reached. That is
    the `Q-75` shape: a test that goes around the code it is named for.
    """
    magnitude_d = Decimal(magnitude)
    difference_d = Decimal(difference)
    tolerance = Tolerance(relative=float(relative))  # as the dataclass declares it

    outcome = Classifier(tolerance).classify("k", magnitude_d, magnitude_d + difference_d)

    assert outcome is None, (
        f"a difference of exactly {difference} against a {relative} relative bound on "
        f"{magnitude} was classified {outcome.kind.value if outcome else '-'}. The exact "
        f"allowance is {Decimal(relative) * magnitude_d}; in binary floating point the "
        f"same product is {float(relative) * float(magnitude)!r}, which is below it — "
        "so the boundary the declaration draws falls on the wrong side of itself."
    )


@pytest.mark.parametrize("relative,magnitude,difference", EXACTLY_REPRESENTABLE)
def test_the_ordinary_case_is_still_not_a_break(
    relative: str, magnitude: str, difference: str
) -> None:
    """Values binary floating point represents exactly, which must not regress."""
    magnitude_d = Decimal(magnitude)
    outcome = Classifier(Tolerance(relative=float(relative))).classify(
        "k", magnitude_d, magnitude_d + Decimal(difference)
    )
    assert outcome is None


def test_a_difference_one_unit_above_the_allowance_is_still_a_break() -> None:
    """The boundary moved in one direction only.

    Without this, the whole file is satisfied by a `permits` that returns True
    unconditionally — which is the shape of fix this codebase has produced
    before, and which no assertion above would catch.
    """
    magnitude = Decimal("527712.72")
    allowance = Decimal("0.0001") * magnitude  # 52.771272 exactly
    classify = Classifier(Tolerance(relative=0.0001)).classify

    assert classify("k", magnitude, magnitude + allowance) is None
    assert classify("k", magnitude, magnitude + allowance + Decimal("0.01")) is not None, (
        "a difference above the exact allowance is within tolerance, so the bound "
        "no longer bounds anything"
    )


def test_the_absolute_bound_keeps_its_exactness_too() -> None:
    """`absolute` needs no multiplication, so it is the half that looks safe.

    It is not: the comparison still happens between whatever types reach it, and
    a `Decimal` difference compared against a `float` bound raises rather than
    coerces once both sides are exact. Asserted so the repair cannot fix the
    relative path and leave this one converting.
    """
    classify = Classifier(Tolerance(absolute=0.01)).classify
    base = Decimal("1000")
    assert classify("k", base, base + Decimal("0.01")) is None
    assert classify("k", base, base + Decimal("0.02")) is not None


def test_the_bounds_are_declared_exact() -> None:
    """Asserted on the type, so the conversion cannot return by another route.

    The behavioural tests above all pass if somebody keeps `float` bounds and
    rounds inside `permits`. That would fix these four magnitudes and leave the
    next one broken, because the defect is the representation, not the boundary.
    """
    import dataclasses

    fields = {f.name: f.type for f in dataclasses.fields(Tolerance)}
    for name in ("absolute", "relative"):
        annotation = str(fields[name])
        assert "float" not in annotation, (
            f"Tolerance.{name} is declared {annotation}; a money bound held as a "
            "binary float cannot represent the allowance a declaration states"
        )
        assert "Decimal" in annotation, f"Tolerance.{name} is declared {annotation}"
