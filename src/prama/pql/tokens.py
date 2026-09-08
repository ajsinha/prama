"""Turning PQL text into tokens.

Two decisions shape everything downstream.

**Keywords are recognised, not reserved.** ``account_id`` may be a column even
though ``ACCOUNT`` is not a keyword and ``COUNT`` is; a bank's columns are named
``severity``, ``source``, ``check_digit`` and ``on``, and a language that
forbade them would be rejected on its first real dataset. The lexer emits a
keyword token when the spelling matches and the parser accepts a keyword token
wherever an identifier is legal but no keyword can be.

**Multi-word keywords stay separate.** ``IS NOT NULL`` is three tokens, not one.
Gluing them in the lexer makes ``IS NOT`` followed by something else report an
error pointing at the whole phrase, when the reader needs the caret under the
word that was actually wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import re

from prama.pql.errors import Position, PqlSyntaxError


class TokenKind(enum.Enum):
    KEYWORD = "keyword"
    IDENTIFIER = "identifier"
    NUMBER = "number"
    STRING = "string"
    REGEX = "regex"
    PARAMETER = "parameter"
    OPERATOR = "operator"
    PUNCTUATION = "punctuation"
    END = "end"

    @property
    def is_value(self) -> bool:
        return self in (TokenKind.NUMBER, TokenKind.STRING, TokenKind.REGEX)


#: Every word the language recognises. Recognised, not reserved: see the module
#: docstring. Kept as one frozen set because a keyword's *category* is the
#: parser's business — the lexer only needs to know the spelling exists.
KEYWORDS: frozenset[str] = frozenset(
    [
        "IMPORT",
        "DEFINE",
        "AS",
        "SUITE",
        "CHECK",
        "MONITOR",
        "RECONCILE",
        "CONTRACT",
        "PACK",
        "IS",
        "NOT",
        "NULL",
        "UNIQUE",
        "IN",
        "CODELIST",
        "BETWEEN",
        "AND",
        "OR",
        "MATCHES",
        "HAS",
        "FORMAT",
        "LENGTH",
        "OF",
        "TYPE",
        "PRECISION",
        "SCALE",
        "VALID",
        "INCREASING",
        "DECREASING",
        "NON",
        "CALENDAR",
        "BUSINESS",
        "DAY",
        "DAYS",
        "DISTINCT",
        "COUNT",
        "RATE",
        "BELOW",
        "ABOVE",
        "ROW",
        "ROWS",
        "KEY",
        "FRESH",
        "WITHIN",
        "CONFORMS",
        "TO",
        "SCHEMA",
        "DUPLICATE",
        "PARTITIONS",
        "FOR",
        "EVERY",
        "SINCE",
        "TRAILER",
        "RECORD",
        "SATISFIES",
        "DETERMINES",
        "REFERENCES",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "MEDIAN",
        "STDDEV",
        "EACH",
        "HAVING",
        "BY",
        "AT",
        "MOST",
        "LEAST",
        "EXACTLY",
        "WHERE",
        "WHEN",
        "SEVERITY",
        "DIMENSION",
        "BECAUSE",
        "EVIDENCE",
        "SCHEDULE",
        "SCOPE",
        "OWNER",
        "ON",
        "FAIL",
        "ALERT",
        "BLOCK",
        "QUARANTINE",
        "TAG",
        "SAMPLES",
        "COUNTS",
        "FULL",
        "BASELINE",
        "SEASONALITY",
        "SENSITIVITY",
        "BUDGET",
        "AGAINST",
        "COMPARING",
        "NORMALISING",
        "USING",
        "FROM",
        "OFFSET",
        "CLASSIFY",
        "TREAT",
        "UNKNOWN",
        "PASS",
        "PRESERVING",
        "DERIVES",
        "TRUE",
        "FALSE",
        "CASE",
        "THEN",
        "ELSE",
        "END",
        "LIKE",
        "ILIKE",
    ]
)

#: Longest first: ``>=`` must not be read as ``>`` followed by ``=``.
OPERATORS: tuple[str, ...] = (
    "<>",
    "!=",
    ">=",
    "<=",
    "||",
    "=",
    ">",
    "<",
    "+",
    "-",
    "*",
    "/",
    "%",
)

PUNCTUATION: frozenset[str] = frozenset("(),.{}[]:;")

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUOTED_IDENTIFIER = re.compile(r'"(?:[^"]|"")*"')
#: A number, optionally with a decimal part, an exponent, or a trailing ``%``.
#: The percent is part of the literal because ``BELOW 0.1 %`` and
#: ``BELOW 0.1%`` mean the same thing to a reader and should to the parser.
_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")
_PARAMETER = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    position: Position
    #: For strings and regexes: the value with quoting and escapes resolved.
    value: str = ""

    @property
    def upper(self) -> str:
        return self.text.upper()

    def is_keyword(self, *words: str) -> bool:
        return self.kind is TokenKind.KEYWORD and self.upper in {w.upper() for w in words}

    def is_punctuation(self, *marks: str) -> bool:
        return self.kind is TokenKind.PUNCTUATION and self.text in marks

    def is_operator(self, *symbols: str) -> bool:
        return self.kind is TokenKind.OPERATOR and self.text in symbols

    @property
    def describe(self) -> str:
        """How this token should be named in an error message."""
        if self.kind is TokenKind.END:
            return "the end of the control"
        if self.kind is TokenKind.STRING:
            return f"the text {self.text}"
        return f"{self.text!r}"

    def __repr__(self) -> str:
        return f"Token({self.kind.value}, {self.text!r}, {self.position})"


class Lexer:
    """PQL text to tokens, with a position on every one."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._offset = 0
        self._line = 1
        self._column = 1

    def tokens(self) -> list[Token]:
        out: list[Token] = []
        while True:
            token = self._next()
            out.append(token)
            if token.kind is TokenKind.END:
                return out

    # -- scanning ----------------------------------------------------------

    def _next(self) -> Token:
        self._skip_ignorable()
        if self._offset >= len(self.source):
            return Token(TokenKind.END, "", self._here(0))
        character = self.source[self._offset]
        if character == "'":
            return self._string()
        if character == '"':
            return self._quoted_identifier()
        if character == "/" and self._looks_like_regex():
            return self._regex()
        if character == "$":
            return self._parameter()
        if character.isdigit():
            return self._number()
        if character.isalpha() or character == "_":
            return self._word()
        for symbol in OPERATORS:
            if self.source.startswith(symbol, self._offset):
                return self._emit(TokenKind.OPERATOR, symbol)
        if character in PUNCTUATION:
            return self._emit(TokenKind.PUNCTUATION, character)
        raise self._error(
            f"{character!r} does not belong in a control",
            remedy=(
                "Remove it. If it is part of a name, quote the name: "
                "\"odd name\". If it is part of text, quote the text: 'value'."
            ),
            length=1,
        )

    def _skip_ignorable(self) -> None:
        while self._offset < len(self.source):
            character = self.source[self._offset]
            if character in " \t\r" or character == "\n":
                self._advance(1)
            elif self.source.startswith("--", self._offset):
                end = self.source.find("\n", self._offset)
                self._advance((len(self.source) if end < 0 else end) - self._offset)
            elif self.source.startswith("/*", self._offset):
                self._skip_block_comment()
            else:
                return

    def _skip_block_comment(self) -> None:
        start = self._here(2)
        end = self.source.find("*/", self._offset + 2)
        if end < 0:
            raise PqlSyntaxError(
                "a comment is opened with /* and never closed",
                remedy="Close it with */, or use -- for a comment to the end of the line.",
                position=start,
                source=self.source,
            )
        self._advance(end + 2 - self._offset)

    def _word(self) -> Token:
        match = _IDENTIFIER.match(self.source, self._offset)
        assert match is not None
        text = match.group(0)
        kind = TokenKind.KEYWORD if text.upper() in KEYWORDS else TokenKind.IDENTIFIER
        return self._emit(kind, text)

    def _quoted_identifier(self) -> Token:
        match = _QUOTED_IDENTIFIER.match(self.source, self._offset)
        if match is None:
            raise self._error(
                "a quoted name is opened and never closed",
                remedy='Close it with a double quote: "risk positions".',
                length=1,
            )
        text = match.group(0)
        return self._emit(TokenKind.IDENTIFIER, text, value=text[1:-1].replace('""', '"'))

    def _string(self) -> Token:
        start = self._offset
        cursor = start + 1
        while cursor < len(self.source):
            if self.source[cursor] == "'":
                if self.source.startswith("''", cursor):
                    cursor += 2
                    continue
                text = self.source[start : cursor + 1]
                return self._emit(TokenKind.STRING, text, value=text[1:-1].replace("''", "'"))
            if self.source[cursor] == "\n":
                break
            cursor += 1
        raise self._error(
            "a piece of text is opened with ' and never closed",
            remedy=(
                "Close it with another '. To include a quote in the text, double it: 'O''Brien'."
            ),
            length=1,
        )

    def _regex(self) -> Token:
        start = self._offset
        cursor = start + 1
        while cursor < len(self.source):
            character = self.source[cursor]
            if character == "\\":
                cursor += 2
                continue
            if character == "/":
                text = self.source[start : cursor + 1]
                return self._emit(TokenKind.REGEX, text, value=text[1:-1])
            if character == "\n":
                break
            cursor += 1
        raise self._error(
            "a pattern is opened with / and never closed",
            remedy="Close it with another /, as in /^[A-Z]{2}[0-9]{10}$/.",
            length=1,
        )

    def _looks_like_regex(self) -> bool:
        """Whether ``/`` starts a pattern or is division.

        Decided by what came before: a pattern cannot follow a value, and
        division cannot follow an operator or ``MATCHES``. Getting this wrong
        either way produces an error a long way from the actual text, so it is
        worth the small amount of state.
        """
        return not self._previous_allows_division()

    def _previous_allows_division(self) -> bool:
        cursor = self._offset - 1
        while cursor >= 0 and self.source[cursor] in " \t\r\n":
            cursor -= 1
        if cursor < 0:
            return False
        character = self.source[cursor]
        if character in ")]":
            return True
        if character.isdigit():
            return True
        if character.isalnum() or character == "_":
            # An identifier, unless it is a keyword that expects a pattern.
            match = None
            for candidate in _IDENTIFIER.finditer(self.source, 0, cursor + 1):
                if candidate.end() == cursor + 1:
                    match = candidate
            return not (match and match.group(0).upper() in ("MATCHES", "LIKE", "ILIKE"))
        return False

    def _number(self) -> Token:
        match = _NUMBER.match(self.source, self._offset)
        assert match is not None
        return self._emit(TokenKind.NUMBER, match.group(0))

    def _parameter(self) -> Token:
        match = _PARAMETER.match(self.source, self._offset)
        if match is None:
            raise self._error(
                "$ must be followed by a parameter name",
                remedy=(
                    "Name the parameter, as in $business_date. Parameters are how a "
                    "control refers to the run's date without becoming non-repeatable."
                ),
                length=1,
            )
        return self._emit(TokenKind.PARAMETER, match.group(0), value=match.group(0)[1:])

    # -- bookkeeping -------------------------------------------------------

    def _emit(self, kind: TokenKind, text: str, *, value: str = "") -> Token:
        position = self._here(len(text))
        self._advance(len(text))
        return Token(kind, text, position, value=value)

    def _here(self, length: int) -> Position:
        return Position(
            line=self._line, column=self._column, offset=self._offset, length=max(1, length)
        )

    def _advance(self, count: int) -> None:
        for _ in range(count):
            if self._offset < len(self.source) and self.source[self._offset] == "\n":
                self._line += 1
                self._column = 1
            else:
                self._column += 1
            self._offset += 1

    def _error(self, message: str, *, remedy: str, length: int) -> PqlSyntaxError:
        return PqlSyntaxError(
            message, remedy=remedy, position=self._here(length), source=self.source
        )


def tokenise(source: str) -> list[Token]:
    return Lexer(source).tokens()
