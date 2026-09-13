"""The conformance corpus: controls every backend must agree about.

A portability claim is only as good as the thing that checks it. This is that
thing — a fixed dataset and a fixed set of controls, run on every supported
engine, with the results required to match exactly. A backend that disagrees
does not ship.

The dataset is small and deliberately nasty: nulls where they matter, a
duplicate key, a value that breaks a pattern, an empty segment, a numeric
boundary exactly on a threshold. Every row is there because some engine gets
that case wrong if nobody looks.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

#: Columns of the corpus table, in order, with a portable type for each engine.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("row_id", "INTEGER"),
    ("account_id", "VARCHAR(20)"),
    ("instrument_id", "VARCHAR(20)"),
    ("entity", "VARCHAR(10)"),
    ("isin", "VARCHAR(12)"),
    ("ccy", "VARCHAR(3)"),
    ("notional", "DOUBLE PRECISION"),
    ("status", "VARCHAR(10)"),
    ("lei", "VARCHAR(20)"),
)

#: The corpus rows. Each is annotated in ROW_NOTES with what it is there to
#: catch, so a future edit cannot quietly remove the case that mattered.
ROWS: tuple[tuple[object, ...], ...] = (
    (1, "A1", "I1", "EMEA", "GB0002634946", "GBP", 100.0, "ACTIVE", "5493001KJTIIGC8Y1R12"),
    (2, "A1", "I2", "EMEA", "US0378331005", "USD", 250.0, "ACTIVE", "213800LBQA1Y9L22JB70"),
    (3, "A2", "I1", "APAC", "DE0007164600", "EUR", 0.0, "ACTIVE", "HWUPKR0MPOU8FGXBT394"),
    (4, "A2", "I2", "APAC", None, "JPY", 500.0, "ACTIVE", None),
    (5, "A3", "I1", "EMEA", "NOTANISIN", "GBP", -10.0, "ACTIVE", "not-an-lei"),
    (6, "A3", "I1", "EMEA", "GB0002634946", "XXX", None, "CANCELLED", "AAAAAAAAAAAAAAAAAA00"),
    (7, "A4", "I3", "AMER", "US0378331005", "USD", 1000.0, "ACTIVE", "7LTWFZYICNSX8D621K86"),
    (8, "A4", "I4", "AMER", "GB0002634946", "GBP", 100.0, "CANCELLED", "ZXTILKJKG63JELOEG630"),
)

ROW_NOTES: dict[int, str] = {
    4: "a null ISIN: the unknown that SQL would let pass silently",
    5: "an ISIN that is the right length and the wrong shape",
    6: "a null notional and an unlisted currency, on a cancelled row — and an LEI "
    "with a perfect shape whose check characters do not verify, which is the row no "
    "SQL engine can catch and the reason IS VALID is two-stage",
    8: "duplicates row 6's key only after the CANCELLED filter is applied",
    3: "a legacy LEI without the ISO 17442 reserved zeros — valid, and a screen "
    "requiring them would reject it",
}

#: (account_id, instrument_id) repeats on rows 5 and 6, so a unique key over
#: that pair fails — by exactly one row, which is the count the engines must
#: agree on rather than merely agreeing that it failed.
DUPLICATE_KEY = ("account_id", "instrument_id")


@dataclasses.dataclass(frozen=True, slots=True)
class Case:
    """One corpus control, and why it is in the corpus."""

    name: str
    pql: str
    #: Capabilities without which an engine may legitimately refuse this case.
    requires: frozenset[str] = frozenset()
    catches: str = ""
    #: For a two-stage control, how many violations the **SQL screen alone**
    #: must find. Declared as a number rather than left in the prose of
    #: `catches`, because the conformance suite previously required only that an
    #: engine find no *more* than the exact check — so a screen that rejected
    #: nothing at all was excused, and a neutered screen was indistinguishable
    #: from a working one. See finding T4.
    screen_violations: float | None = None


CASES: tuple[Case, ...] = (
    Case(
        name="not_null",
        pql="CHECK corpus.isin IS NOT NULL",
        catches="the plain case, and that a null is counted",
    ),
    Case(
        name="not_null_filtered",
        pql="CHECK corpus.notional IS NOT NULL WHERE status = 'ACTIVE'",
        catches="a filter changing both the numerator and the denominator",
    ),
    Case(
        name="unknown_is_violation",
        pql="CHECK corpus.notional > 0",
        catches=(
            "the inversion of SQL's default: the null notional on row 6 must count "
            "against the control, not vanish"
        ),
    ),
    Case(
        name="unknown_may_pass",
        pql="CHECK corpus.notional > 0 TREAT UNKNOWN AS PASS BECAUSE 'declared'",
        catches="the same data with the opposite unknown policy, to pin the difference",
    ),
    Case(
        name="in_set",
        pql="CHECK corpus.ccy IN ('GBP', 'USD', 'EUR', 'JPY')",
        catches="set membership, including that an unlisted value fails",
    ),
    Case(
        name="not_in_set",
        pql="CHECK corpus.ccy NOT IN ('XXX')",
        catches="negation, where an engine may get the null handling wrong",
    ),
    Case(
        name="between_boundaries",
        pql="CHECK corpus.notional BETWEEN 0 AND 1000",
        catches="inclusive bounds, exactly on 0 and exactly on 1000",
    ),
    Case(
        name="semantic_type_two_stage",
        pql="CHECK corpus.lei IS VALID 'lei'",
        screen_violations=2.0,
        catches=(
            "the row every engine gets wrong on its own: AAAAAAAAAAAAAAAAAA00 has an "
            "LEI's exact shape and check characters that do not verify. SQL applies the "
            "screen and finds two violations; the exact check finds three. The engines "
            "are not required to agree here — they are required to differ in one "
            "direction only, because a screen that rejected a valid value would report "
            "a violation on good reference data"
        ),
    ),
    Case(
        name="division_by_zero",
        pql="CHECK corpus SATISFIES (1000 / notional) > 0",
        catches=(
            "a zero divisor — row 3 has notional 0.0 — on which the three "
            "engines agreed about nothing. "
            "PostgreSQL raised and aborted the whole query, DuckDB and SQLite "
            "returned NULL, and the reference returned UNKNOWN — so one bad row "
            "killed a control on one engine and was silently skipped on two. "
            "Every divisor is now wrapped in NULLIF, which makes all three "
            "return NULL and agree with the oracle. Aborting was the worst of "
            "the four: a control that cannot report because one row was bad has "
            "said nothing about the other million"
        ),
    ),
    Case(
        name="modulo_on_a_fraction",
        pql="CHECK corpus SATISFIES (notional % 2) <> 0.5",
        catches=(
            "PostgreSQL's `%`, which is defined for integer and numeric and not "
            "for double precision — `notional % 2` on a DOUBLE column raises "
            "'operator does not exist'. DuckDB and SQLite accept it, so this "
            "ran on two engines and could not run on the third. Found only when "
            "the conformance suite was pointed at a real PostgreSQL, which it "
            "had never been"
        ),
    ),
    Case(
        name="modulo_on_a_negative",
        pql="CHECK corpus SATISFIES (notional % 3) <> 2",
        catches=(
            "the sign of a remainder. Row 5 has notional -10: Python floors and "
            "gives 2, every SQL engine truncates and gives -1. The reference "
            "interpreter reported a violation none of the three engines did, and "
            "the corpus had no arithmetic case at all, so the gate never saw it"
        ),
    ),
    Case(
        name="division_is_not_integer_division",
        pql="CHECK corpus SATISFIES (row_id / 2) > 0",
        catches=(
            "the one case where the engines disagreed with *each other*: SQLite "
            "and PostgreSQL divide two integers as integers, so row 1 gives 0, "
            "while DuckDB and the interpreter give 0.5. Same control, PASS on two "
            "engines and FAIL on the third"
        ),
    ),
    Case(
        name="row_count",
        pql="CHECK corpus HAS ROW COUNT BETWEEN 1 AND 8",
        catches="a dataset-level assertion with no per-row predicate",
    ),
    Case(
        name="row_count_filtered",
        pql="CHECK corpus HAS ROW COUNT AT LEAST 7 WHERE status = 'ACTIVE'",
        catches="a row count that fails, so a failing verdict is compared too",
    ),
    Case(
        name="unique_key",
        pql="CHECK corpus HAS UNIQUE KEY (account_id, instrument_id)",
        catches="a set-level property, and that the violating count is 1 and not 2",
    ),
    Case(
        name="unique_key_holds",
        pql="CHECK corpus HAS UNIQUE KEY (row_id)",
        catches="the same machinery when it passes",
    ),
    Case(
        name="functional_dependency",
        pql="CHECK corpus SATISFIES account_id DETERMINES entity",
        catches=(
            "a dependency that holds — and that the test is not the unique-key "
            "test, which would fail here because every account appears twice"
        ),
    ),
    Case(
        name="functional_dependency_broken",
        pql="CHECK corpus SATISFIES ccy DETERMINES entity",
        catches="a determinant carrying two dependents, counted in determinants not rows",
    ),
    Case(
        name="segmented",
        pql="CHECK corpus.isin IS NOT NULL FOR EACH entity",
        catches="per-segment verdicts, and that one bad segment fails the whole",
    ),
    Case(
        name="segmented_rate",
        pql="CHECK corpus.isin IS NOT NULL FOR EACH entity BELOW 30%",
        catches="a rate threshold applied within each segment, not across them",
    ),
    Case(
        name="rate_threshold",
        pql="CHECK corpus.isin IS NOT NULL BELOW 20%",
        catches="a rate that must be computed from one pass, 1/8 against 20%",
    ),
    Case(
        name="rate_threshold_fails",
        pql="CHECK corpus.isin IS NOT NULL BELOW 10%",
        catches="the same rate on the other side of the line",
    ),
    Case(
        name="expression",
        pql="CHECK corpus SATISFIES NOT (status = 'CANCELLED' AND notional > 0)",
        catches="a compound expression, and NOT binding the whole comparison",
    ),
    Case(
        name="length",
        pql="CHECK corpus.isin HAS LENGTH BETWEEN 12 AND 12",
        catches="a function inside a predicate, with a null argument present",
    ),
    Case(
        name="regex",
        pql=r"CHECK corpus.isin MATCHES /^[A-Z]{2}[0-9A-Z]{9}[0-9]$/",
        requires=frozenset({"pushdown.regex"}),
        catches="a pattern, where engines differ and one must refuse rather than guess",
    ),
)


def create_table(table: str = "corpus", *, dialect: str = "postgresql") -> str:
    """DDL for the corpus table, in a form all three engines accept."""
    from prama.backend.dialect import dialect as resolve

    double = resolve(dialect).double_type
    columns = ", ".join(
        f'"{name}" {double if "DOUBLE" in kind else kind}' for name, kind in COLUMNS
    )
    return f'CREATE TABLE "{table}" ({columns})'


def insert_rows(table: str = "corpus", *, placeholder: str = "?") -> str:
    marks = ", ".join(
        placeholder if placeholder != "$" else f"${i + 1}" for i in range(len(COLUMNS))
    )
    names = ", ".join(f'"{name}"' for name, _ in COLUMNS)
    return f'INSERT INTO "{table}" ({names}) VALUES ({marks})'
