"""Turning PQL text into tokens.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql.errors import PqlSyntaxError
from prama.pql.tokens import TokenKind, tokenise


def kinds(source: str) -> list[TokenKind]:
    return [t.kind for t in tokenise(source)[:-1]]


def texts(source: str) -> list[str]:
    return [t.text for t in tokenise(source)[:-1]]


class TestKeywordsAreRecognisedNotReserved:
    def test_a_keyword_is_a_keyword(self) -> None:
        assert tokenise("CHECK")[0].kind is TokenKind.KEYWORD

    def test_keywords_are_case_insensitive(self) -> None:
        # People write these by hand, and a control that fails because somebody
        # typed "check" would be an unkind thing to ship.
        assert tokenise("check")[0].is_keyword("CHECK")
        assert tokenise("ChEcK")[0].is_keyword("check")

    def test_a_column_may_be_spelled_like_a_keyword(self) -> None:
        # Real banking columns are named severity, source, check_digit and on.
        # A language that reserved those would be rejected on its first dataset.
        assert texts("severity_score check_digit rate_of_return") == [
            "severity_score",
            "check_digit",
            "rate_of_return",
        ]

    def test_a_name_needing_protection_can_be_quoted(self) -> None:
        token = tokenise('"risk positions"')[0]
        assert token.kind is TokenKind.IDENTIFIER
        assert token.value == "risk positions"

    def test_a_quote_inside_a_quoted_name_is_doubled(self) -> None:
        assert tokenise('"say ""what"""')[0].value == 'say "what"'


class TestMultiWordKeywordsStaySeparate:
    def test_is_not_null_is_three_tokens(self) -> None:
        # Gluing them would make "IS NOT something-else" point the caret at the
        # whole phrase rather than at the word that was wrong.
        assert texts("IS NOT NULL") == ["IS", "NOT", "NULL"]

    def test_for_each_is_two_tokens(self) -> None:
        assert texts("FOR EACH") == ["FOR", "EACH"]


class TestLiterals:
    def test_text_is_delimited_by_single_quotes(self) -> None:
        token = tokenise("'CDE for FRTB'")[0]
        assert token.kind is TokenKind.STRING
        assert token.value == "CDE for FRTB"

    def test_a_quote_inside_text_is_doubled(self) -> None:
        assert tokenise("'O''Brien Ltd'")[0].value == "O'Brien Ltd"

    def test_numbers_carry_their_percent(self) -> None:
        # BELOW 0.1% and BELOW 0.1 % mean the same thing to a reader, so they
        # must to the parser.
        assert texts("0.1% 5 1e6 12.75") == ["0.1%", "5", "1e6", "12.75"]

    def test_a_parameter_names_the_run_context(self) -> None:
        token = tokenise("$business_date")[0]
        assert token.kind is TokenKind.PARAMETER
        assert token.value == "business_date"


class TestPatternsAgainstDivision:
    def test_a_pattern_after_matches_is_a_pattern(self) -> None:
        assert kinds("MATCHES /^[A-Z]{2}[0-9]{10}$/") == [
            TokenKind.KEYWORD,
            TokenKind.REGEX,
        ]

    def test_a_slash_after_a_value_is_division(self) -> None:
        # Getting this wrong swallows the rest of the line into a "pattern" and
        # reports an error a long way from the real one.
        assert kinds("failed / total") == [
            TokenKind.IDENTIFIER,
            TokenKind.OPERATOR,
            TokenKind.IDENTIFIER,
        ]

    def test_a_slash_after_a_number_is_division(self) -> None:
        assert kinds("100 / 3") == [TokenKind.NUMBER, TokenKind.OPERATOR, TokenKind.NUMBER]

    def test_a_slash_after_a_bracket_is_division(self) -> None:
        assert kinds("(a + b) / 2")[-2:] == [TokenKind.OPERATOR, TokenKind.NUMBER]

    def test_a_pattern_may_contain_an_escaped_slash(self) -> None:
        assert tokenise(r"MATCHES /a\/b/")[1].value == r"a\/b"


class TestComments:
    def test_a_line_comment_runs_to_the_end_of_the_line(self) -> None:
        assert texts("CHECK -- ignored\nSUITE") == ["CHECK", "SUITE"]

    def test_a_block_comment_is_skipped(self) -> None:
        assert texts("CHECK /* why not */ SUITE") == ["CHECK", "SUITE"]

    def test_a_block_comment_may_span_lines(self) -> None:
        assert texts("CHECK /* a\nb\nc */ SUITE") == ["CHECK", "SUITE"]


class TestPositions:
    def test_every_token_knows_where_it_is(self) -> None:
        tokens = tokenise("CHECK t\n  IS NULL")
        assert (tokens[0].position.line, tokens[0].position.column) == (1, 1)
        assert (tokens[2].position.line, tokens[2].position.column) == (2, 3)

    def test_a_position_spans_the_whole_token(self) -> None:
        assert tokenise("SEVERITY")[0].position.length == len("SEVERITY")


class TestErrorsReadLikeAdvice:
    """These are read by data owners, not only by engineers."""

    def test_unterminated_text_says_how_to_close_it(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            tokenise("BECAUSE 'unclosed")
        assert "never closed" in str(caught.value)
        assert "O''Brien" in caught.value.remedy

    def test_unterminated_pattern_shows_the_shape_of_one(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            tokenise("MATCHES /^abc")
        assert "[0-9]{10}" in caught.value.remedy

    def test_an_unclosed_comment_is_caught_where_it_opened(self) -> None:
        # Not at the end of the file, which is where the scanner noticed.
        with pytest.raises(PqlSyntaxError) as caught:
            tokenise("CHECK /* open\nand more\nand more")
        assert caught.value.position.line == 1

    def test_a_stray_character_suggests_quoting(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            tokenise("CHECK t.a #= 1")
        assert "quote the name" in caught.value.remedy

    def test_the_rendered_error_puts_a_caret_under_the_problem(self) -> None:
        with pytest.raises(PqlSyntaxError) as caught:
            tokenise("CHECK t.a #= 1")
        rendered = caught.value.render()
        lines = rendered.splitlines()
        caret = next(line for line in lines if line.strip().startswith("^"))
        source = next(line for line in lines if "CHECK t.a" in line)
        assert source.index("#") == caret.index("^")

    def test_a_long_line_is_windowed_around_the_error(self) -> None:
        # Truncating from the left would hide whichever end the mistake is at.
        padding = "a" * 200
        with pytest.raises(PqlSyntaxError) as caught:
            tokenise(f"CHECK t WHERE {padding} #= 1")
        excerpt = caught.value.render()
        assert "…" in excerpt
        assert len(max(excerpt.splitlines(), key=len)) < 200
