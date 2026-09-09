"""Reading PQL into an AST.

Recursive descent, deliberately. A generated parser would be shorter and would
produce errors nobody can act on; here every place the parser can be surprised
is a place we can say what was expected and what to do instead, and that is most
of the value of having a language at all.

The parser's other job is to refuse things that parse but should not exist:
a control with no justification, a comparison against ``CURRENT_DATE``, a
threshold on an assertion that has no rate. Catching those here — at authoring
time, with the caret on the offending clause — is the whole difference between
a language and a string that is executed later and hopefully works.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

from prama.pql import ast
from prama.pql.errors import Position, PqlSyntaxError
from prama.pql.tokens import Token, TokenKind, tokenise

#: Functions that read the clock or a random source. Refused inside an
#: expression: a control whose verdict depends on when it ran cannot be
#: replayed, and an evidence record that cannot be replayed is an assertion
#: rather than a finding. The run's date arrives as $business_date instead.
NON_DETERMINISTIC: frozenset[str] = frozenset(
    {
        "NOW",
        "CURRENT_TIMESTAMP",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "GETDATE",
        "SYSDATE",
        "RANDOM",
        "RAND",
        "UUID",
        "NEWID",
    }
)

#: Aggregates the language knows. Anything else is a scalar function call and
#: is checked against the backend's capabilities later.
AGGREGATES: frozenset[str] = frozenset({"COUNT", "SUM", "AVG", "MIN", "MAX", "MEDIAN", "STDDEV"})

#: Binary operator precedence, loosest first.
PRECEDENCE: tuple[tuple[str, ...], ...] = (
    ("OR",),
    ("AND",),
    ("=", "<>", "!=", ">", ">=", "<", "<="),
    ("+", "-", "||"),
    ("*", "/", "%"),
)

#: Where the keyword predicates — IS NULL, IN, BETWEEN, MATCHES, LIKE — bind.
#: The same level as a comparison, so ``a = 1 AND b IN (…)`` groups the way a
#: reader expects rather than turning the whole conjunction into the left side
#: of the IN.
COMPARISON_LEVEL = 2

#: NOT sits between AND and comparison, as it does in SQL. Parsed as part of
#: the unary chain instead, ``NOT side = 'BUY'`` would read as
#: ``(NOT side) = 'BUY'`` — which is a different control, and a valid-looking
#: one.
NOT_LEVEL = 2


class Parser:
    """One PQL source text to a :class:`~prama.pql.ast.Program`."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._tokens = tokenise(source)
        self._index = 0
        #: True while parsing a selector's condition, where IS begins the
        #: assertion rather than continuing the condition.
        self._in_selector = False

    # -- entry points ------------------------------------------------------

    def parse(self) -> ast.Program:
        controls: list[ast.Control] = []
        suites: list[ast.Suite] = []
        while not self._at_end:
            if self._peek.is_keyword("SUITE"):
                suites.append(self._suite())
            elif self._peek.is_keyword("CHECK"):
                controls.append(self._control())
            else:
                raise self._error(
                    f"expected a control and found {self._peek.describe}",
                    remedy=(
                        "A control begins with CHECK, and a group of them with SUITE. "
                        "For example: CHECK positions.account_id IS NOT NULL"
                    ),
                )
        return ast.Program(controls=tuple(controls), suites=tuple(suites))

    def parse_control(self) -> ast.Control:
        """One control, for the editor and for tests."""
        control = self._control()
        if not self._at_end:
            raise self._error(
                f"there is more text after the control: {self._peek.describe}",
                remedy="Each control ends where the next CHECK begins.",
            )
        return control

    # -- structure ---------------------------------------------------------

    def _suite(self) -> ast.Suite:
        start = self._expect_keyword("SUITE").position
        name = self._name("a name for the suite")
        self._expect_punctuation("{")
        controls: list[ast.Control] = []
        while not self._peek.is_punctuation("}"):
            if self._at_end:
                raise self._error(
                    f"the suite {name!r} is opened and never closed",
                    remedy="Close it with }.",
                )
            controls.append(self._control())
        self._expect_punctuation("}")
        return ast.Suite(name=name, controls=tuple(controls), position=start)

    def _control(self) -> ast.Control:
        start = self._expect_keyword("CHECK").position
        selector = self._selector()
        if selector is not None:
            # The assertion's subject is the attribute the selector will pick,
            # which is not known until expansion.
            placeholder = ast.SelectedAttribute(position=self._peek.position)
            assertion = self._assertion("every attribute", placeholder)
            control = ast.Control(assertion=assertion, selector=selector, position=start)
            return self._modifiers(control)
        target, subject = self._target()
        assertion = self._assertion(target, subject)
        control = ast.Control(target=target, assertion=assertion, position=start)
        return self._modifiers(control)

    def _selector(self) -> ast.Selector | None:
        """``EVERY ATTRIBUTE WHERE …`` or ``CONCEPT Instrument.ISIN``.

        Recognised before the target, because both begin where a dataset name
        would go and neither is one.
        """
        start = self._peek.position
        if self._peek.is_keyword("EVERY"):
            self._advance()
            self._expect_keyword("ATTRIBUTE")
            where = self._selector_condition() if self._match_keyword("WHERE") else None
            return ast.Selector(kind="attribute", where=where, position=start)
        if self._peek.is_keyword("CONCEPT"):
            self._advance()
            concept = self._name("the concept, as in Instrument")
            self._expect_punctuation(".")
            prop = self._name("the concept property, as in ISIN")
            return ast.Selector(
                kind="concept", concept=concept, concept_property=prop, position=start
            )
        return None

    def _selector_condition(self) -> ast.Expression:
        """The metadata condition of a selector, stopping before the assertion.

        ``EVERY ATTRIBUTE WHERE is_cde IS NOT NULL`` is ambiguous to a parser
        and, read carefully, to a person: does IS NOT NULL qualify ``is_cde``
        or state what must be true of the matched attributes? The rule is that
        it always begins the assertion — so inside a selector condition ``IS``
        ends the condition, and an attribute's missing metadata is written
        ``domain = ''`` rather than ``domain IS NULL``.

        Everything else stays available: ``tags IN ('pii')`` and
        ``criticality IN ('tier1','tier2')`` read the way they should, because
        IN cannot begin an assertion about a matched attribute on its own.
        """
        self._in_selector = True
        try:
            return self._expression()
        finally:
            self._in_selector = False

    def _target(self) -> tuple[str, ast.ColumnRef | None]:
        """The dataset a control is about, and the column if it names one.

        ``CHECK positions.notional IS NOT NULL`` is about ``positions``; the
        column is the assertion's subject. Reading it the other way round —
        treating ``positions.notional`` as the target — would make the scope of
        every column check a single column, and the row count meaningless.
        """
        first = self._name("the dataset this control is about")
        if self._peek.is_punctuation("."):
            self._advance()
            column = self._name("a column name after the dot")
            return first, ast.ColumnRef(
                name=column, dataset=first, position=self._previous.position
            )
        return first, None

    # -- assertions --------------------------------------------------------

    def _assertion(self, target: str, subject: ast.Expression | None) -> ast.Assertion:
        token = self._peek
        if token.is_keyword("HAS"):
            return self._has_assertion(subject)
        if token.is_keyword("IS"):
            return self._is_assertion(subject)
        if token.is_keyword("IN", "NOT", "MATCHES", "BETWEEN") or token.kind is TokenKind.OPERATOR:
            return self._predicate(self._require_subject(subject, token))
        if token.is_keyword("REFERENCES"):
            return self._references(self._require_subject(subject, token))
        if token.is_keyword("SATISFIES"):
            return self._satisfies()
        raise self._error(
            f"expected something to check about {target} and found {token.describe}",
            remedy=(
                "A control says what must be true: IS NOT NULL, IN CODELIST, "
                "HAS UNIQUE KEY (…), HAS ROW COUNT BETWEEN …, REFERENCES …, SATISFIES …"
            ),
        )

    def _has_assertion(self, subject: ast.Expression | None) -> ast.Assertion:
        start = self._expect_keyword("HAS").position
        if self._peek.is_keyword("UNIQUE"):
            self._advance()
            self._expect_keyword("KEY")
            return ast.UniqueKeyAssertion(columns=self._column_list(), position=start)
        if self._peek.is_keyword("ROW"):
            self._advance()
            self._expect_keyword("COUNT")
            minimum, maximum = self._bounds()
            return ast.RowCountAssertion(minimum=minimum, maximum=maximum, position=start)
        if self._peek.is_keyword("LENGTH"):
            self._advance()
            self._expect_keyword("BETWEEN")
            lower, upper = self._between_bounds()
            return ast.PredicateAssertion(
                subject=self._require_subject(subject, self._previous),
                operator="has_length_between",
                argument=lower,
                upper=upper,
                position=start,
            )
        if self._peek.is_keyword("FORMAT"):
            self._advance()
            return ast.PredicateAssertion(
                subject=self._require_subject(subject, self._previous),
                operator="has_format",
                argument=self._reference_literal(),
                position=start,
            )
        raise self._error(
            f"expected UNIQUE KEY, ROW COUNT, LENGTH or FORMAT after HAS, "
            f"found {self._peek.describe}",
            remedy=(
                "For example: HAS UNIQUE KEY (account_id, as_of_date), or "
                "HAS ROW COUNT BETWEEN 900000 AND 1200000"
            ),
        )

    def _is_assertion(self, subject: ast.Expression | None) -> ast.Assertion:
        start = self._expect_keyword("IS").position
        negated = bool(self._match_keyword("NOT"))
        if self._peek.is_keyword("NULL"):
            self._advance()
            return ast.PredicateAssertion(
                subject=self._require_subject(subject, self._previous),
                operator="is_not_null" if negated else "is_null",
                position=start,
            )
        if self._peek.is_keyword("UNIQUE"):
            self._advance()
            return ast.PredicateAssertion(
                subject=self._require_subject(subject, self._previous),
                operator="is_unique",
                position=start,
            )
        if self._peek.is_keyword("VALID"):
            self._advance()
            return ast.PredicateAssertion(
                subject=self._require_subject(subject, self._previous),
                operator="is_valid",
                argument=self._reference_literal(),
                negated=negated,
                position=start,
            )
        if self._peek.is_keyword("FRESH"):
            self._advance()
            return self._freshness(start, subject)
        if self._peek.is_keyword("IN"):
            self._advance()
            return self._in_predicate(
                self._require_subject(subject, self._previous), negated, start
            )
        raise self._error(
            f"expected NULL, UNIQUE, VALID, FRESH or IN after IS, found {self._peek.describe}",
            remedy=(
                "For example: IS NOT NULL, IS UNIQUE, IS VALID ISIN, or "
                "IS FRESH WITHIN 30 MINUTES OF '06:30'"
            ),
        )

    def _freshness(self, start: Position, subject: ast.Expression | None) -> ast.FreshnessAssertion:
        self._expect_keyword("WITHIN")
        minutes = self._duration_minutes()
        due_time = ""
        calendar = ""
        if self._match_keyword("OF"):
            due_time = self._text("the time the data is due, as in '06:30'")
        if self._match_keyword("CALENDAR"):
            calendar = self._text("the calendar name, as in 'TARGET2'")
        return ast.FreshnessAssertion(
            tolerance_minutes=minutes,
            due_time=due_time,
            calendar=calendar,
            column=subject if isinstance(subject, ast.ColumnRef) else None,
            position=start,
        )

    def _predicate(self, subject: ast.Expression) -> ast.Assertion:
        start = self._peek.position
        negated = bool(self._match_keyword("NOT"))
        token = self._peek
        if token.is_keyword("IN"):
            self._advance()
            return self._in_predicate(subject, negated, start)
        if token.is_keyword("BETWEEN"):
            self._advance()
            lower, upper = self._between_bounds()
            return ast.PredicateAssertion(
                subject=subject,
                operator="between",
                argument=lower,
                upper=upper,
                negated=negated,
                position=start,
            )
        if token.is_keyword("MATCHES"):
            self._advance()
            return ast.PredicateAssertion(
                subject=subject,
                operator="matches",
                argument=self._pattern(),
                negated=negated,
                position=start,
            )
        if token.kind is TokenKind.OPERATOR and token.text in ast.COMPARISONS | {"!="}:
            self._advance()
            operator = "<>" if token.text == "!=" else token.text
            return ast.PredicateAssertion(
                subject=subject, operator=operator, argument=self._expression(), position=start
            )
        raise self._error(
            f"expected a comparison after {subject.render()}, found {token.describe}",
            remedy="For example: > 0, IN ('GBP','USD'), BETWEEN 1 AND 10, MATCHES /^[A-Z]{2}/",
        )

    def _between_bounds(self) -> tuple[ast.Expression, ast.Expression]:
        """The two bounds of BETWEEN, without swallowing its AND.

        Parsed above the precedence of AND, or ``BETWEEN 1 AND 100`` reads as
        ``BETWEEN (1 AND 100)`` and the rest of the control disappears into a
        boolean expression.
        """
        lower = self._expression(COMPARISON_LEVEL + 1)
        self._expect_keyword("AND")
        return lower, self._expression(COMPARISON_LEVEL + 1)

    def _in_predicate(
        self, subject: ast.Expression, negated: bool, start: Position
    ) -> ast.PredicateAssertion:
        if self._match_keyword("CODELIST"):
            return ast.PredicateAssertion(
                subject=subject,
                operator="in_codelist",
                argument=self._reference_literal(),
                negated=negated,
                position=start,
            )
        return ast.PredicateAssertion(
            subject=subject,
            operator="in",
            argument=self._list_expression(),
            negated=negated,
            position=start,
        )

    def _references(self, subject: ast.Expression) -> ast.ReferenceAssertion:
        start = self._expect_keyword("REFERENCES").position
        column = self._require_column(
            subject,
            "a reference names one column on each side, so it cannot be written against a selector",
            "Write it against the dataset: CHECK positions.account_id REFERENCES "
            "accounts.account_id.",
        )
        dataset = self._name("the dataset the value must exist in")
        self._expect_punctuation(".")
        target = self._name("the column the value must exist in")
        return ast.ReferenceAssertion(
            column=column, target_dataset=dataset, target_column=target, position=start
        )

    def _satisfies(self) -> ast.Assertion:
        start = self._expect_keyword("SATISFIES").position
        if self._match_keyword("EXCEL"):
            return self._excel(start)
        first = self._expression()
        if self._match_keyword("DETERMINES"):
            determinant = _as_columns(first)
            if determinant is None:
                raise self._error(
                    "the left of DETERMINES must be one or more columns",
                    remedy="For example: SATISFIES account_id DETERMINES legal_entity_id",
                )
            dependent = _as_columns(self._expression())
            if dependent is None:
                raise self._error(
                    "the right of DETERMINES must be one or more columns",
                    remedy="For example: SATISFIES account_id DETERMINES legal_entity_id",
                )
            return ast.FunctionalDependencyAssertion(
                determinant=determinant, dependent=dependent, position=start
            )
        return ast.ExpressionAssertion(condition=first, position=start)

    def _excel(self, start: Position) -> ast.Assertion:
        """``SATISFIES EXCEL '=…'`` — a formula, in the syntax people write.

        Marked explicitly rather than sniffed. The two syntaxes overlap: ``=``
        is equality in a formula and nowhere in PQL, ``<>`` is inequality in one
        and nothing in the other, and a parser guessing between them would
        occasionally guess wrong on a control that then means something its
        author did not write.

        What it produces is an ordinary ``ExpressionAssertion`` over the *same*
        AST. There is no Excel evaluator, no Excel IR and no Excel code path in
        the compiler — which is what keeps one control meaning one thing.
        """
        from prama.pql.excel import parse_formula

        token = self._peek
        if token.kind is not TokenKind.STRING:
            raise self._error(
                "EXCEL must be followed by the formula in quotes",
                remedy=(
                    "For example: SATISFIES EXCEL "
                    "'=AND([quantity] > 0, [notional] = [quantity] * [price])'"
                ),
            )
        self._advance()
        condition = parse_formula(str(token.value))
        return ast.ExpressionAssertion(
            condition=condition, position=start, source_syntax="excel", source=str(token.value)
        )

    # -- modifiers ---------------------------------------------------------

    def _modifiers(self, control: ast.Control) -> ast.Control:
        """Every clause after the assertion, in any order.

        Order-independent because people write them in the order they think of
        them, and a language that insisted on WHERE before SEVERITY would be
        rejected by everyone who had to use it.
        """
        seen: set[str] = set()
        while True:
            token = self._peek
            clause = self._modifier_name(token)
            if clause is None:
                break
            if clause in seen:
                raise self._error(
                    f"{clause} is given twice for this control",
                    remedy=(
                        f"Remove one of them. Two {clause} clauses would leave it "
                        f"ambiguous which was meant."
                    ),
                )
            seen.add(clause)
            control = self._apply_modifier(control, clause)
        return self._finish(control)

    def _modifier_name(self, token: Token) -> str | None:
        if token.is_keyword("WHERE"):
            return "WHERE"
        if token.is_keyword("FOR"):
            return "FOR EACH"
        if token.is_keyword("SEVERITY"):
            return "SEVERITY"
        if token.is_keyword("DIMENSION"):
            return "DIMENSION"
        if token.is_keyword("BECAUSE"):
            return "BECAUSE"
        if token.is_keyword("EVIDENCE"):
            return "EVIDENCE"
        if token.is_keyword("OWNER"):
            return "OWNER"
        if token.is_keyword("TREAT"):
            return "TREAT UNKNOWN"
        if token.is_keyword("ON"):
            return "ON FAIL"
        if token.is_keyword("AT", "BELOW", "WITHIN"):
            return "threshold"
        return None

    def _apply_modifier(self, control: ast.Control, clause: str) -> ast.Control:
        if clause == "WHERE":
            self._advance()
            return dataclasses.replace(control, where=self._expression())
        if clause == "FOR EACH":
            return dataclasses.replace(control, segmentation=self._segmentation())
        if clause == "SEVERITY":
            self._advance()
            return dataclasses.replace(control, severity=self._severity())
        if clause == "DIMENSION":
            self._advance()
            return dataclasses.replace(control, dimensions=self._dimensions())
        if clause == "BECAUSE":
            self._advance()
            return dataclasses.replace(
                control, because=self._text("the reason this control exists")
            )
        if clause == "EVIDENCE":
            self._advance()
            return dataclasses.replace(control, evidence=self._evidence())
        if clause == "OWNER":
            self._advance()
            return dataclasses.replace(control, owner=self._text("who owns this control"))
        if clause == "TREAT UNKNOWN":
            return dataclasses.replace(control, unknown_policy=self._unknown_policy())
        if clause == "ON FAIL":
            return dataclasses.replace(control, on_fail=self._fail_action())
        return dataclasses.replace(control, threshold=self._threshold())

    def _segmentation(self) -> ast.Segmentation:
        start = self._expect_keyword("FOR").position
        self._expect_keyword("EACH")
        columns = [self._column()]
        while self._peek.is_punctuation(","):
            self._advance()
            columns.append(self._column())
        having = self._expression() if self._match_keyword("HAVING") else None
        return ast.Segmentation(columns=tuple(columns), having=having, position=start)

    def _severity(self) -> ast.Severity:
        token = self._advance()
        try:
            return ast.Severity(token.text.lower())
        except ValueError:
            raise self._error(
                f"{token.text!r} is not a severity",
                remedy=f"Use one of: {', '.join(s.value for s in ast.Severity)}.",
                token=token,
            ) from None

    def _dimensions(self) -> tuple[ast.Dimension, ...]:
        out = [self._dimension()]
        while self._peek.is_punctuation(","):
            self._advance()
            out.append(self._dimension())
        return tuple(out)

    def _dimension(self) -> ast.Dimension:
        token = self._advance()
        try:
            return ast.Dimension(token.text.lower())
        except ValueError:
            raise self._error(
                f"{token.text!r} is not a quality dimension",
                remedy=f"Use one of: {', '.join(d.value for d in ast.Dimension)}.",
                token=token,
            ) from None

    def _evidence(self) -> ast.EvidenceSpec:
        token = self._advance()
        level = token.text.lower()
        if level not in {e.value for e in ast.EvidenceLevel}:
            raise self._error(
                f"{token.text!r} is not an evidence level",
                remedy="Use counts, samples, or full.",
                token=token,
            )
        maximum = 50
        if self._peek.is_punctuation("("):
            self._advance()
            maximum = self._integer("how many samples to keep")
            self._expect_punctuation(")")
        return ast.EvidenceSpec(level=ast.EvidenceLevel(level), max_samples=maximum)

    def _unknown_policy(self) -> ast.UnknownPolicy:
        self._expect_keyword("TREAT")
        self._expect_keyword("UNKNOWN")
        self._expect_keyword("AS")
        token = self._advance()
        if token.upper == "PASS":
            return ast.UnknownPolicy.PASS
        if token.upper in ("VIOLATION", "FAIL"):
            return ast.UnknownPolicy.VIOLATION
        raise self._error(
            f"expected PASS or VIOLATION after TREAT UNKNOWN AS, found {token.describe}",
            remedy=(
                "Prama counts an unknown as a violation by default, because silence "
                "about unknowns is the commonest source of false confidence. Write "
                "TREAT UNKNOWN AS PASS only where the business genuinely means it."
            ),
            token=token,
        )

    def _require_column(self, subject: ast.Expression, message: str, remedy: str) -> ast.ColumnRef:
        """A named column, where a placeholder will not do.

        Some assertions relate one named column to another. Under a selector
        the left side is a different column for every match, so there is no
        single relationship to declare — refusing is the honest answer rather
        than expanding into something nobody wrote.
        """
        if not isinstance(subject, ast.ColumnRef):
            raise self._error(message, remedy=remedy)
        return subject

    def _fail_action(self) -> ast.FailAction:
        self._expect_keyword("ON")
        self._expect_keyword("FAIL")
        token = self._advance()
        try:
            return ast.FailAction(token.text.lower())
        except ValueError:
            raise self._error(
                f"{token.text!r} is not something to do on failure",
                remedy=f"Use one of: {', '.join(a.value for a in ast.FailAction)}.",
                token=token,
            ) from None

    def _threshold(self) -> ast.Threshold:
        token = self._advance()
        if token.is_keyword("AT"):
            comparator = "<=" if self._expect_keyword_of("MOST", "LEAST").upper == "MOST" else ">="
            value = float(self._number_token().text.rstrip("%"))
            self._match_keyword("ROWS", "ROW")
            return ast.Threshold(unit="rows", value=value, comparator=comparator)
        if token.is_keyword("BELOW"):
            return ast.Threshold(unit="rate", value=self._rate())
        number = self._number_token()
        text = number.text
        if text.endswith("%"):
            return ast.Threshold(unit="rate", value=float(text[:-1]) / 100)
        if self._peek.kind is TokenKind.IDENTIFIER and len(self._peek.text) == 3:
            return ast.Threshold(unit="amount", value=float(text), currency=self._advance().upper)
        return ast.Threshold(unit="amount", value=float(text))

    def _rate(self) -> float:
        token = self._number_token()
        return float(token.text[:-1]) / 100 if token.text.endswith("%") else float(token.text)

    def _finish(self, control: ast.Control) -> ast.Control:
        """Last checks, once everything about the control is known."""
        if control.unknown_policy is ast.UnknownPolicy.PASS and not control.because:
            raise self._error(
                "TREAT UNKNOWN AS PASS needs a BECAUSE",
                remedy=(
                    "Ignoring unknowns is a decision somebody has to own. Say why: "
                    "BECAUSE 'unmatched rows are handled by the break workflow'."
                ),
                token=self._previous,
            )
        return control

    # -- expressions -------------------------------------------------------

    def _expression(self, level: int = 0) -> ast.Expression:
        if level >= len(PRECEDENCE):
            return self._unary()
        if level == NOT_LEVEL and self._peek.is_keyword("NOT"):
            token = self._advance()
            return ast.UnaryOp(
                operator="NOT", operand=self._expression(NOT_LEVEL), position=token.position
            )
        left = self._expression(level + 1)
        if level == COMPARISON_LEVEL:
            left = self._predicate_suffix(left)
        while True:
            token = self._peek
            symbol = self._operator_at(token, level)
            if symbol is None:
                return left
            self._advance()
            right = self._expression(level + 1)
            left = ast.BinaryOp(operator=symbol, left=left, right=right, position=token.position)

    def _predicate_suffix(self, left: ast.Expression) -> ast.Expression:
        """``IS NULL``, ``IN (…)``, ``BETWEEN``, ``MATCHES`` inside an expression.

        The same predicates the assertion catalogue offers, available in a WHERE
        clause — because a filter that could not say ``region IN ('EMEA','APAC')``
        would send people straight to a raw-SQL escape hatch, which is the thing
        the language exists to avoid.
        """
        token = self._peek
        if token.is_keyword("IS") and not self._in_selector:
            self._advance()
            negated = bool(self._match_keyword("NOT"))
            self._expect_keyword("NULL")
            operator = "IS NOT NULL" if negated else "IS NULL"
            return ast.UnaryOp(operator=operator, operand=left, position=token.position)
        negated = False
        if token.is_keyword("NOT") and self._tokens[self._index + 1].is_keyword(
            "IN", "BETWEEN", "MATCHES", "LIKE", "ILIKE"
        ):
            self._advance()
            negated = True
            token = self._peek
        if token.is_keyword("IN"):
            self._advance()
            right: ast.Expression = self._list_expression()
        elif token.is_keyword("BETWEEN"):
            self._advance()
            lower = self._expression(COMPARISON_LEVEL + 1)
            self._expect_keyword("AND")
            upper = self._expression(COMPARISON_LEVEL + 1)
            right = ast.ListExpression(items=(lower, upper), position=token.position)
        elif token.is_keyword("MATCHES", "LIKE", "ILIKE"):
            self._advance()
            right = self._expression(COMPARISON_LEVEL + 1)
        else:
            return left
        operator = f"NOT {token.upper}" if negated else token.upper
        return ast.BinaryOp(operator=operator, left=left, right=right, position=token.position)

    @staticmethod
    def _operator_at(token: Token, level: int) -> str | None:
        symbols = PRECEDENCE[level]
        if token.kind is TokenKind.OPERATOR and token.text in symbols:
            return "<>" if token.text == "!=" else token.text
        if token.kind is TokenKind.KEYWORD and token.upper in symbols:
            return token.upper
        return None

    def _unary(self) -> ast.Expression:
        token = self._peek
        if token.is_operator("-", "+"):
            self._advance()
            return ast.UnaryOp(operator=token.text, operand=self._unary(), position=token.position)
        return self._primary()

    def _primary(self) -> ast.Expression:
        token = self._peek
        if token.is_punctuation("("):
            self._advance()
            inner = self._expression()
            self._expect_punctuation(")")
            return inner
        if token.kind is TokenKind.NUMBER:
            self._advance()
            if token.text.endswith("%"):
                return ast.Literal(
                    value=float(token.text[:-1]) / 100,
                    literal_type="percentage",
                    position=token.position,
                )
            value: float | int = (
                float(token.text)
                if "." in token.text or "e" in token.text.lower()
                else int(token.text)
            )
            return ast.Literal(value=value, literal_type="number", position=token.position)
        if token.kind is TokenKind.STRING:
            self._advance()
            return ast.Literal(value=token.value, literal_type="text", position=token.position)
        if token.kind is TokenKind.REGEX:
            self._advance()
            return ast.Literal(value=token.value, literal_type="pattern", position=token.position)
        if token.kind is TokenKind.PARAMETER:
            self._advance()
            return ast.ParameterRef(name=token.value, position=token.position)
        if token.is_keyword("NULL"):
            self._advance()
            return ast.Literal(value=None, literal_type="null", position=token.position)
        if token.is_keyword("TRUE", "FALSE"):
            self._advance()
            return ast.Literal(
                value=token.upper == "TRUE", literal_type="boolean", position=token.position
            )
        if token.kind in (TokenKind.IDENTIFIER, TokenKind.KEYWORD):
            return self._identifier_expression()
        raise self._error(
            f"expected a value or a column and found {token.describe}",
            remedy="A column name, a number, quoted text, or $business_date.",
        )

    def _identifier_expression(self) -> ast.Expression:
        token = self._advance()
        name = token.value or token.text
        if self._peek.is_punctuation("("):
            return self._call(name, token)
        if self._peek.is_punctuation("."):
            self._advance()
            column = self._name("a column name after the dot")
            return ast.ColumnRef(name=column, dataset=name, position=token.position)
        return ast.ColumnRef(name=name, position=token.position)

    def _call(self, name: str, token: Token) -> ast.Expression:
        if name.upper() in NON_DETERMINISTIC:
            raise self._error(
                f"{name}() cannot be used in a control",
                remedy=(
                    "A control that reads the clock or a random source produces a "
                    "different verdict each time it runs, so its evidence cannot be "
                    "replayed. Use $business_date, which the run supplies and the "
                    "evidence records."
                ),
                token=token,
            )
        self._expect_punctuation("(")
        distinct = bool(self._match_keyword("DISTINCT"))
        arguments: list[ast.Expression] = []
        if self._peek.is_operator("*"):
            self._advance()
        elif not self._peek.is_punctuation(")"):
            arguments.append(self._expression())
            while self._peek.is_punctuation(","):
                self._advance()
                arguments.append(self._expression())
        self._expect_punctuation(")")
        return ast.FunctionCall(
            name=name.upper() if name.upper() in AGGREGATES else name,
            arguments=tuple(arguments),
            distinct=distinct,
            position=token.position,
        )

    def _list_expression(self) -> ast.ListExpression:
        start = self._expect_punctuation("(").position
        if self._peek.is_punctuation(")"):
            # Caught here rather than by the linter: an empty set fails every
            # row, so it is a mistake rather than a style, and the caret can
            # point at the brackets.
            raise self._error(
                "an empty set of values",
                remedy=(
                    "List the permitted values, as in IN ('GBP', 'USD'). To require a "
                    "column to be empty, write IS NULL."
                ),
            )
        items = [self._expression()]
        while self._peek.is_punctuation(","):
            self._advance()
            items.append(self._expression())
        self._expect_punctuation(")")
        return ast.ListExpression(items=tuple(items), position=start)

    def _column_list(self) -> tuple[ast.ColumnRef, ...]:
        self._expect_punctuation("(")
        columns = [self._column()]
        while self._peek.is_punctuation(","):
            self._advance()
            columns.append(self._column())
        self._expect_punctuation(")")
        return tuple(columns)

    def _column(self) -> ast.ColumnRef:
        token = self._peek
        name = self._name("a column name")
        if self._peek.is_punctuation("."):
            self._advance()
            return ast.ColumnRef(
                name=self._name("a column name after the dot"),
                dataset=name,
                position=token.position,
            )
        return ast.ColumnRef(name=name, position=token.position)

    def _bounds(self) -> tuple[int | None, int | None]:
        if self._match_keyword("BETWEEN"):
            lower = self._integer("the smallest acceptable count")
            self._expect_keyword("AND")
            return lower, self._integer("the largest acceptable count")
        if self._match_keyword("AT"):
            word = self._expect_keyword_of("LEAST", "MOST")
            value = self._integer("a count")
            return (value, None) if word.upper == "LEAST" else (None, value)
        raise self._error(
            f"expected BETWEEN or AT LEAST/MOST after ROW COUNT, found {self._peek.describe}",
            remedy="For example: HAS ROW COUNT BETWEEN 900000 AND 1200000",
        )

    def _duration_minutes(self) -> int:
        value = self._integer("how long")
        unit = self._advance()
        factors = {
            "MINUTE": 1,
            "MINUTES": 1,
            "HOUR": 60,
            "HOURS": 60,
            "DAY": 1440,
            "DAYS": 1440,
        }
        if unit.upper not in factors:
            raise self._error(
                f"expected MINUTES, HOURS or DAYS and found {unit.describe}",
                remedy="For example: WITHIN 30 MINUTES, or WITHIN 4 HOURS.",
                token=unit,
            )
        return value * factors[unit.upper]

    def _pattern(self) -> ast.Literal:
        token = self._peek
        if token.kind is not TokenKind.REGEX:
            raise self._error(
                f"expected a pattern after MATCHES and found {token.describe}",
                remedy="Patterns are written between slashes: /^[A-Z]{2}[0-9]{10}$/",
            )
        self._advance()
        return ast.Literal(value=token.value, literal_type="pattern", position=token.position)

    def _reference_literal(self) -> ast.Literal:
        """A named thing: a codelist, a semantic type, a format."""
        token = self._advance()
        if token.kind not in (TokenKind.IDENTIFIER, TokenKind.KEYWORD, TokenKind.STRING):
            raise self._error(
                f"expected a name and found {token.describe}",
                remedy="For example: IN CODELIST iso4217, or IS VALID ISIN.",
                token=token,
            )
        return ast.Literal(
            value=token.value or token.text, literal_type="text", position=token.position
        )

    # -- token handling ----------------------------------------------------

    @property
    def _peek(self) -> Token:
        return self._tokens[self._index]

    @property
    def _previous(self) -> Token:
        return self._tokens[max(0, self._index - 1)]

    @property
    def _at_end(self) -> bool:
        return self._peek.kind is TokenKind.END

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if token.kind is not TokenKind.END:
            self._index += 1
        return token

    def _match_keyword(self, *words: str) -> Token | None:
        if self._peek.is_keyword(*words):
            return self._advance()
        return None

    def _expect_keyword(self, word: str) -> Token:
        if not self._peek.is_keyword(word):
            raise self._error(
                f"expected {word} and found {self._peek.describe}",
                remedy=f"Add {word} here.",
            )
        return self._advance()

    def _expect_keyword_of(self, *words: str) -> Token:
        if not self._peek.is_keyword(*words):
            raise self._error(
                f"expected {' or '.join(words)} and found {self._peek.describe}",
                remedy=f"Use one of: {', '.join(words)}.",
            )
        return self._advance()

    def _expect_punctuation(self, mark: str) -> Token:
        if not self._peek.is_punctuation(mark):
            raise self._error(
                f"expected {mark!r} and found {self._peek.describe}",
                remedy=f"Add {mark!r} here.",
            )
        return self._advance()

    def _name(self, what: str) -> str:
        """A dataset or column name.

        Keywords are accepted here, because they are recognised rather than
        reserved: a bank's columns really are called ``source``, ``severity``
        and ``on``, and refusing them would make the language unusable on the
        first real dataset it met.
        """
        token = self._peek
        if token.kind not in (TokenKind.IDENTIFIER, TokenKind.KEYWORD):
            raise self._error(
                f"expected {what} and found {token.describe}",
                remedy=(
                    "Names are written plainly, or in double quotes if they contain "
                    'spaces: "risk positions".'
                ),
            )
        self._advance()
        return token.value or token.text

    def _text(self, what: str) -> str:
        token = self._peek
        if token.kind is not TokenKind.STRING:
            raise self._error(
                f"expected {what}, in quotes, and found {token.describe}",
                remedy="Quoted text is written between single quotes: 'like this'.",
            )
        self._advance()
        return token.value

    def _integer(self, what: str) -> int:
        token = self._number_token(what)
        if "." in token.text or token.text.endswith("%"):
            raise self._error(
                f"expected {what} as a whole number and found {token.text!r}",
                remedy="Use a whole number here.",
                token=token,
            )
        return int(token.text)

    def _number_token(self, what: str = "a number") -> Token:
        token = self._peek
        if token.kind is not TokenKind.NUMBER:
            raise self._error(
                f"expected {what} and found {token.describe}",
                remedy="Write a number here.",
            )
        return self._advance()

    def _require_subject(self, subject: ast.Expression | None, token: Token) -> ast.Expression:
        if subject is None:
            raise self._error(
                "this check is about a column, but no column was named",
                remedy=(
                    "Name the column: CHECK positions.notional_amount IS NOT NULL. "
                    "Checks about the whole dataset use HAS: HAS ROW COUNT, "
                    "HAS UNIQUE KEY."
                ),
                token=token,
            )
        return subject

    def _error(self, message: str, *, remedy: str, token: Token | None = None) -> PqlSyntaxError:
        """Build the error. Raised at the call site, so control flow is visible.

        Returning it rather than raising it here keeps every place the parser
        gives up spelled ``raise`` where it happens, instead of hidden behind a
        helper that a reader has to look up to know the function ends there.
        """
        offending = token or self._peek
        return PqlSyntaxError(
            message, remedy=remedy, position=offending.position, source=self.source
        )


def _as_columns(expression: ast.Expression) -> tuple[ast.ColumnRef, ...] | None:
    """Read an expression as a column list, for ``a, b DETERMINES c``.

    ``DETERMINES`` takes columns on both sides, but they arrive through the
    expression parser, so a single column looks like a ColumnRef and several
    look like nothing the expression grammar has a node for. Rather than
    complicate the grammar for one construct, the shapes that could be a column
    list are recognised here and everything else is refused with a clear
    message.
    """
    if isinstance(expression, ast.ColumnRef):
        return (expression,)
    if isinstance(expression, ast.ListExpression) and all(
        isinstance(item, ast.ColumnRef) for item in expression.items
    ):
        return tuple(item for item in expression.items if isinstance(item, ast.ColumnRef))
    return None


def parse(source: str) -> ast.Program:
    """Parse a whole PQL document."""
    return Parser(source).parse()


def parse_control(source: str) -> ast.Control:
    """Parse exactly one control."""
    return Parser(source).parse_control()
