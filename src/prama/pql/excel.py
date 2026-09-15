"""The Excel-familiar surface.

A finance person writes formulas every day. This lets them write one, and
compiles it to the **same** ``ast.Expression`` tree the rest of PQL produces —
no second IR, no second evaluator, no second conformance suite. That constraint
is the whole design: if Excel expressions had their own execution path, there
would be one more surface on which two engines can disagree, and that surface
is what the conformance suite exists to police.

**Familiarity, never compatibility.** Saying "we accept Excel formulas" makes
every reader expect ``VLOOKUP``, ``IFERROR`` and ``"1" + 1 = 2``. The moment one
behaves differently — silently — the trust this product is built on is gone. So
the differences are declared per function in the catalogue, printed by
``control explain``, and listed in ``docs/07``.

The parser is precedence-climbing and hand-written, matching how PQL's own
parser is written and for the same reasons: a generated parser needs a build
step this project does not have, and its error messages cannot carry a remedy.

Syntax accepted::

    =AND([quantity] > 0, [notional] = [quantity] * [price])
    =IF(ISBLANK([lei]), FALSE, LEN([lei]) = 20)
    =[currency] <> "USD"
    =ROUND([notional], 2) = [notional]

Columns are ``[bracketed]`` or bare identifiers. There are no ``A1``
references: this is a formula over a named dataset, not a grid, and the
resemblance is to a spreadsheet *table* rather than to cells.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Final

from prama.pql import ast
from prama.pql.errors import PqlSyntaxError
from prama.pql.functions import VOLATILE
from prama.pql.library import FUNCTIONS

#: Binding power per operator. Excel's precedence, which is also SQL's for
#: everything here except ``&`` and ``^`` — and those two are the reason this
#: is a table rather than a recursive-descent ladder copied from the PQL
#: parser: Excel puts concatenation *below* comparison, and getting that
#: backwards would silently reassociate every formula that mixes them.
PRECEDENCE: Final[dict[str, int]] = {
    "OR": 1,
    "AND": 2,
    "=": 3,
    "<>": 3,
    "<": 3,
    "<=": 3,
    ">": 3,
    ">=": 3,
    "&": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "^": 7,
}

#: Excel's spellings mapped to the AST's. ``=`` means equality in a formula and
#: assignment nowhere; ``<>`` is inequality.
OPERATORS: Final[dict[str, str]] = {
    "=": "=",
    # `<>`, not `!=`. PQL's not-equal is `<>` — it is in `ast.COMPARISONS` and
    # in the SQL backend's INFIX table — and `!=` is in neither, so every Excel
    # formula using the commonest operator in a spreadsheet produced an AST
    # that compiled on no engine (QA finding PQL-331). The Excel surface exists
    # to let a business author write what they already know; `<>` is what they
    # already know.
    "<>": "<>",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "&": "&",
    "^": "^",
}

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<bracket>\[[^\]]*\])
  | (?P<string>"(?:[^"]|"")*")
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<operator><>|<=|>=|[-+*/^&<>=])
  | (?P<punct>[(),;])
  | (?P<name>[A-Za-z_][A-Za-z0-9_.]*)
    """,
    re.VERBOSE,
)


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str
    position: int


def tokenise(formula: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(formula):
        match = _TOKEN.match(formula, index)
        if match is None:
            raise PqlSyntaxError(
                f"{formula[index]!r} is not something a formula can contain",
                remedy=(
                    'Formulas use columns in [brackets], numbers, "text", the '
                    "operators = <> < <= > >= + - * / & ^, and function calls."
                ),
                context={"position": index, "formula": formula},
            )
        index = match.end()
        kind = match.lastgroup or ""
        if kind == "space":
            continue
        tokens.append(Token(kind=kind, text=match.group(), position=match.start()))
    return tokens


class ExcelParser:
    """Precedence climbing over the token list.

    Small enough to read in one sitting, which is deliberate: an expression
    language whose parser nobody can follow is an expression language whose
    edge cases nobody can predict.
    """

    def __init__(self, formula: str) -> None:
        # A leading "=" is how a spreadsheet starts a formula and how a user
        # will type it. Accepted and discarded rather than refused, because
        # refusing it would be pedantry about the one habit this surface exists
        # to accommodate.
        self.source = formula.strip()
        body = self.source[1:] if self.source.startswith("=") else self.source
        self.tokens = tokenise(body)
        self.index = 0

    # -- the token stream --------------------------------------------------

    @property
    def current(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> Token:
        token = self.current
        if token is None:
            raise self._error("the formula ends before it is finished")
        self.index += 1
        return token

    def expect(self, text: str) -> Token:
        token = self.current
        if token is None or token.text.upper() != text.upper():
            found = token.text if token else "the end of the formula"
            raise self._error(f"expected {text!r} and found {found!r}")
        return self.take()

    def _error(self, message: str, *, remedy: str = "") -> PqlSyntaxError:
        """A refusal, with the generic remedy unless the caller knows better.

        The default is about brackets and argument counts, which is right for
        most failures here and useless for a malformed column reference — so a
        caller that knows what was wrong can say so instead.
        """
        position = self.current.position if self.current else len(self.source)
        return PqlSyntaxError(
            message,
            remedy=remedy
            or (
                "Check the brackets and the argument count. Functions available: "
                + ", ".join(FUNCTIONS.names())
                + "."
            ),
            context={"formula": self.source, "position": position},
        )

    # -- the grammar -------------------------------------------------------

    def parse(self) -> ast.Expression:
        if not self.tokens:
            raise self._error("the formula is empty")
        expression = self.expression()
        if self.current is not None:
            raise self._error(f"unexpected {self.current.text!r} after the formula")
        return expression

    def expression(self, minimum: int = 0) -> ast.Expression:
        left = self.unary()
        while True:
            token = self.current
            if token is None:
                break
            operator = token.text.upper()
            binding = PRECEDENCE.get(operator)
            if binding is None or binding < minimum:
                break
            self.take()
            # All of Excel's binary operators are left-associative, including
            # ``^`` — which differs from mathematics and from most languages,
            # and is one of the places a copied ladder would get it wrong.
            right = self.expression(binding + 1)
            left = self._binary(operator, left, right)
        return left

    def unary(self) -> ast.Expression:
        token = self.current
        if token is not None and token.text in ("-", "+"):
            self.take()
            operand = self.unary()
            if token.text == "-":
                return ast.UnaryOp(operator="-", operand=operand)
            return operand
        if token is not None and token.text.upper() == "NOT":
            self.take()
            return ast.UnaryOp(operator="NOT", operand=self.unary())
        return self.primary()

    def primary(self) -> ast.Expression:
        token = self.take()
        if token.kind == "punct" and token.text == "(":
            inner = self.expression()
            self.expect(")")
            return inner
        if token.kind == "number":
            value = float(token.text) if "." in token.text else int(token.text)
            return ast.Literal(value=value, literal_type="number")
        if token.kind == "string":
            # Excel escapes a quote by doubling it, and so does SQL.
            return ast.Literal(value=token.text[1:-1].replace('""', '"'), literal_type="text")
        if token.kind == "bracket":
            inside = token.text[1:-1].strip()
            if not inside:
                # `[]` stripped to "" and produced a ColumnRef with an empty
                # name — a reference that cannot resolve to anything, built
                # without complaint. QA round 4, `PQL-339`.
                raise self._error("[] does not name a column")
            # Brackets are the quoting mechanism, so what is inside them is a
            # name verbatim — a dot included. That is the point of quoting, and
            # it is how `[total.gbp]` reaches a column actually called that.
            # A bare identifier splits on the dot instead; see `name`.
            return ast.ColumnRef(name=inside)
        if token.kind == "name":
            return self.name(token)
        raise self._error(f"unexpected {token.text!r}")

    def name(self, token: Token) -> ast.Expression:
        upper = token.text.upper()
        if upper in ("TRUE", "FALSE"):
            return ast.Literal(value=upper == "TRUE", literal_type="boolean")
        if self.current is not None and self.current.text == "(":
            return self.call(token)
        # A bare identifier is a column. Excel would call this a defined name;
        # over a dataset it is the column of that name, and there is nothing
        # else it could sensibly be.
        #
        # Qualified the way the PQL parser qualifies one — `dataset.column`,
        # exactly one dot — rather than as a single name containing a dot. The
        # tokenizer's `name` pattern swallows dots, so `positions.notional`
        # became one column literally called "positions.notional", which cannot
        # resolve against any schema and said nothing at parse time.
        # QA round 4, `PQL-338`.
        dataset, _, column = token.text.partition(".")
        if not column:
            return ast.ColumnRef(name=token.text)
        if "." in column:
            raise self._error(
                f"{token.text!r} has more than one dot",
                remedy="A column is written as `dataset.column`, or in [brackets] verbatim.",
            )
        return ast.ColumnRef(name=column, dataset=dataset)

    def call(self, token: Token) -> ast.Expression:
        name = token.text.upper()
        self.expect("(")
        arguments: list[ast.Expression] = []
        if self.current is not None and self.current.text != ")":
            arguments.append(self.expression())
            while self.current is not None and self.current.text in (",", ";"):
                # ``;`` as well as ``,``: a European locale's Excel separates
                # arguments with a semicolon, and a user pasting their own
                # formula should not have to know that Prama is not localised.
                self.take()
                arguments.append(self.expression())
        self.expect(")")

        if name in ("AND", "OR"):
            # Connectives, not functions: they lower to the IR's own boolean
            # operators so the three-valued logic is the language's rather than
            # a function's approximation of it.
            return self._connective(name, arguments)
        if name == "NOT":
            if len(arguments) != 1:
                raise self._error("NOT takes exactly one argument")
            return ast.UnaryOp(operator="NOT", operand=arguments[0])
        if name in VOLATILE:
            raise PqlSyntaxError(
                f"{name}() cannot be used in a control: it returns {VOLATILE[name]}",
                remedy=(
                    "A control has to replay: the same plan against the same snapshot "
                    "must give the same verdict, or its evidence is not evidence. "
                    "Use a parameter, which the run supplies and the evidence records."
                ),
                context={"formula": self.source, "function": name},
            )
        declared = FUNCTIONS.find(name)
        if declared is None:
            raise PqlSyntaxError(
                f"there is no function called {name}",
                remedy=(
                    "Available: "
                    + ", ".join(FUNCTIONS.names())
                    + ". Prama accepts a deliberately small set: every one of them has "
                    "a lowering for each engine and a reference implementation that is "
                    "tested to agree with it."
                ),
                context={"formula": self.source, "function": name},
            )
        if not declared.accepts(len(arguments)):
            raise self._error(
                f"{name} takes {declared.arity_words()}, and was given {len(arguments)}"
            )
        return ast.FunctionCall(name=name, arguments=tuple(arguments))

    def _connective(self, name: str, arguments: list[ast.Expression]) -> ast.Expression:
        if len(arguments) < 2:
            raise self._error(f"{name} takes at least two arguments")
        combined = arguments[0]
        for argument in arguments[1:]:
            combined = ast.BinaryOp(operator=name, left=combined, right=argument)
        return combined

    def _binary(self, operator: str, left: ast.Expression, right: ast.Expression) -> ast.Expression:
        if operator in ("AND", "OR"):
            return ast.BinaryOp(operator=operator, left=left, right=right)
        if operator == "&":
            # Excel's concatenation operator becomes the catalogue's CONCAT, so
            # it inherits the same per-engine lowering and the same unknown
            # rule rather than acquiring its own.
            return ast.FunctionCall(name="CONCAT", arguments=(left, right))
        if operator == "^":
            raise PqlSyntaxError(
                "^ is not supported",
                remedy=(
                    "Exponentiation is not in the catalogue: the engines disagree "
                    "about precision and about what a fractional exponent of a "
                    "negative number means, and a control has to mean one thing."
                ),
                context={"formula": self.source},
            )
        return ast.BinaryOp(operator=OPERATORS[operator], left=left, right=right)


def parse_formula(formula: str) -> ast.Expression:
    """One Excel-familiar formula as a PQL expression."""
    return ExcelParser(formula).parse()
