"""A bound imported from somewhere else must mean what it meant there.

QA round 2, `CTR-029`, `CTR-031`, `IMP-028`, `IMP-046`, `CLS-114`, `CLS-127`.
Four importers that quietly changed the control they were translating, and two
holes in the gate that decides whether a validator may run at all.

Every one of the four moves in the same direction: the imported control accepts
data the original refused, or refuses data the original accepted, and nothing
says so.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pathlib

from prama.classify.plugins import scan_source
from prama.contract.quality import controls_from
from prama.importers.great_expectations import _tolerance
from prama.importers.soda import _threshold


def _quality(block: dict) -> object:
    return controls_from({"schema": [{"name": "orders", "quality": [block]}]}, dataset="orders")


class TestAStrictBoundIsNotAnInclusiveOne:
    """`CTR-029`. `mustBeLessThan: 1200000` means a maximum of 1,199,999.

    `HAS ROW COUNT BETWEEN` is inclusive on both ends, so copying the number
    across accepted a row count the contract forbids. `_threshold` in the same
    module already made this adjustment — one file, right and wrong about the
    same word.
    """

    def test_a_strict_maximum_loses_one(self) -> None:
        imported = _quality(
            {"rule": "rowCount", "mustBeGreaterOrEqualTo": 900000, "mustBeLessThan": 1200000}
        )
        assert "BETWEEN 900000 AND 1199999" in imported.controls[0]

    def test_an_inclusive_maximum_is_unchanged(self) -> None:
        """The counterfactual: the adjustment must apply to one spelling only."""
        imported = _quality(
            {
                "rule": "rowCount",
                "mustBeGreaterOrEqualTo": 900000,
                "mustBeLessOrEqualTo": 1200000,
            }
        )
        assert "BETWEEN 900000 AND 1200000" in imported.controls[0]


class TestAFreshnessWindowKeepsItsUnit:
    """`CTR-031`. The unit was assumed to be days whatever the contract said.

    `4` with a unit of hours became `WITHIN 4 day` — a window twenty-four times
    longer than stated, in the direction that lets stale data pass.
    """

    def test_hours_stay_hours(self) -> None:
        imported = _quality({"rule": "freshness", "mustBeLessThan": 4, "unit": "hours"})
        assert "WITHIN 4 hour" in imported.controls[0]

    def test_days_are_still_the_default(self) -> None:
        imported = _quality({"rule": "freshness", "mustBeLessThan": 4})
        assert "WITHIN 4 day" in imported.controls[0]

    def test_a_unit_pql_cannot_express_is_refused(self) -> None:
        """Refused, not approximated.

        A freshness control wrong by a factor is worse than one that was never
        generated, because the first is believed.
        """
        imported = _quality({"rule": "freshness", "mustBeLessThan": 4, "unit": "weeks"})
        assert not imported.controls
        assert imported.refused


class TestSodaComparisonsKeepTheirStrictness:
    """`IMP-028`. `< 5` failures means at most four."""

    def test_a_strict_count_loses_one(self) -> None:
        assert _threshold("<", "5", percent=False) == "AT MOST 4 ROWS"

    def test_an_inclusive_count_is_unchanged(self) -> None:
        assert _threshold("<=", "5", percent=False) == "AT MOST 5 ROWS"

    def test_a_strict_rate_is_refused_rather_than_widened(self) -> None:
        """A strict bound on a rate has no representable predecessor.

        The contract importer refuses the same shape for the same reason, and
        the two agreeing is worth more than either being clever.
        """
        assert _threshold("<", "1", percent=True) is None


class TestAnUnreadableToleranceIsReported:
    """`IMP-046`. An unparseable `mostly` silently became no tolerance at all.

    Stricter is not safer: the imported control then fails on data the source
    suite accepted, and the first person to see it has no way to know the
    tolerance was lost in translation.
    """

    def test_it_produces_a_caveat(self) -> None:
        threshold, note = _tolerance("high")
        assert threshold == ""
        assert note, "an unreadable tolerance was discarded without a word"

    def test_a_readable_one_still_converts(self) -> None:
        threshold, note = _tolerance(0.99)
        assert threshold == "BELOW 1%"
        assert note

    def test_an_absent_one_is_not_an_error(self) -> None:
        """`mostly` is optional, and its absence is not a translation failure."""
        assert _tolerance(None) == ("", "")


class TestThePurityGateCannotBeSteppedAround:
    """`CLS-114`, `CLS-127`. Two ways past the gate that decides what may run."""

    def test_a_bare_dynamic_import_is_refused(self, tmp_path: pathlib.Path) -> None:
        """`importlib.import_module` was caught; the bare name was not.

        One extra import line stepped around it, which makes a gate that
        inconveniences the honest.
        """
        source = tmp_path / "sneaky.py"
        source.write_text('from importlib import import_module\nimport_module("socket")\n')
        assert scan_source(str(source))

    def test_the_attribute_spelling_is_still_refused(self, tmp_path: pathlib.Path) -> None:
        source = tmp_path / "plain.py"
        source.write_text('import importlib\nimportlib.import_module("socket")\n')
        assert scan_source(str(source))

    def test_an_ordinary_regex_is_not_refused(self, tmp_path: pathlib.Path) -> None:
        """The counterfactual, and the one my first fix broke.

        `compile` is in the builtin table because `compile()` runs generated
        code. `re.compile(...)` is an attribute call with the same name and is
        what every ordinary validator does — checking both tables for
        attributes refused every regex in the shipped set. The suite caught it
        immediately, which is the trade worth having lost.
        """
        source = tmp_path / "ordinary.py"
        source.write_text('import re\nPATTERN = re.compile(r"^[A-Z]{2}$")\n')
        assert scan_source(str(source)) == []

    def test_a_file_that_cannot_be_read_is_a_finding(self, tmp_path: pathlib.Path) -> None:
        """An unscannable file returned "nothing forbidden".

        This function is the pre-flight run *before* importing is acceptable,
        so an empty result and a clean scan were indistinguishable — and an
        empty result is exactly what a deliberately unreadable file produces.
        """
        source = tmp_path / "broken.py"
        source.write_text("def validator(:\n")
        found = scan_source(str(source))
        assert found
        assert "could not be scanned" in found[0][1]
