"""Charts, and the four ways a chart lies.

Every test here is written against a specific way a plausible-looking chart
says something untrue: an unmeasured value drawn as zero, a truncated axis that
does not say it is truncated, a label that is not escaped, and a picture that
exists only as a picture.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.report import charts
from prama.report.palette import PRINT, SCREEN, UNVERIFIED_GREY


class TestNoDataIsNotZero:
    """The first and worst of them.

    A zero-height bar and an absent bar look identical and mean opposite
    things; a flat line along the bottom of a sparkline says "the value was
    zero" when nothing was measured at all.
    """

    def test_an_empty_sparkline_says_not_examined(self) -> None:
        svg = charts.sparkline([], label="match rate")
        assert "not examined" in svg
        assert "polyline" not in svg
        assert "absence of observation" in svg

    def test_an_unmeasured_score_is_not_drawn_as_zero(self) -> None:
        svg = charts.score_ring(None, label="completeness")
        assert "0.0%" not in svg
        assert "not examined" in svg
        assert "not the same as a score of zero" in svg

    def test_a_measured_zero_is_drawn_as_zero(self) -> None:
        """The counterfactual: a real zero must still render as a real zero."""
        svg = charts.score_ring(0.0, label="completeness")
        assert "0.0%" in svg
        assert "not examined" not in svg

    def test_an_unmeasured_bar_is_not_a_zero_length_bar(self) -> None:
        svg = charts.bars(
            [
                charts.Series("accuracy", (0.99,), dimension="accuracy"),
                charts.Series("timeliness", (), dimension="timeliness"),
            ],
            label="dimensions",
        )
        assert "not examined" in svg
        assert "timeliness not examined" in svg

    def test_an_empty_distribution_says_so(self) -> None:
        assert "not examined" in charts.distribution([], label="breaks")
        assert "not examined" in charts.distribution([("a", 0), ("b", 0)], label="breaks")


class TestAxisHonesty:
    def test_a_zero_based_axis_is_used_when_it_shows_anything(self) -> None:
        axis = charts.Axis.for_values([10.0, 60.0, 100.0])
        assert axis.minimum == 0.0
        assert not axis.is_truncated

    def test_a_narrow_high_series_is_truncated_rather_than_flattened(self) -> None:
        """99.7%-100% on a zero axis is a flat line at the top: honest and
        useless. Truncation is the right call — saying so is what makes it
        defensible."""
        axis = charts.Axis.for_values([0.997, 0.998, 1.0])
        assert axis.is_truncated

    def test_a_truncated_sparkline_states_the_truncation(self) -> None:
        svg = charts.sparkline([0.997, 0.998, 1.0], label="pass rate")
        assert "not from zero" in svg

    def test_an_untruncated_sparkline_makes_no_such_claim(self) -> None:
        svg = charts.sparkline([0.1, 0.5, 1.0], label="pass rate")
        assert "not from zero" not in svg

    def test_a_flat_series_does_not_divide_by_zero(self) -> None:
        svg = charts.sparkline([5.0, 5.0, 5.0], label="rows")
        assert "polyline" in svg

    def test_a_single_point_is_not_given_a_trend(self) -> None:
        """A line through one point invents a direction the data lacks."""
        svg = charts.sparkline([0.99], label="pass rate")
        assert "polyline" not in svg
        assert "no trend" in svg


class TestEscaping:
    """Labels are dataset names, imported from dbt and read out of catalogues.
    They are user data and they reach the markup."""

    @pytest.mark.parametrize(
        "hostile",
        ["<script>alert(1)</script>", "a & b", 'quote" here', "</title><img src=x>"],
    )
    def test_a_hostile_label_cannot_break_out(self, hostile: str) -> None:
        svg = charts.sparkline([1.0, 2.0], label=hostile)
        assert "<script>" not in svg
        assert "<img" not in svg
        assert svg.count("<title>") == 1

    def test_a_hostile_bucket_name_cannot_break_out(self) -> None:
        svg = charts.distribution([("<b>x</b>", 3)], label="breaks")
        assert "<b>" not in svg

    def test_the_table_alternative_escapes_too(self) -> None:
        table = charts.table_alternative([("<b>x</b>", "1")], caption="c")
        assert "<b>" not in table


class TestAccessibility:
    def test_every_chart_carries_a_title_and_a_description(self) -> None:
        for svg in (
            charts.sparkline([1.0, 2.0], label="a"),
            charts.sparkline([], label="a"),
            charts.score_ring(0.5, label="a"),
            charts.score_ring(None, label="a"),
            charts.bars([charts.Series("a", (1.0,))], label="a"),
            charts.distribution([("x", 1)], label="a"),
        ):
            assert 'role="img"' in svg
            assert "<title>" in svg and "<desc>" in svg
            assert "aria-label=" in svg

    def test_the_description_carries_the_numbers_not_just_the_shape(self) -> None:
        """A description saying "a line chart" is worse than nothing: it tells
        a screen-reader user a chart exists and refuses to say what it shows."""
        svg = charts.sparkline([0.5, 0.9], label="pass rate")
        assert "0.5" in svg and "0.9" in svg

    def test_a_bar_chart_names_every_series_in_text(self) -> None:
        svg = charts.bars([charts.Series("uniqueness", (0.4,), dimension="uniqueness")], label="d")
        assert "uniqueness" in svg


class TestPalette:
    def test_unverified_grey_is_used_only_for_the_unexamined(self) -> None:
        healthy = charts.bars([charts.Series("a", (1.0,), dimension="accuracy")], label="d")
        assert UNVERIFIED_GREY not in healthy

        stale = charts.bars([charts.Series("a", (1.0,), unverified=True)], label="d")
        assert UNVERIFIED_GREY in stale

    def test_the_print_palette_emits_no_css_variables(self) -> None:
        """A ``var(--x)`` in a PDF renders as nothing — silently, as a blank
        chart that looks like a chart with no data."""
        svg = charts.bars(
            [charts.Series("a", (1.0,), dimension="accuracy")], label="d", palette=PRINT
        )
        assert "var(--" not in svg
        assert "#00B3A4" in svg

    def test_the_screen_palette_keeps_a_literal_fallback(self) -> None:
        """So an SVG saved, emailed or embedded outside the console still has
        its colours."""
        svg = charts.bars(
            [charts.Series("a", (1.0,), dimension="accuracy")], label="d", palette=SCREEN
        )
        assert "var(--dim-accuracy, #00B3A4)" in svg

    def test_a_dimension_keeps_its_hue_wherever_it_appears(self) -> None:
        """The palette's one promise: the same hue means the same dimension on
        every chart, so a reader learns it once."""
        first = charts.bars([charts.Series("x", (1.0,), dimension="validity")], label="a")
        second = charts.distribution([("x", 1)], label="b", dimension="validity")
        assert "dim-validity" in first
        assert "dim-validity" in second


class TestDeterminism:
    def test_the_same_input_produces_the_same_bytes(self) -> None:
        """What makes every assertion above worth writing, and what a canvas
        cannot offer."""
        values = [0.1, 0.55, 0.9, 0.42]
        assert charts.sparkline(values, label="a") == charts.sparkline(values, label="a")

    def test_coordinates_are_rounded_rather_than_full_precision(self) -> None:
        svg = charts.sparkline([1 / 3, 2 / 3, 1.0], label="a")
        assert "0.3333333" not in svg
