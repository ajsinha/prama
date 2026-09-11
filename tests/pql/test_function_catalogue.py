"""The function catalogue, and the agreement it exists to enforce.

Before the catalogue, an unknown function name passed straight through to SQL
while the reference interpreter returned UNKNOWN for anything it did not
recognise — so the compiler and the independent check that exists to catch the
compiler being wrong silently disagreed. These tests are what stops that
returning.

The one that matters most is ``TestEveryFunctionAgreesWithItsSql``: it runs
every function's *SQL* against its *reference implementation* on the same
inputs, on every engine that claims it. A function whose two halves drift apart
fails here rather than in somebody's evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import functools
import os
import sqlite3
from decimal import Decimal
from typing import Any

import duckdb
import pytest

from prama.core.errors import ValidationError
from prama.pql.functions import ENGINES, UNSET, VOLATILE, Function, FunctionRegistry
from prama.pql.library import FUNCTIONS
from prama.pql.types import BOOLEAN, NUMBER, TEMPORAL, TEXT, UNKNOWN

#: Inputs per argument family. Chosen to include the values that break things:
#: an empty string, a negative, a zero divisor, a value with a decimal that
#: rounds differently under half-even.
SAMPLES: dict[str, list[Any]] = {
    TEXT: ["Acme", " padded ", "", "GB0002634946"],
    NUMBER: [Decimal("2.675"), Decimal("-7.5"), Decimal("0"), Decimal("1000")],
    BOOLEAN: [True, False],
    TEMPORAL: ["2026-09-08", "2024-02-29"],
    UNKNOWN: ["Acme", Decimal("3")],
}


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, Decimal):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _cases(function: Function) -> list[list[Any]]:
    """A handful of argument tuples for one function.

    Small on purpose: the corpus is here to catch a lowering that disagrees
    with its reference implementation, not to prove a function correct. One
    disagreement is enough to fail, and a thousand cases would only make the
    failure harder to read.
    """
    low, high = function.arity
    count = min(max(low, 1), 3 if high > 3 else high)
    families = [function.expected_type(i) for i in range(count)]
    rows: list[list[Any]] = []
    for index in range(4):
        row = []
        for position, family in enumerate(families):
            pool = SAMPLES.get(family) or SAMPLES[UNKNOWN]
            # Second and third arguments of the text-slicing functions are
            # lengths; a 1000 there produces nothing interesting and a negative
            # is not a case anybody writes.
            if (
                family is NUMBER
                and position > 0
                and function.name in ("LEFT", "RIGHT", "MID", "ROUND")
            ):
                pool = [Decimal(2), Decimal(1)]
            row.append(pool[index % len(pool)])
        rows.append(row)
    return rows


@functools.lru_cache(maxsize=1)
def _postgres() -> Any:
    """One connection for the whole module.

    Per-call would be several hundred connections for twenty-five functions
    across their cases, which is slow enough that somebody would stop running
    it with a DSN set — and a conformance test nobody runs is not one.
    """
    import psycopg

    return psycopg.connect(POSTGRES_DSN)


def _run(engine: str, sql: str) -> Any:
    if engine == "postgresql":
        connection = _postgres()
        with connection.cursor() as cursor:
            try:
                cursor.execute(f"SELECT {sql}")
                return cursor.fetchone()[0]
            finally:
                # A failed statement aborts the transaction, and every
                # subsequent case in this connection would then fail with
                # "current transaction is aborted" — reporting one broken
                # lowering as twenty-five.
                connection.rollback()
    if engine == "duckdb":
        with duckdb.connect(":memory:") as connection:
            return connection.execute(f"SELECT {sql}").fetchone()[0]
    connection = sqlite3.connect(":memory:")
    try:
        from prama.connect.sources.query import register_regexp

        register_regexp(connection)
        return connection.execute(f"SELECT {sql}").fetchone()[0]
    finally:
        connection.close()


def _comparable(value: Any) -> Any:
    """Both sides reduced to something that can be compared honestly.

    Numbers to Decimal, because a driver returning 2.68 as a float and a
    reference implementation returning Decimal('2.68') agree about the number
    and disagree about the type. Booleans to bool, because SQLite has none.
    """
    if value is None or value is UNSET:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value)).normalize()
    return str(value)


#: Engines a test can actually reach. DuckDB and SQLite are in-process and
#: always run. PostgreSQL joins when PRAMA_TEST_POSTGRES_DSN names a server, and
#: when it does this stops being a check that the SQL *renders* and becomes a
#: check that it *means the same thing* — which is the only version of this test
#: worth the name. Without a server the PostgreSQL lowerings are still rendered,
#: so a template with a hole in it fails either way; what a server adds is
#: everything a renderer cannot see, which is most of it.
POSTGRES_DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "")
LOCAL_ENGINES = ("duckdb", "sqlite")
EXECUTED_ENGINES = (*LOCAL_ENGINES, "postgresql") if POSTGRES_DSN else LOCAL_ENGINES


class TestTheCatalogueIsComplete:
    @pytest.mark.parametrize("name", FUNCTIONS.names())
    def test_every_function_has_a_reference_implementation(self, name: str) -> None:
        """A required field, so a function without one does not construct.

        This is the structural guarantee: the compiler cannot acquire a
        function its independent check does not have.
        """
        assert callable(FUNCTIONS.get(name).evaluate)

    @pytest.mark.parametrize("name", FUNCTIONS.names())
    def test_every_function_renders_on_every_engine_it_claims(self, name: str) -> None:
        function = FUNCTIONS.get(name)
        arguments = [f"a{i}" for i in range(function.arity[0])]
        for engine in ENGINES:
            if not function.supports(engine):
                continue
            rendered = function.render(engine, arguments)
            assert rendered and "{" not in rendered, f"{name} on {engine}: {rendered}"

    @pytest.mark.parametrize("name", FUNCTIONS.names())
    def test_every_function_says_what_it_is_for(self, name: str) -> None:
        assert FUNCTIONS.get(name).summary.strip()

    def test_a_function_with_no_sql_form_cannot_be_declared(self) -> None:
        with pytest.raises(ValidationError, match="no SQL form"):
            Function(
                name="NOPE",
                summary="s",
                arity=(1, 1),
                returns=TEXT,
                argument_types=(TEXT,),
                evaluate=lambda a: a[0],
            )


class TestEveryFunctionAgreesWithItsSql:
    """The test the catalogue exists for.

    Each function's SQL is executed and compared with its own reference
    implementation on the same inputs. A lowering that drifts from its
    reference — a rounding mode, an argument order, an off-by-one in a
    substring — fails here rather than in somebody's evidence six months later.
    """

    @pytest.mark.parametrize("engine", EXECUTED_ENGINES)
    @pytest.mark.parametrize("name", FUNCTIONS.names())
    def test_each_function(self, name: str, engine: str) -> None:
        function = FUNCTIONS.get(name)
        if not function.supports(engine):
            pytest.skip(f"{name} is not claimed on {engine}")
        disagreements = []
        for arguments in _cases(function):
            expected = _comparable(function.evaluate(list(arguments)))
            sql = function.render(engine, [_sql_literal(a) for a in arguments])
            try:
                actual = _comparable(_run(engine, sql))
            except Exception as exc:  # a lowering that will not run is a failure
                disagreements.append(f"{arguments}: SQL failed — {exc}")
                continue
            if expected != actual:
                disagreements.append(f"{arguments}: reference={expected!r} sql={actual!r}  [{sql}]")
        assert not disagreements, f"{name} on {engine}:\n  " + "\n  ".join(disagreements)


class TestUnknownNamesAreRefused:
    def test_an_unknown_function_names_the_ones_that_exist(self) -> None:
        """It used to compile straight through to SQL and fail at execution —
        or worse, succeed on an engine that happened to have a function of that
        name and mean something else."""
        with pytest.raises(ValidationError, match="no function called"):
            FUNCTIONS.get("NONSENSE_FN")

    def test_the_refusal_lists_what_is_available(self) -> None:
        with pytest.raises(ValidationError) as caught:
            FUNCTIONS.get("VLOOKUP")
        assert "UPPER" in str(caught.value)

    def test_find_returns_nothing_rather_than_raising(self) -> None:
        assert FUNCTIONS.find("NONSENSE_FN") is None
        assert FUNCTIONS.find("upper") is not None


class TestVolatileFunctionsAreRefused:
    """Not "unsupported" — refused. Each is expressible on every engine, and
    each would make a control unreplayable, which is worse than missing."""

    @pytest.mark.parametrize("name", sorted(VOLATILE))
    def test_by_name(self, name: str) -> None:
        with pytest.raises(ValidationError, match="refused"):
            FUNCTIONS.get(name)

    @pytest.mark.parametrize("name", sorted(VOLATILE))
    def test_and_cannot_be_registered_either(self, name: str) -> None:
        registry = FunctionRegistry()
        with pytest.raises(ValidationError, match="cannot be a control function"):
            registry.register(
                Function(
                    name=name,
                    summary="s",
                    arity=(0, 0),
                    returns=NUMBER,
                    argument_types=(),
                    sql="1",
                    evaluate=lambda *_: 1,
                )
            )

    def test_the_reason_is_replay_not_capability(self) -> None:
        with pytest.raises(ValidationError) as caught:
            FUNCTIONS.get("NOW")
        assert "replay" in str(caught.value)


class TestUnknownPropagation:
    def test_most_functions_are_strict(self) -> None:
        """A function of an unknown is unknown. Returning 0 for LENGTH(NULL)
        would make a length check silently pass on every null."""
        assert FUNCTIONS.get("UPPER").strict_unknown
        assert FUNCTIONS.get("ROUND").strict_unknown

    def test_the_exceptions_are_the_ones_whose_job_is_unknowns(self) -> None:
        for name in ("IF", "ISBLANK", "COALESCE", "IFBLANK", "ISNUMBER"):
            assert not FUNCTIONS.get(name).strict_unknown, name

    def test_isblank_answers_rather_than_propagating(self) -> None:
        assert FUNCTIONS.get("ISBLANK").evaluate([None]) is True
        assert FUNCTIONS.get("ISBLANK").evaluate([""]) is True
        assert FUNCTIONS.get("ISBLANK").evaluate(["x"]) is False

    def test_if_with_an_undetermined_condition_is_undetermined(self) -> None:
        """Excel takes the FALSE branch. Choosing one here would invent an
        answer, and the branch it would invent is the one that passes."""
        assert FUNCTIONS.get("IF").evaluate([UNSET, "a", "b"]) is UNSET

    def test_a_zero_divisor_is_unknown_not_an_error_value(self) -> None:
        assert FUNCTIONS.get("MOD").evaluate([Decimal(5), Decimal(0)]) is UNSET


class TestTheDivergencesAreStated:
    def test_every_divergence_says_what_excel_does(self) -> None:
        """A divergence discovered in production is worth less than one stated
        on the control, and one stated vaguely is worth nothing."""
        for name in FUNCTIONS.names():
            note = FUNCTIONS.get(name).excel_divergence
            if note:
                assert "Excel" in note, name
                assert len(note) > 40, f"{name}: too vague to act on"

    def test_rounding_is_half_up_because_money(self) -> None:
        """Several engines round half to even by default. This one runs over
        settlement amounts."""
        assert FUNCTIONS.get("ROUND").evaluate([Decimal("2.675"), Decimal(2)]) == Decimal("2.68")
        assert FUNCTIONS.get("ROUND").evaluate([Decimal("2.665"), Decimal(2)]) == Decimal("2.67")

    @pytest.mark.parametrize("engine", LOCAL_ENGINES)
    def test_rounding_does_not_round_twice(self, engine: str) -> None:
        """The bug this test was written for, found on real data.

        A bare ``CAST(x AS NUMERIC)`` is arbitrary precision in PostgreSQL and
        ``DECIMAL(18,3)`` in DuckDB. Rounding through three decimals and then to
        two is a double rounding: ``1953193.4649`` becomes ``.465`` and then
        ``.47``, where one correct rounding gives ``.46``.

        It reported 131 rows in 3,000 as a cent out when they were not — a
        false alarm on the control people trust most, in the direction that
        makes a clean book look broken.
        """
        function = FUNCTIONS.get("ROUND")
        if not function.supports(engine):
            pytest.skip(f"ROUND is refused on {engine}")
        value = Decimal("1953193.4649")
        expected = _comparable(function.evaluate([value, Decimal(2)]))
        actual = _comparable(_run(engine, function.render(engine, [str(value), "2"])))
        assert expected == Decimal("1953193.46")
        assert actual == expected, f"{engine} rounded twice: {actual}"

    def test_a_boolean_is_not_a_number(self) -> None:
        """Excel's TRUE + 1 is 2. A boolean in an arithmetic position here is a
        mistake worth surfacing, not a 1 worth guessing."""
        assert FUNCTIONS.get("ABS").evaluate([True]) is UNSET
