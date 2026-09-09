"""The Excel-familiar surface.

Two things are being tested and they are different. That the parser produces
the tree somebody meant — precedence, associativity, the operators a
spreadsheet has and PQL does not. And that the surface is *familiarity* rather
than *compatibility*: where Prama deliberately differs, it says so, and the
difference is the one documented rather than an accident.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql import ast, parse_control
from prama.pql.errors import PqlSyntaxError
from prama.pql.excel import PRECEDENCE, parse_formula
from prama.pql.functions import VOLATILE
from prama.pql.library import FUNCTIONS


def _render(formula: str) -> str:
    return parse_formula(formula).render()


class TestItParsesWhatPeopleWrite:
    @pytest.mark.parametrize(
        ("formula", "expected"),
        [
            ("=[a] > 0", "a > 0"),
            # The parentheses are PQL's own rendering, not something Excel
            # introduced: BinaryOp parenthesises a right operand of equal
            # binding so associativity survives a round trip.
            ("=[a] <> [b]", "a != (b)"),
            ("=[a] = [b]", "a = b"),
            ("=[a] >= 1 AND [b] <= 2", "a >= 1 AND b <= 2"),
            ("=NOT(ISBLANK([a]))", "NOT ISBLANK(a)"),
            ("=UPPER([a])", "UPPER(a)"),
        ],
    )
    def test_the_common_shapes(self, formula: str, expected: str) -> None:
        assert _render(formula) == expected

    def test_a_leading_equals_is_optional(self) -> None:
        """It is how a spreadsheet starts a formula and how a user will type
        it. Refusing it would be pedantry about the one habit this surface
        exists to accommodate."""
        assert _render("=[a] > 0") == _render("[a] > 0")

    def test_bare_identifiers_are_columns(self) -> None:
        assert _render("=quantity > 0") == _render("=[quantity] > 0")

    def test_a_semicolon_separates_arguments_too(self) -> None:
        """A European locale's Excel uses ``;``. A user pasting their own
        formula should not have to know Prama is not localised."""
        assert _render("=MIN([a]; [b])") == _render("=MIN([a], [b])")

    def test_doubled_quotes_are_an_escaped_quote(self) -> None:
        assert parse_formula('=[a] = "say ""hi"""').render().endswith("'say \"hi\"'")

    def test_true_and_false_are_literals_not_columns(self) -> None:
        parsed = parse_formula("=IF([a], TRUE, FALSE)")
        assert isinstance(parsed, ast.FunctionCall)
        assert all(isinstance(x, ast.Literal) for x in parsed.arguments[1:])


class TestPrecedenceAndAssociativity:
    def test_and_binds_looser_than_comparison(self) -> None:
        """``a > 0 AND b > 0`` must not parse as ``a > (0 AND b) > 0``."""
        assert _render("=[a] > 0 AND [b] > 0") == "a > 0 AND b > 0"

    def test_or_binds_looser_than_and(self) -> None:
        rendered = _render("=[a] AND [b] OR [c]")
        assert rendered == "a AND b OR c"

    def test_multiplication_binds_tighter_than_addition(self) -> None:
        assert _render("=[a] + [b] * [c]") == "a + b * c"

    def test_concatenation_binds_looser_than_arithmetic(self) -> None:
        """Excel puts ``&`` *below* arithmetic and above comparison. Copying
        SQL's ladder would silently reassociate every formula mixing them."""
        assert PRECEDENCE["&"] < PRECEDENCE["+"]
        assert PRECEDENCE["&"] > PRECEDENCE["="]

    def test_parentheses_win(self) -> None:
        assert _render("=([a] + [b]) * [c]") == "(a + b) * c"

    def test_unary_minus(self) -> None:
        assert _render("=-[a] < 0") == "-a < 0"


class TestItIsFamiliarityNotCompatibility:
    def test_an_unknown_function_names_the_ones_that_exist(self) -> None:
        """Every reader will try VLOOKUP. The refusal has to say what to do
        instead rather than merely saying no."""
        with pytest.raises(PqlSyntaxError) as caught:
            parse_formula("=VLOOKUP([a], [b], 2, FALSE)")
        assert "no function called VLOOKUP" in str(caught.value)
        assert "UPPER" in str(caught.value)

    @pytest.mark.parametrize("name", sorted(VOLATILE))
    def test_a_volatile_function_is_refused_with_the_reason(self, name: str) -> None:
        with pytest.raises(PqlSyntaxError, match="replay"):
            parse_formula(f"={name}() > 1")

    def test_exponentiation_is_refused_rather_than_approximated(self) -> None:
        """The engines disagree about precision and about what a fractional
        exponent of a negative number means, and a control has to mean one
        thing."""
        with pytest.raises(PqlSyntaxError, match="not supported"):
            parse_formula("=[a] ^ 2 > 4")

    def test_wrong_arity_is_caught_at_parse_time(self) -> None:
        with pytest.raises(PqlSyntaxError, match="exactly 1 argument"):
            parse_formula("=UPPER([a], [b])")

    def test_concatenation_becomes_the_catalogue_function(self) -> None:
        """So ``&`` inherits the same per-engine lowering and the same unknown
        rule rather than acquiring its own."""
        parsed = parse_formula('=[a] & "-" & [b]')
        assert isinstance(parsed, ast.FunctionCall)
        assert parsed.name == "CONCAT"

    def test_iferror_does_not_exist(self) -> None:
        """There are no error values to catch: a failed computation is UNKNOWN,
        and UNKNOWN is a violation rather than something to swallow."""
        assert FUNCTIONS.find("IFERROR") is None
        with pytest.raises(PqlSyntaxError):
            parse_formula("=IFERROR([a] / [b], 0)")


class TestBadInput:
    @pytest.mark.parametrize("formula", ["=", "=[a] +", "=([a]", "=[a] ) ", "=AND([a])", "=@#$"])
    def test_it_refuses_rather_than_guessing(self, formula: str) -> None:
        with pytest.raises(PqlSyntaxError):
            parse_formula(formula)

    def test_the_error_carries_the_formula(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            parse_formula("=UPPER(")
        assert "formula" in str(caught.value).lower()


class TestTheControlSurface:
    FORMULA = "=AND([quantity] > 0, [notional] = [quantity] * [price])"

    def _control(self) -> ast.Control:
        return parse_control(
            f"CHECK trades SATISFIES EXCEL '{self.FORMULA}' "
            "SEVERITY critical DIMENSION consistency BECAUSE 'derived from the trade'"
        )

    def test_it_round_trips(self) -> None:
        """``parse(render(x)) == x`` has to hold for both syntaxes, which is
        why the formula as written is kept on the assertion. Rendering it back
        as translated PQL would give the author a control they do not
        recognise."""
        control = self._control()
        assert parse_control(control.render()) == control

    def test_it_renders_as_what_was_typed(self) -> None:
        assert self.FORMULA in self._control().render()

    def test_it_explains_itself_as_a_formula(self) -> None:
        assert self.FORMULA in self._control().assertion.describe()

    def test_it_lowers_to_an_ordinary_plan(self) -> None:
        """No Excel IR and no Excel code path in the compiler — which is what
        keeps one control meaning one thing."""
        from prama.ir.resolve import resolved

        assert resolved(self._control()).plan_id.startswith("ir:sha256:")

    def test_it_pushes_down_to_sql(self) -> None:
        """The performance decision that matters. A formula evaluated row by
        row in Python instead of pushed into the engine is two orders of
        magnitude slower on the scans this runs against."""
        from prama.backend import compile_for
        from prama.ir.resolve import resolved

        sql = compile_for(resolved(self._control()), "duckdb", table="trades").metric_query
        assert '"quantity" > 0' in sql
        assert "AND" in sql

    def test_the_marker_is_required(self) -> None:
        """``=`` means equality in a formula and nothing in PQL. A parser
        sniffing between the two would occasionally guess wrong on a control
        that then means something its author did not write."""
        with pytest.raises(PqlSyntaxError):
            parse_control(
                "CHECK trades SATISFIES EXCEL =[a] > 0 "
                "SEVERITY major DIMENSION validity BECAUSE 'x'"
            )
