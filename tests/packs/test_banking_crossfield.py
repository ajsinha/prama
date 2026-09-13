"""Cross-field banking checks: the defects a column cannot see.

Two halves, and the second is the one that makes the first trustworthy.

The reference implementation is tested directly, on values chosen because they
are individually valid and jointly wrong — a German IBAN with a French BIC, a
yen amount with two decimal places. Every one of those passes every single-field
validator in the product.

Then the same cases are compiled to SQL and run in DuckDB, and the two answers
are required to agree. A function whose SQL and reference implementation
disagree is worse than one with no SQL at all: the compiler and its independent
check are the whole basis for believing a verdict, and a silent divergence
removes it while looking like coverage.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from prama.backend import compile_for
from prama.ir.resolve import resolved
from prama.packs.banking.crossfield import BANKING_FUNCTIONS, install
from prama.pql import parse_control
from prama.pql.functions import UNSET

duckdb = pytest.importorskip("duckdb")


@pytest.fixture(scope="module", autouse=True)
def _installed() -> None:
    from prama.pql.library import FUNCTIONS

    if "IBAN_BIC_CONSISTENT" not in FUNCTIONS:
        install()


def _run(name: str, args: list) -> object:
    from prama.pql.library import FUNCTIONS

    function = FUNCTIONS.find(name)
    assert function is not None
    return function.evaluate(args)


class TestIbanAgainstBic:
    """Both identifiers are valid. The payment is still wrong."""

    def test_matching_countries_pass(self) -> None:
        assert _run("IBAN_BIC_CONSISTENT", ["DE89370400440532013000", "COBADEFFXXX"])

    def test_a_german_iban_with_a_french_bic_fails(self) -> None:
        """The case the whole module exists for: a mod-97-valid IBAN, a
        well-formed BIC, and money routed to a bank that does not hold the
        account."""
        assert _run("IBAN_BIC_CONSISTENT", ["DE89370400440532013000", "BNPAFRPPXXX"]) is False

    def test_case_does_not_matter(self) -> None:
        assert _run("IBAN_BIC_CONSISTENT", ["de89370400440532013000", "cobadeffxxx"])

    def test_a_malformed_identifier_is_unknown_not_inconsistent(self) -> None:
        """Answering False would report one defect as two and send it to the
        wrong person: a truncated IBAN is the format control's finding."""
        assert _run("IBAN_BIC_CONSISTENT", ["D", "COBADEFFXXX"]) is UNSET
        assert _run("IBAN_BIC_CONSISTENT", [None, "COBADEFFXXX"]) is UNSET


class TestMinorUnits:
    def test_a_yen_amount_with_decimals_fails(self) -> None:
        """JPY has no minor unit. 1050.75 JPY is a number no yen amount can
        take, and every downstream sum inherits it."""
        assert _run("MINOR_UNITS_OK", [1050.75, "JPY"]) is False

    def test_a_whole_yen_amount_passes(self) -> None:
        assert _run("MINOR_UNITS_OK", [1050, "JPY"])

    def test_a_euro_amount_with_decimals_passes(self) -> None:
        """Two places is right for most currencies, and this is not the place
        to enumerate the exceptions to that."""
        assert _run("MINOR_UNITS_OK", [1050.75, "EUR"])

    @pytest.mark.parametrize("currency", ["JPY", "KRW", "CLP", "VND", "XOF"])
    def test_the_list_is_iso_4217_rather_than_folklore(self, currency: str) -> None:
        assert _run("MINOR_UNITS_OK", [10.5, currency]) is False

    def test_an_unparseable_amount_is_unknown(self) -> None:
        assert _run("MINOR_UNITS_OK", ["not a number", "JPY"]) is UNSET


class TestSettlementOrder:
    def test_settlement_after_trade_passes(self) -> None:
        assert _run("SETTLES_AFTER_TRADE", ["2026-09-01", "2026-09-03"])

    def test_same_day_settlement_passes(self) -> None:
        assert _run("SETTLES_AFTER_TRADE", ["2026-09-01", "2026-09-01"])

    def test_settlement_before_trade_fails(self) -> None:
        """Almost always a date parsed in the wrong order, and a system that
        accepted it has been silently mis-ageing positions."""
        assert _run("SETTLES_AFTER_TRADE", ["2026-09-05", "2026-09-01"]) is False


class TestSignAgainstSide:
    def test_a_positive_buy_passes(self) -> None:
        assert _run("SIGN_MATCHES_SIDE", ["BUY", 10])

    def test_a_negative_sell_passes(self) -> None:
        assert _run("SIGN_MATCHES_SIDE", ["SELL", -5])

    def test_a_positive_sell_fails(self) -> None:
        """A book mixing both conventions nets to a position nobody holds."""
        assert _run("SIGN_MATCHES_SIDE", ["SELL", 5]) is False

    def test_zero_has_no_sign(self) -> None:
        """A zero-quantity row is a different finding, and answering False here
        would attach it to this control."""
        assert _run("SIGN_MATCHES_SIDE", ["BUY", 0]) is UNSET

    def test_an_unrecognised_side_is_unknown(self) -> None:
        assert _run("SIGN_MATCHES_SIDE", ["XFER", 10]) is UNSET


class TestExtraction:
    def test_the_eurobond_prefix_is_returned_as_itself(self) -> None:
        """XS is not a country. A control comparing an ISIN prefix to an
        issuer's jurisdiction has to allow for it or it fires on every Eurobond
        in the book."""
        assert _run("ISIN_COUNTRY", ["XS1234567890"]) == "XS"

    def test_countries_come_from_the_right_positions(self) -> None:
        assert _run("IBAN_COUNTRY", ["GB33BUKB20201555555555"]) == "GB"
        assert _run("BIC_COUNTRY", ["BUKBGB22XXX"]) == "GB"


CONFORMANCE = [
    # (pql function, columns, rows) — chosen so each case exercises a branch.
    (
        "IBAN_BIC_CONSISTENT(iban, bic)",
        ("iban", "bic"),
        [
            ("DE89370400440532013000", "COBADEFFXXX"),
            ("DE89370400440532013000", "BNPAFRPPXXX"),
            ("GB33BUKB20201555555555", "BUKBGB22XXX"),
            ("de89370400440532013000", "cobadeffxxx"),
        ],
    ),
    (
        "SETTLES_AFTER_TRADE(trade_date, settle_date)",
        ("trade_date", "settle_date"),
        [
            ("2026-09-01", "2026-09-03"),
            ("2026-09-01", "2026-09-01"),
            ("2026-09-05", "2026-09-01"),
        ],
    ),
    (
        "SAME_COUNTRY(a, b)",
        ("a", "b"),
        [("GB", "GB"), ("GB", "FR"), ("gb", "GB")],
    ),
]


class TestTheSqlAgreesWithTheReferenceImplementation:
    """The property that makes any of this believable.

    A function whose SQL and reference implementation disagree is worse than one
    with no SQL: the compiler and its independent check are the entire basis for
    trusting a verdict, and a silent divergence removes that while looking like
    coverage.
    """

    @pytest.mark.parametrize("expression,columns,rows", CONFORMANCE)
    def test_the_violation_count_matches(
        self, expression: str, columns: tuple[str, ...], rows: list[tuple]
    ) -> None:
        from prama.pql.library import FUNCTIONS

        connection = duckdb.connect()
        declaration = ", ".join(f"{name} VARCHAR" for name in columns)
        connection.execute(f"CREATE TABLE t ({declaration})")
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(f"INSERT INTO t VALUES ({placeholders})", rows)

        pql = (
            f"CHECK t SATISFIES {expression} "
            "SEVERITY major DIMENSION consistency BECAUSE 'conformance'"
        )
        query = compile_for(resolved(parse_control(pql)), "duckdb", table="t").metric_query
        _, from_sql = connection.execute(query).fetchone()

        name = expression.split("(", 1)[0]
        function = FUNCTIONS.find(name)
        assert function is not None
        from_reference = sum(1 for row in rows if function.evaluate(list(row)) is False)
        connection.close()

        assert from_sql == from_reference, (
            f"{name}: SQL found {from_sql:g} violation(s) and the reference "
            f"implementation found {from_reference}"
        )

    def test_the_planted_defects_are_found_in_a_realistic_table(self) -> None:
        """One row per defect class, in one table, compiled and executed."""
        connection = duckdb.connect()
        connection.execute(
            "CREATE TABLE payments (iban VARCHAR, bic VARCHAR, amount DOUBLE, "
            "ccy VARCHAR, trade_date VARCHAR, settle_date VARCHAR, side VARCHAR, qty DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO payments VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    "DE89370400440532013000",
                    "COBADEFFXXX",
                    100.0,
                    "EUR",
                    "2026-09-01",
                    "2026-09-03",
                    "BUY",
                    10.0,
                ),
                (
                    "DE89370400440532013000",
                    "BNPAFRPPXXX",
                    100.0,
                    "EUR",
                    "2026-09-01",
                    "2026-09-03",
                    "BUY",
                    10.0,
                ),
                (
                    "FR1420041010050500013M02606",
                    "BNPAFRPPXXX",
                    1050.75,
                    "JPY",
                    "2026-09-01",
                    "2026-09-03",
                    "SELL",
                    -5.0,
                ),
                (
                    "DE89370400440532013000",
                    "COBADEFFXXX",
                    100.0,
                    "USD",
                    "2026-09-05",
                    "2026-09-01",
                    "SELL",
                    5.0,
                ),
            ],
        )
        for expression in (
            "IBAN_BIC_CONSISTENT(iban, bic)",
            "MINOR_UNITS_OK(amount, ccy)",
            "SETTLES_AFTER_TRADE(trade_date, settle_date)",
            "SIGN_MATCHES_SIDE(side, qty)",
        ):
            pql = (
                f"CHECK payments SATISFIES {expression} "
                "SEVERITY critical DIMENSION consistency BECAUSE 'pack'"
            )
            query = compile_for(
                resolved(parse_control(pql)), "duckdb", table="payments"
            ).metric_query
            scanned, violating = connection.execute(query).fetchone()
            assert scanned == 4, expression
            assert violating == 1, f"{expression} found {violating}, expected 1"
        connection.close()


class TestRegistration:
    def test_every_function_carries_sql(self) -> None:
        """Not a residual. A check that runs in the warehouse examines every
        row; a residual examines only the rows a screen let through."""
        for function in BANKING_FUNCTIONS:
            assert function.sql or function.sql_by_engine, function.name
            assert not function.unsupported_on, function.name

    def test_every_function_names_what_it_is_for(self) -> None:
        for function in BANKING_FUNCTIONS:
            assert len(function.summary) > 30, function.name


class TestWhatIsAdvertisedExists:
    """Finding H1, first half. `prama pack list` printed eight cross-field
    checks and `prama control check` refused every one as an unknown function.

    `install()` was written, tested, and called only from `tests/` — never once
    from `src/`. Documentation drifting from behaviour is ordinary; an
    advertisement and a refusal in the same CLI is two halves of one product
    disagreeing.
    """

    def test_every_advertised_function_resolves(self) -> None:
        from prama.packs import install_shipped
        from prama.pql.library import FUNCTIONS

        install_shipped()
        missing = [f.name for f in BANKING_FUNCTIONS if FUNCTIONS.get(f.name) is None]
        assert not missing, f"advertised by `prama pack list` and not installed: {missing}"

    def test_the_bootstrap_is_reachable_from_src(self) -> None:
        """The defect was structural, not a typo: nothing outside tests called
        it. This pins that a production entry point still does."""
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parents[2] / "src" / "prama"
        callers = [
            path.relative_to(src).as_posix()
            for path in src.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "install_shipped"
        ]
        assert len(callers) >= 2, (
            f"install_shipped() is called from {callers or 'nowhere in src/'}; "
            "the CLI and the app must both install what the packs advertise"
        )


class TestTheSqlAgreesWithItsOwnReference:
    """Finding H1, second half. Five of eight templates disagreed with the
    function's own `evaluate`, every one of them in the unsafe direction: SQL
    said TRUE where the reference said UNKNOWN.

    That is the worst possible direction. Under Prama's default policy an
    unknown is a violation, so the reference routes a malformed row to a human
    and the SQL passed it silently — on the engine that actually runs in
    production.

    Each case below is a row that is *malformed*, not wrong: the finding belongs
    to the format control, and answering TRUE reports a defect as a pass.
    """

    #: (function, arguments, why this input is not a judgement)
    ADVERSARIAL: ClassVar[tuple[tuple[str, tuple[object, ...], str], ...]] = (
        ("IBAN_BIC_CONSISTENT", ("", ""), "two empty identifiers compare equal"),
        ("IBAN_BIC_CONSISTENT", ("GB", "DEUT"), "a BIC too short to carry a country"),
        ("MINOR_UNITS_OK", (1050.75, "JP"), "'JP' is not a currency code"),
        ("SIGN_MATCHES_SIDE", ("BORROW", 10), "a lending side read as a buy"),
        ("SAME_COUNTRY", ("GBR", "GBR"), "alpha-3 codes in an alpha-2 comparison"),
        ("IBAN_COUNTRY", ("X",), "one character cannot be a country"),
        ("BIC_COUNTRY", ("DEUT",), "too short to reach the country position"),
        ("ISIN_COUNTRY", ("X",), "one character cannot be a country"),
    )

    @pytest.mark.parametrize(
        ("name", "arguments", "why"), ADVERSARIAL, ids=[c[0] + ":" + c[2][:18] for c in ADVERSARIAL]
    )
    def test_the_reference_declines_to_judge(
        self, name: str, arguments: tuple[object, ...], why: str
    ) -> None:
        """First, that the reference really does decline. Without this the test
        below would be satisfied by a reference that was itself wrong."""
        function = next(f for f in BANKING_FUNCTIONS if f.name == name)
        assert function.evaluate is not None
        assert function.evaluate(list(arguments)) is UNSET, why

    @pytest.mark.parametrize(
        ("name", "arguments", "why"), ADVERSARIAL, ids=[c[0] + ":" + c[2][:18] for c in ADVERSARIAL]
    )
    def test_the_sql_declines_too(self, name: str, arguments: tuple[object, ...], why: str) -> None:
        """And that the SQL agrees, executed rather than inspected.

        NULL is how SQL says UNKNOWN, and the IR's Kleene handling turns it
        into a violation under the default policy — which is the answer the
        reference gives.
        """
        import duckdb

        function = next(f for f in BANKING_FUNCTIONS if f.name == name)
        literals = [
            "NULL" if a is None else (f"'{a}'" if isinstance(a, str) else repr(a))
            for a in arguments
        ]
        expression = function.sql.format(*literals)
        answer = duckdb.sql(f"SELECT {expression} AS answer").fetchone()
        assert answer is not None
        assert answer[0] is None, (
            f"{name}{arguments} -> {answer[0]!r} in SQL but UNKNOWN in its own "
            f"reference implementation: {why}. SQL passing a row the reference "
            "sends to a human is the unsafe direction of a disagreement."
        )
