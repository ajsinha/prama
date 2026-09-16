"""A `Decimal` reaches SQL as a number, not as quoted text.

QA round 4, `BE-006` (P1) and `BE-007`. `SqlDialect.literal` tested
`isinstance(value, int | float)` and sent everything else to the string branch.
`Decimal` is not an `int` or a `float`, so it was emitted **quoted**.

**That is not a cosmetic type change, and the triage understated it.** A quoted
number makes the comparison *lexical*. Measured against real engines:

    SELECT '9.0' > '10.0'   -->  true    on DuckDB and on SQLite
    SELECT  9.0  >  10.0    -->  false

So a control reading `amount > 10.00`, written with the `Decimal` this codebase
uses for money everywhere else, **passes rows of nine pounds** — and reports a
verdict, on financial data, with no error anywhere. Of everything this round
turned up, this is the one that produces a wrong answer rather than a crash, a
false alarm, or an unhelpful message.

`BE-007`: `repr(float("inf"))` is the Python string `inf`, which parses as SQL
on none of the three engines.

**What a careless version of this test would assert.** `"1.5" in rendered` —
true whether the literal is quoted or not, which is exactly the difference. The
assertion has to be on the quoting, and better still on the ordering the quoting
changes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.backend.dialect import dialect
from prama.core.errors import ValidationError

ENGINES = ("postgresql", "duckdb", "sqlite")


@pytest.mark.parametrize("engine", ENGINES)
def test_a_decimal_is_not_quoted(engine: str) -> None:
    rendered = dialect(engine).literal(Decimal("10.00"))
    assert "'" not in rendered, (
        f"{engine} renders Decimal('10.00') as {rendered} — quoted, so the engine "
        "compares it as text and 9.0 > 10.0 is true"
    )
    assert rendered == "10.00", f"the value changed on the way through: {rendered}"


@pytest.mark.parametrize("engine", ENGINES)
def test_the_scale_survives(engine: str) -> None:
    """`Decimal("10.00")` is not `10.0`; money carries its scale.

    Rendering through `float` would pass the quoting assertion above and throw
    the scale away, which is the repair somebody reaches for first.
    """
    assert dialect(engine).literal(Decimal("10.00")) == "10.00"
    assert dialect(engine).literal(Decimal("0.1")) == "0.1"


def test_the_ordering_it_was_getting_wrong() -> None:
    """The consequence, asserted against a real engine rather than argued.

    The defect is not the quote character; it is that the quote changes the
    answer. This runs both spellings through DuckDB and requires the numeric one.
    """
    duckdb = pytest.importorskip("duckdb")
    connection = duckdb.connect()
    literal = dialect("duckdb").literal

    nine, ten = literal(Decimal("9.0")), literal(Decimal("10.0"))
    answer = connection.execute(f"SELECT {nine} > {ten}").fetchone()[0]
    connection.close()

    assert answer is False, (
        f"DuckDB says {nine} > {ten} is {answer}. As text that is true, which is "
        "how a control on an amount column passes rows below its threshold."
    )


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "value",
    [float("inf"), float("-inf"), float("nan"), Decimal("NaN"), Decimal("Infinity")],
    ids=["inf", "-inf", "nan", "decimal-nan", "decimal-inf"],
)
def test_a_non_finite_number_is_refused(engine: str, value: object) -> None:
    """`BE-007`. `repr(inf)` is `inf`, which is not SQL anywhere."""
    with pytest.raises(ValidationError):
        dialect(engine).literal(value)


@pytest.mark.parametrize("engine", ENGINES)
def test_everything_else_renders_as_it_did(engine: str) -> None:
    """The counterfactual.

    `literal` is on the path of every compiled control, so a repair here is one
    of the easiest places to break something far away. These are the branches
    that were already right.
    """
    rendering = dialect(engine).literal
    assert rendering(None) == "NULL"
    assert rendering(10) == "10"
    assert rendering(1.5) == "1.5"
    assert rendering("text") == "'text'"
    assert rendering("it's") == "'it''s'", "quote escaping is gone"
    assert rendering(True) == dialect(engine).boolean(True)
