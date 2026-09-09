"""The language service.

One module answers the editor and the LSP server, so these tests are the only
place the answers are checked. Everything here is about the three things a
language service is tempted to do and must not: invent a name, guess a
position, and let "not checked" render as "checked and fine".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql.analysis import KIND_FIELD, KIND_FUNCTION, LanguageService
from prama.pql.types import Catalogue

CATALOGUE = Catalogue.of(
    positions={"notional": "DECIMAL(18,2)", "account_id": "VARCHAR(32)", "as_of_date": "DATE"},
    trades={"trade_id": "VARCHAR(32)", "quantity": "INTEGER"},
)

GOOD = "CHECK positions.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"


@pytest.fixture
def service() -> LanguageService:
    return LanguageService(CATALOGUE)


class TestDiagnostics:
    def test_a_clean_control_produces_none(self, service: LanguageService) -> None:
        assert service.diagnostics(GOOD) == []

    def test_empty_text_is_not_an_error(self, service: LanguageService) -> None:
        """An editor asks on every keystroke, including the first."""
        assert service.diagnostics("") == []
        assert service.diagnostics("   \n  ") == []

    def test_a_typo_names_the_column_and_the_nearest_real_one(
        self, service: LanguageService
    ) -> None:
        [found] = service.diagnostics(GOOD.replace("notional", "notionl"))
        assert "no column called notionl" in found.message
        assert "notional" in found.remedy
        assert found.level == "error"

    def test_it_reports_every_problem_not_just_the_first(self, service: LanguageService) -> None:
        """Fixing a control one message at a time gives somebody a chance to
        give up at every round trip."""
        text = (
            "CHECK positions.nope IS NOT NULL SEVERITY major DIMENSION completeness "
            "BECAUSE 'a'\n"
            "CHECK trades.alsonope IS NOT NULL SEVERITY major DIMENSION completeness "
            "BECAUSE 'b'"
        )
        assert len(service.diagnostics(text)) == 2

    def test_an_undeclared_dataset_is_unchecked_not_clean(self, service: LanguageService) -> None:
        """The distinction the level exists for. "Nobody has looked" and "we
        looked and it is fine" must not render the same."""
        found = service.diagnostics(
            "CHECK ledger.amount IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'"
        )
        assert found
        assert all(d.level == "unchecked" for d in found)
        assert all(d.severity == 3 for d in found)

    def test_an_undeclared_dataset_is_said_once_not_once_per_control(
        self, service: LanguageService
    ) -> None:
        """One fact about the estate, not one per control. Repeating it buries
        the findings that really are about a control."""
        text = "\n".join(
            f"CHECK ledger.amount IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'c{n}'"
            for n in range(4)
        )
        assert len(service.diagnostics(text)) == 1

    def test_a_syntax_error_is_one_diagnostic_with_no_control(
        self, service: LanguageService
    ) -> None:
        [found] = service.diagnostics("CHECK ???")
        assert found.level == "error"
        assert found.control == ""


class TestPositionsAreNeverGuessed:
    def test_a_located_finding_reports_its_place(self, service: LanguageService) -> None:
        [found] = service.diagnostics(GOOD.replace("notional", "notionl"))
        assert found.has_position
        assert found.line == 1
        assert found.column > 1

    def test_an_unlocated_finding_says_so_rather_than_claiming_line_one(
        self, service: LanguageService
    ) -> None:
        """Line 1 column 1 is a real place. A diagnostic that claims it sends
        the reader to the top of the file to look for a problem that is
        somewhere else."""
        from prama.pql.analysis import Diagnostic

        unlocated = Diagnostic(message="something", line=0, column=0)
        assert not unlocated.has_position

    def test_severity_keeps_unchecked_below_a_warning(self) -> None:
        """A warning says "this is probably wrong"; unchecked says "nobody has
        looked". Rendering the second as the first trains people to dismiss
        both."""
        from prama.pql.analysis import Diagnostic

        assert Diagnostic("x", level="error").severity == 1
        assert Diagnostic("x", level="warning").severity == 2
        assert Diagnostic("x", level="unchecked").severity == 3


class TestCompletionNeverInventsAName:
    def test_after_a_dot_it_offers_that_datasets_columns(self, service: LanguageService) -> None:
        labels = [c.label for c in service.completions("CHECK positions.", 1, 17)]
        assert labels == ["notional", "account_id", "as_of_date"]

    def test_it_does_not_offer_another_datasets_columns(self, service: LanguageService) -> None:
        """A control naming the wrong dataset's column parses, type-checks
        against nothing, and fails at compile time with a message about SQL."""
        labels = [c.label for c in service.completions("CHECK positions.", 1, 17)]
        assert "trade_id" not in labels

    def test_after_a_dot_on_an_undeclared_dataset_it_offers_nothing(
        self, service: LanguageService
    ) -> None:
        """Not "every column we know". A dataset nobody declared has no columns
        to offer, and inventing some is how a control names a column that has
        never existed."""
        assert service.completions("CHECK ledger.", 1, 14) == []

    def test_a_prefix_narrows_the_columns(self, service: LanguageService) -> None:
        labels = [c.label for c in service.completions("CHECK positions.ac", 1, 19)]
        assert labels == ["account_id"]

    def test_columns_come_back_with_their_declared_type(self, service: LanguageService) -> None:
        [item] = service.completions("CHECK positions.no", 1, 19)
        assert item.kind == KIND_FIELD
        assert "DECIMAL(18,2)" in item.detail

    def test_bare_words_offer_datasets_functions_and_keywords(
        self, service: LanguageService
    ) -> None:
        labels = [c.label for c in service.completions("CHECK ", 1, 7)]
        assert "positions" in labels
        assert "trades" in labels

    def test_a_function_prefix_finds_the_function(self, service: LanguageService) -> None:
        items = service.completions("CHECK ROU", 1, 10)
        [rounded] = [c for c in items if c.label == "ROUND"]
        assert rounded.kind == KIND_FUNCTION
        assert rounded.documentation


class TestHover:
    def test_a_column_reports_its_declared_type(self, service: LanguageService) -> None:
        hover = service.hover(GOOD, 1, 20)
        assert hover.title == "positions.notional"
        assert "DECIMAL(18,2)" in hover.body

    def test_the_dataset_half_of_a_name_answers_about_the_dataset(
        self, service: LanguageService
    ) -> None:
        """Returning the whole dotted name either way answers the column
        question both times, which is wrong in the half where somebody is
        checking a dataset name."""
        assert service.hover(GOOD, 1, 10).title == "positions"
        assert service.hover(GOOD, 1, 20).title == "positions.notional"

    def test_an_unknown_column_names_the_real_ones(self, service: LanguageService) -> None:
        hover = service.hover("CHECK positions.nope IS NULL", 1, 18)
        assert "Not a declared column" in hover.body
        assert "notional" in hover.body

    def test_an_undeclared_dataset_says_nothing_has_been_checked(
        self, service: LanguageService
    ) -> None:
        hover = service.hover("CHECK ledger.amount IS NULL", 1, 8)
        assert "is not declared" in hover.body
        assert "will not be verified" in hover.body

    def test_a_function_reports_where_it_is_not_available(self, service: LanguageService) -> None:
        """The thing somebody needs before writing it into a control that has
        to run on two engines."""
        hover = service.hover("ROUND(x, 2)", 1, 3)
        assert "ROUND" in hover.title
        assert "Not available on sqlite" in hover.body

    def test_nothing_under_the_cursor_is_an_empty_hover(self, service: LanguageService) -> None:
        """Not an empty box. A tooltip that follows the cursor with nothing in
        it is worse than none."""
        assert service.hover(GOOD, 1, 6).is_empty or service.hover(GOOD, 1, 6).title == "CHECK"
        assert service.hover("   ", 1, 2).is_empty


class TestItStopsShortOfTheIr:
    def test_the_language_layer_does_not_import_the_lowerer(self) -> None:
        """Explaining a control means lowering it, and the language layer may
        not depend on the lowerer — ``tests/architecture`` enforces that and
        caught this file importing ``prama.ir`` for exactly that convenience.
        Asserted here too, at the place somebody would add it back."""
        import ast
        import pathlib

        import prama.pql.analysis as module

        tree = ast.parse(pathlib.Path(module.__file__).read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(m.startswith("prama.ir") or m.startswith("prama.backend") for m in imported)


class TestWithoutACatalogue:
    def test_everything_is_unchecked_rather_than_clean(self) -> None:
        """A server started with no catalogue must not report a clean file. It
        has checked nothing, and that is the more useful of the two facts."""
        found = LanguageService().diagnostics(GOOD)
        assert found
        assert all(d.level == "unchecked" for d in found)

    def test_completion_still_offers_functions_and_keywords(self) -> None:
        labels = [c.label for c in LanguageService().completions("CHECK ROU", 1, 10)]
        assert "ROUND" in labels
