"""The shipped functions.

Chosen by what a finance person actually writes in a spreadsheet, and bounded
by what compiles to SQL on every engine Prama targets. Each carries its
reference implementation beside its lowering, so the two are written together
and read together — which is the only reliable way to keep them agreeing.

Where Prama differs from a spreadsheet, the function says so in
``excel_divergence`` and ``control explain`` prints it. There are five such
divergences in this file and every one of them is deliberate:

* **No implicit coercion.** Excel's ``"1" + 1`` is ``2``. Here it is a type
  error at check time, because a control that silently reinterprets its data is
  a control whose verdict nobody can reason about.
* **A blank is unknown, not zero.** Excel's blank is ``0`` in arithmetic and
  ``""`` in concatenation. Prama's is ``UNKNOWN``, and unknown counts as a
  violation — the inversion of SQL's default that the whole language rests on.
* **No error values.** Excel has ``#DIV/0!`` and ``#VALUE!`` and they propagate
  by their own rules. Division by zero here is unknown, and ``IFERROR`` does not
  exist because there is no error to catch.
* **Money is exact.** ``ROUND`` uses half-up, which is what a settlement system
  does, rather than the banker's rounding some engines default to.
* **Dates are ISO text.** No serial numbers, so no 1900 leap-year bug and no
  arithmetic on dates that silently means days.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

from prama.pql.families import BOOLEAN, NUMBER, TEMPORAL, TEXT, UNKNOWN
from prama.pql.functions import (
    UNSET,
    VARIADIC,
    Function,
    FunctionRegistry,
)

# ---------------------------------------------------------------------------
# Helpers for the reference implementations
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _number(value: Any) -> Decimal | None:
    """A value as an exact number, or nothing.

    ``Decimal``, not ``float``. These functions run over money, and a
    reconciliation that summed in binary floating point would manufacture
    exactly the small discrepancies it exists to detect.
    """
    if isinstance(value, bool):
        # Excel treats TRUE as 1. Prama does not: a boolean in an arithmetic
        # position is a mistake worth surfacing, not a 1 worth guessing.
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    return None


def _strict_number(value: Any) -> Any:
    number = _number(value)
    return UNSET if number is None else number


def _is_blank(value: Any) -> bool:
    return value is None or value is UNSET or (isinstance(value, str) and not value.strip())


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

TEXT_FUNCTIONS = (
    Function(
        name="UPPER",
        summary="The text in upper case.",
        arity=(1, 1),
        returns=TEXT,
        argument_types=(TEXT,),
        sql="UPPER({0})",
        evaluate=lambda a: _text(a[0]).upper(),
    ),
    Function(
        name="LOWER",
        summary="The text in lower case.",
        arity=(1, 1),
        returns=TEXT,
        argument_types=(TEXT,),
        sql="LOWER({0})",
        evaluate=lambda a: _text(a[0]).lower(),
    ),
    Function(
        name="TRIM",
        summary="The text without leading or trailing spaces.",
        arity=(1, 1),
        returns=TEXT,
        argument_types=(TEXT,),
        sql="TRIM({0})",
        evaluate=lambda a: _text(a[0]).strip(),
        excel_divergence=(
            "Excel's TRIM also collapses runs of spaces inside the text; this one "
            "only removes the ends, which is what every SQL engine's TRIM does. "
            "Collapsing interior spaces on one side and not the other would make "
            "the same control give two answers."
        ),
    ),
    Function(
        name="LENGTH",
        summary="How many characters the text has.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(TEXT,),
        sql="LENGTH({0})",
        sql_by_engine={"postgresql": "LENGTH({0})", "sqlite": "LENGTH({0})"},
        evaluate=lambda a: Decimal(len(_text(a[0]))),
        excel_divergence="Excel calls this LEN; both names are accepted.",
    ),
    Function(
        name="LEN",
        summary="How many characters the text has. Excel's name for LENGTH.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(TEXT,),
        sql="LENGTH({0})",
        evaluate=lambda a: Decimal(len(_text(a[0]))),
    ),
    Function(
        name="LEFT",
        summary="The first n characters.",
        arity=(2, 2),
        returns=TEXT,
        argument_types=(TEXT, NUMBER),
        sql="SUBSTR({0}, 1, CAST({1} AS INTEGER))",
        evaluate=lambda a: _text(a[0])[: max(0, int(_number(a[1]) or 0))],
    ),
    Function(
        name="RIGHT",
        summary="The last n characters.",
        arity=(2, 2),
        returns=TEXT,
        argument_types=(TEXT, NUMBER),
        sql="SUBSTR({0}, GREATEST(LENGTH({0}) - CAST({1} AS INTEGER) + 1, 1))",
        sql_by_engine={
            # SQLite has no GREATEST; MAX with two arguments is its scalar form,
            # which is a different function from the aggregate MAX of one.
            "sqlite": "SUBSTR({0}, MAX(LENGTH({0}) - CAST({1} AS INTEGER) + 1, 1))",
        },
        evaluate=lambda a: (
            _text(a[0])[-int(_number(a[1]) or 0) :] if int(_number(a[1]) or 0) > 0 else ""
        ),
    ),
    Function(
        name="MID",
        summary="n characters starting at a position, counting from 1.",
        arity=(3, 3),
        returns=TEXT,
        argument_types=(TEXT, NUMBER, NUMBER),
        sql="SUBSTR({0}, CAST({1} AS INTEGER), CAST({2} AS INTEGER))",
        evaluate=lambda a: _text(a[0])[
            max(0, int(_number(a[1]) or 1) - 1) : max(0, int(_number(a[1]) or 1) - 1)
            + max(0, int(_number(a[2]) or 0))
        ],
    ),
    Function(
        name="SUBSTITUTE",
        summary="Every occurrence of one piece of text replaced by another.",
        arity=(3, 3),
        returns=TEXT,
        argument_types=(TEXT, TEXT, TEXT),
        sql="REPLACE({0}, {1}, {2})",
        evaluate=lambda a: _text(a[0]).replace(_text(a[1]), _text(a[2])),
        excel_divergence=(
            "Excel's SUBSTITUTE takes an optional fourth argument selecting which "
            "occurrence to replace. It is not accepted here: no engine expresses it, "
            "and emulating it would move the work out of SQL and onto every row."
        ),
    ),
    Function(
        name="CONCAT",
        summary="Several pieces of text joined together.",
        arity=(1, VARIADIC),
        returns=TEXT,
        argument_types=(TEXT,),
        sql="CONCAT({*})",
        # SQLite has no CONCAT function; concatenation is the || operator.
        # Rendering a comma-joined list there produced "(a, b, c)" — a row
        # constructor, which parses and means something entirely different.
        sql_by_engine={"sqlite": "({*})"},
        separator_by_engine={"sqlite": " || "},
        evaluate=lambda a: "".join(_text(x) for x in a),
        excel_divergence=(
            "Excel treats a blank as the empty string here, so CONCAT of a blank "
            "succeeds. Prama returns UNKNOWN, which counts as a violation: a "
            "concatenated key silently missing one of its parts is how two different "
            "rows acquire the same identity."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


def _absolute(arguments: list[Any]) -> Any:
    number = _number(arguments[0])
    return UNSET if number is None else abs(number)


def _whole_part(arguments: list[Any]) -> Any:
    number = _number(arguments[0])
    return UNSET if number is None else Decimal(math.floor(number))


def _mod(arguments: list[Any]) -> Any:
    left, right = _number(arguments[0]), _number(arguments[1])
    if left is None or right is None or right == 0:
        return UNSET
    return left % right


def _sign(arguments: list[Any]) -> Any:
    number = _number(arguments[0])
    if number is None:
        return UNSET
    return Decimal(0) if number == 0 else Decimal(1) if number > 0 else Decimal(-1)


def _extreme(arguments: list[Any], *, smallest: bool) -> Any:
    """The smallest or largest, or unknown if any argument is.

    Not "skip the unknowns". Silently ignoring a missing value is how a minimum
    becomes a statement about the rows that happened to be populated rather
    than about the rows there are.
    """
    exact: list[Decimal] = []
    for value in arguments:
        number = _number(value)
        if number is None:
            return UNSET
        exact.append(number)
    return min(exact) if smallest else max(exact)


def _rounded(arguments: list[Any]) -> Any:
    value, places = _number(arguments[0]), _number(arguments[1])
    if value is None or places is None:
        return UNSET
    return _round_half_up(value, int(places))


def _round_half_up(value: Decimal, places: int) -> Decimal:
    """Half away from zero, which is what a settlement system does.

    PostgreSQL rounds NUMERIC half-up and DOUBLE half-even; DuckDB and SQLite
    differ again. Pinning it here and rendering the cast explicitly is what
    makes the same control give the same number on three engines, and it is the
    difference between a hash total that ties and one that is out by a penny
    for reasons nobody can find.
    """
    quantum = Decimal(1).scaleb(-places)
    return value.quantize(quantum, rounding="ROUND_HALF_UP")


NUMBER_FUNCTIONS = (
    Function(
        name="ABS",
        summary="The value without its sign.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(NUMBER,),
        sql="ABS({0})",
        evaluate=_absolute,
    ),
    Function(
        name="ROUND",
        summary="Rounded to n decimal places, half away from zero.",
        arity=(2, 2),
        returns=NUMBER,
        argument_types=(NUMBER, NUMBER),
        # CAST to an exact type first, *with a stated scale*. Rounding a float
        # is engine-dependent and this function runs over money — but the width
        # matters as much as the exactness.
        #
        # A bare ``CAST(x AS NUMERIC)`` is arbitrary precision in PostgreSQL and
        # ``DECIMAL(18,3)`` in DuckDB. Rounding through three decimals and then
        # to two is a **double rounding**: 1953193.4649 becomes .465 and then
        # .47, where one correct rounding gives .46. On a real blotter that was
        # 131 rows in 3,000 reported as a cent out when they were not — a false
        # alarm on exactly the control people trust most.
        sql="ROUND(CAST({0} AS NUMERIC), CAST({1} AS INTEGER))",
        sql_by_engine={
            "duckdb": "ROUND(CAST({0} AS DECIMAL(38,12)), CAST({1} AS INTEGER))",
        },
        # SQLite is refused, and the refusal is not a gap in this file. SQLite
        # has no exact numeric type at all — every number is a double, so the
        # literal 2.675 is already 2.67499999… before ROUND sees it and no
        # template can recover the intended value. It returns 2.67 where every
        # other engine returns 2.68.
        #
        # A penny is exactly the size of error a hash total exists to detect,
        # so approximating here would break reconciliation on the engine where
        # it is hardest to notice. The conformance corpus found this on its
        # first run, which is what the corpus is for.
        unsupported_on=frozenset({"sqlite"}),
        evaluate=_rounded,
        excel_divergence=(
            "Excel rounds half away from zero and so does this. Several SQL engines "
            "round half to even by default, which is why the value is cast to an "
            "exact type first — otherwise the same control gives a different penny "
            "on a different engine. SQLite is refused outright: it has no exact "
            "numeric type, so the value is already wrong before ROUND sees it."
        ),
    ),
    Function(
        name="INT",
        summary="The whole part, rounded down.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(NUMBER,),
        sql="FLOOR({0})",
        evaluate=_whole_part,
        excel_divergence=(
            "Excel's INT rounds towards negative infinity, and so does FLOOR. "
            "TRUNC would round towards zero and disagree on negatives."
        ),
    ),
    Function(
        name="MOD",
        summary="The remainder after division.",
        arity=(2, 2),
        returns=NUMBER,
        argument_types=(NUMBER, NUMBER),
        sql="CASE WHEN {1} = 0 THEN NULL ELSE MOD({0}, {1}) END",
        sql_by_engine={"sqlite": "CASE WHEN {1} = 0 THEN NULL ELSE ({0} % {1}) END"},
        evaluate=_mod,
        excel_divergence=(
            "Excel returns #DIV/0! for a zero divisor. There are no error values "
            "here: the result is UNKNOWN, which counts as a violation rather than "
            "propagating through the rest of the expression."
        ),
    ),
    Function(
        name="SIGN",
        summary="-1, 0 or 1.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(NUMBER,),
        sql="SIGN({0})",
        evaluate=lambda a: (
            (
                Decimal(0)
                if _number(a[0]) == 0
                else Decimal(1)
                if (_number(a[0]) or 0) > 0
                else Decimal(-1)
            )
            if _number(a[0]) is not None
            else UNSET
        ),
    ),
    Function(
        name="MIN",
        summary="The smallest of several values.",
        arity=(2, VARIADIC),
        returns=NUMBER,
        argument_types=(NUMBER,),
        sql="LEAST({*})",
        sql_by_engine={"sqlite": "MIN({*})"},
        evaluate=lambda a: _extreme(a, smallest=True),
        excel_divergence=(
            "Excel's MIN over a range ignores blanks and text. This is the scalar "
            "form over named columns: an unknown argument makes the result unknown, "
            "because silently skipping a missing value is how a minimum becomes a "
            "statement about the rows that happened to be populated."
        ),
    ),
    Function(
        name="MAX",
        summary="The largest of several values.",
        arity=(2, VARIADIC),
        returns=NUMBER,
        argument_types=(NUMBER,),
        sql="GREATEST({*})",
        sql_by_engine={"sqlite": "MAX({*})"},
        evaluate=lambda a: _extreme(a, smallest=False),
    ),
)


# ---------------------------------------------------------------------------
# Logic and null handling
# ---------------------------------------------------------------------------


def _if(arguments: list[Any]) -> Any:
    condition = arguments[0]
    if condition is UNSET or condition is None:
        # Not "take the false branch". A condition nobody can evaluate makes
        # the whole expression undetermined, and choosing a branch would be
        # inventing an answer.
        return UNSET
    return arguments[1] if condition else arguments[2]


def _coalesce(arguments: list[Any]) -> Any:
    for value in arguments:
        if value is not None and value is not UNSET:
            return value
    return UNSET


LOGIC_FUNCTIONS = (
    Function(
        name="IF",
        summary="One value when the condition holds, another when it does not.",
        arity=(3, 3),
        returns=UNKNOWN,
        argument_types=(BOOLEAN, UNKNOWN, UNKNOWN),
        sql="CASE WHEN {0} THEN {1} ELSE {2} END",
        evaluate=_if,
        # Not strict: the whole purpose is to choose between two values, and a
        # branch not taken must not make the result unknown.
        strict_unknown=False,
        excel_divergence=(
            "Excel's IF takes the FALSE branch when the condition is blank. Here an "
            "undetermined condition makes the whole expression undetermined: "
            "choosing a branch would be inventing an answer, and the branch it "
            "would invent is the one that passes."
        ),
    ),
    Function(
        name="IFBLANK",
        summary="A substitute value when the first is missing.",
        arity=(2, 2),
        returns=UNKNOWN,
        argument_types=(UNKNOWN, UNKNOWN),
        sql="COALESCE({0}, {1})",
        evaluate=_coalesce,
        strict_unknown=False,
        excel_divergence=(
            "Excel has no direct equivalent; the usual spelling is IF(ISBLANK(x), y, x). "
            "IFERROR is deliberately absent — there are no error values to catch, "
            "because a failed computation is UNKNOWN and UNKNOWN is a violation "
            "rather than something to swallow."
        ),
    ),
    Function(
        name="COALESCE",
        summary="The first value that is present.",
        arity=(2, VARIADIC),
        returns=UNKNOWN,
        argument_types=(UNKNOWN,),
        sql="COALESCE({*})",
        evaluate=_coalesce,
        strict_unknown=False,
    ),
    Function(
        name="ISBLANK",
        summary="Whether the value is missing or empty.",
        arity=(1, 1),
        returns=BOOLEAN,
        argument_types=(UNKNOWN,),
        sql="({0} IS NULL OR TRIM(CAST({0} AS VARCHAR)) = '')",
        evaluate=lambda a: _is_blank(a[0]),
        # The one function whose entire job is to answer a question about an
        # unknown. Strictness here would make it always return unknown.
        strict_unknown=False,
        excel_divergence=(
            "Excel's ISBLANK is false for a cell containing an empty string. This "
            "one is true for both, because in a database an empty string and a NULL "
            "are the same defect wearing two hats, and a control that caught one "
            "and not the other would be turned off."
        ),
    ),
    Function(
        name="ISNUMBER",
        summary="Whether the value is a number.",
        arity=(1, 1),
        returns=BOOLEAN,
        argument_types=(UNKNOWN,),
        # No engine-portable "is this castable"; a regex over the text form is
        # the one construction all three agree on.
        sql="(CAST({0} AS VARCHAR) ~ '^-?[0-9]+(\\.[0-9]+)?$')",
        sql_by_engine={
            "duckdb": "regexp_matches(CAST({0} AS VARCHAR), '^-?[0-9]+(\\.[0-9]+)?$')",
            "sqlite": "(CAST({0} AS VARCHAR) REGEXP '^-?[0-9]+(\\.[0-9]+)?$')",
        },
        requires=frozenset({"pushdown.regex"}),
        evaluate=lambda a: (
            not _is_blank(a[0])
            and re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", _text(a[0]).strip()) is not None
        ),
        strict_unknown=False,
    ),
)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _date_part(value: Any, group: int) -> Any:
    match = _ISO_DATE.match(_text(value).strip())
    return Decimal(match.group(group)) if match else UNSET


DATE_FUNCTIONS = (
    Function(
        name="YEAR",
        summary="The year of an ISO-8601 date.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(TEMPORAL,),
        sql="CAST(SUBSTR(CAST({0} AS VARCHAR), 1, 4) AS INTEGER)",
        evaluate=lambda a: _date_part(a[0], 1),
        excel_divergence=(
            "Excel's YEAR takes a serial number and inherits the 1900 leap-year bug. "
            "Dates here are ISO-8601 text throughout, so there is no serial number "
            "and no bug — and no arithmetic on dates that silently means days."
        ),
    ),
    Function(
        name="MONTH",
        summary="The month of an ISO-8601 date, 1 to 12.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(TEMPORAL,),
        sql="CAST(SUBSTR(CAST({0} AS VARCHAR), 6, 2) AS INTEGER)",
        evaluate=lambda a: _date_part(a[0], 2),
    ),
    Function(
        name="DAY",
        summary="The day of the month of an ISO-8601 date.",
        arity=(1, 1),
        returns=NUMBER,
        argument_types=(TEMPORAL,),
        sql="CAST(SUBSTR(CAST({0} AS VARCHAR), 9, 2) AS INTEGER)",
        evaluate=lambda a: _date_part(a[0], 3),
    ),
)


def default_registry() -> FunctionRegistry:
    """Everything Prama ships. A deployment may add to it; nothing is removed."""
    registry = FunctionRegistry()
    for function in (
        *TEXT_FUNCTIONS,
        *NUMBER_FUNCTIONS,
        *LOGIC_FUNCTIONS,
        *DATE_FUNCTIONS,
    ):
        registry.register(function)
    return registry


#: The catalogue every part of Prama consults.
FUNCTIONS = default_registry()
