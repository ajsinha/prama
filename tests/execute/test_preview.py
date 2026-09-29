"""Preview and backtest, against a real engine.

Every trial here runs actual SQL over actual rows in DuckDB. A preview that was
tested against a stub executor would confirm the shape of the answer and
nothing about its truth, and the whole reason a preview exists is that the
author does not trust the shape — they want the number.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import pytest

from prama.core.errors import ValidationError
from prama.execute.preview import Backtest, Preview, Trial, business_dates

duckdb = pytest.importorskip("duckdb")

NOT_NULL = (
    "CHECK positions.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)


@pytest.fixture
def book():
    """Ten business days of positions, with two bad days and one empty one.

    2026-09-01..02 clean, 03 has nulls, 04 clean, 07 has nulls, 08 clean,
    09 present but empty of rows in scope, 10..11 clean.
    """
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE positions (as_of_date VARCHAR, account_id VARCHAR, notional DOUBLE)"
    )
    rows: list[tuple[str, str, float | None]] = []
    for day, nulls in [
        ("2026-09-01", 0),
        ("2026-09-02", 0),
        ("2026-09-03", 3),
        ("2026-09-04", 0),
        ("2026-09-07", 5),
        ("2026-09-08", 0),
        ("2026-09-10", 0),
        ("2026-09-11", 0),
    ]:
        for n in range(20):
            value = None if n < nulls else 1000.0 + n
            rows.append((day, f"ACC{n:03d}", value))
    connection.executemany("INSERT INTO positions VALUES (?, ?, ?)", rows)

    def execute(sql: str) -> list[dict]:
        cursor = connection.execute(sql)
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    yield execute
    connection.close()


class TestOneTrial:
    def test_it_finds_what_is_there(self, book) -> None:
        trial = Preview(execute=book, engine="duckdb").once(NOT_NULL)
        assert trial.verdict == "fail"
        assert trial.scanned_rows == 160
        assert trial.violating_rows == 8
        assert trial.ran

    def test_a_clean_control_passes(self, book) -> None:
        trial = Preview(execute=book, engine="duckdb").once(
            "CHECK positions.account_id IS NOT NULL "
            "SEVERITY major DIMENSION completeness BECAUSE 'key'"
        )
        assert trial.verdict == "pass"
        assert trial.violating_rows == 0

    def test_an_unreadable_source_is_an_error_not_a_pass(self, book) -> None:
        """The distinction the whole module turns on: "we could not look" and
        "we looked and found nothing" must never render the same."""
        trial = Preview(execute=book, engine="duckdb").once(
            "CHECK absent.thing IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'"
        )
        assert not trial.ran
        assert trial.verdict == ""
        assert "absent" in trial.error

    def test_pql_that_will_not_parse_is_reported_as_such(self, book) -> None:
        trial = Preview(execute=book, engine="duckdb").once("CHECK ???")
        assert not trial.ran
        assert trial.verdict == ""

    def test_it_reports_the_sql_that_ran(self, book) -> None:
        """An author who cannot see the query cannot tell a surprising number
        from a wrong one."""
        trial = Preview(execute=book, engine="duckdb").once(NOT_NULL)
        assert "FROM" in trial.query
        assert "positions" in trial.query


class TestNothingIsRecorded:
    def test_the_preview_holds_no_way_to_write(self) -> None:
        """A structural guard, not a behavioural one. The reason a trial cannot
        reach the ledger is that this object has no unit of work at all, and a
        test on one code path would not notice a second path appearing."""
        preview = Preview(execute=lambda _sql: [], engine="duckdb")
        attributes = {name for name in dir(preview) if not name.startswith("__")}
        assert not any("uow" in a or "evidence" in a or "ledger" in a for a in attributes)

    def test_a_trial_is_not_an_evidence_record(self, book) -> None:
        """Different types, deliberately. A trial ran against an unapproved
        control, often over a bounded scan; a record is what a regulator may
        read. Making them convertible is one refactor away from a ledger
        nobody can vouch for."""
        from prama.evidence.record import EvidenceRecord

        trial = Preview(execute=book, engine="duckdb").once(NOT_NULL)
        assert isinstance(trial, Trial)
        assert not isinstance(trial, EvidenceRecord)
        assert not hasattr(trial, "content_hash")

    def test_the_module_imports_nothing_that_could_persist(self) -> None:
        """Scanned rather than exercised. Behaviour tests cover the paths that
        exist; this covers the one somebody adds later, by making the *import*
        the thing that fails rather than the write."""
        import ast
        import pathlib

        import prama.execute.preview as module

        tree = ast.parse(pathlib.Path(module.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)

        forbidden = ("prama.db", "prama.evidence", "sqlalchemy")
        offending = {m for m in imported for f in forbidden if m == f or m.startswith(f + ".")}
        assert not offending, f"a preview must not be able to persist: {sorted(offending)}"


class TestTheScanCap:
    def test_a_cap_bounds_the_scan_and_says_so(self, book) -> None:
        trial = Preview(execute=book, engine="duckdb", max_rows=50).once(NOT_NULL)
        assert trial.scanned_rows == 50
        assert trial.was_bounded
        assert "floor" in trial.detail

    def test_an_uncapped_preview_is_not_marked_bounded(self, book) -> None:
        trial = Preview(execute=book, engine="duckdb").once(NOT_NULL)
        assert trial.scanned_rows == 160
        assert not trial.was_bounded

    def test_a_cap_larger_than_the_table_does_not_claim_a_bound(self, book) -> None:
        """Otherwise every small table reads as truncated, the warning appears
        everywhere, and it stops being read anywhere."""
        trial = Preview(execute=book, engine="duckdb", max_rows=10_000).once(NOT_NULL)
        assert trial.scanned_rows == 160
        assert not trial.was_bounded

    def test_the_cap_bounds_the_scan_not_the_result(self, book) -> None:
        """The failure this is really guarding: a LIMIT appended to an
        aggregate query bounds the one row of output and leaves the scan
        exactly as expensive, while reading in the SQL as though it applied."""
        trial = Preview(execute=book, engine="duckdb", max_rows=50).once(NOT_NULL)
        assert "LIMIT 50" in trial.query
        assert trial.query.index("LIMIT 50") < trial.query.rindex(")")


class TestBacktest:
    def _run(self, book, **kwargs) -> Backtest:
        return Preview(execute=book, engine="duckdb", **kwargs).backtest(
            NOT_NULL,
            period_column="as_of_date",
            periods=[
                "2026-09-01",
                "2026-09-02",
                "2026-09-03",
                "2026-09-04",
                "2026-09-07",
                "2026-09-08",
                "2026-09-09",
                "2026-09-10",
                "2026-09-11",
            ],
        )

    def test_each_period_is_evaluated_separately(self, book) -> None:
        result = self._run(book)
        assert len(result.trials) == 9
        assert {t.label for t in result.alerting} == {"2026-09-03", "2026-09-07"}

    def test_a_period_with_no_rows_is_not_a_passing_period(self, book) -> None:
        """The trap this module exists for. An empty slice violates nothing and
        would be judged a pass; ten empty days in thirty quietly cut the
        expected alert rate by a third, and the empty days are usually a
        retention window — so the backtest is most wrong exactly where the
        author trusts it most."""
        result = self._run(book)
        [empty] = result.empty
        assert empty.label == "2026-09-09"
        assert empty.verdict == "no_data"
        assert empty.verdict != "pass"

    def test_the_rate_excludes_the_empty_period(self, book) -> None:
        result = self._run(book)
        assert len(result.evaluated) == 8
        assert result.alert_rate == pytest.approx(2 / 8)
        assert "excluded from the rate rather than counted as quiet" in result.describe()

    def test_the_expected_volume_is_projected_from_evaluated_periods(self, book) -> None:
        result = self._run(book)
        assert result.per_period(20) == pytest.approx(5.0)

    def test_a_period_that_could_not_be_read_is_not_quiet(self, book) -> None:
        result = Preview(execute=book, engine="duckdb").backtest(
            "CHECK absent.thing IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'",
            period_column="as_of_date",
            periods=["2026-09-01", "2026-09-02"],
        )
        assert len(result.errored) == 2
        assert result.alert_rate is None
        assert "none of the 2 period(s) could be evaluated" in result.describe()

    def test_no_evaluated_period_never_reports_zero(self, book) -> None:
        """Zero is the number that gets a control approved on the strength of
        an outage."""
        result = Preview(execute=book, engine="duckdb").backtest(
            "CHECK absent.thing IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'",
            period_column="as_of_date",
            periods=["2026-09-01"],
        )
        assert result.alert_rate is None
        assert result.per_period(30) is None

    def test_too_few_periods_is_said_rather_than_averaged_over(self, book) -> None:
        result = Preview(execute=book, engine="duckdb").backtest(
            NOT_NULL,
            period_column="as_of_date",
            periods=["2026-09-01", "2026-09-03"],
        )
        assert not result.is_trustworthy
        assert "too few to quote a rate from" in result.describe()

    def test_an_existing_where_clause_survives_the_period_filter(self, book) -> None:
        """The period is added to the control, not substituted for it. A
        backtest that dropped the author's own WHERE would be backtesting a
        different control and reporting the number for this one."""
        result = Preview(execute=book, engine="duckdb").backtest(
            "CHECK positions.notional IS NOT NULL WHERE account_id = 'ACC000' "
            "SEVERITY critical DIMENSION completeness BECAUSE 'CDE'",
            period_column="as_of_date",
            periods=["2026-09-01", "2026-09-03"],
        )
        assert [t.scanned_rows for t in result.trials] == [1.0, 1.0]
        assert [t.violating_rows for t in result.trials] == [0.0, 1.0]

    def test_the_periods_stream_as_they_complete(self, book) -> None:
        """A generator, because a thirty-day backtest is thirty round trips and
        a screen that shows nothing until the last one lands is one people stop
        using."""
        stream = Preview(execute=book, engine="duckdb").over(
            NOT_NULL, period_column="as_of_date", periods=["2026-09-01", "2026-09-03"]
        )
        first = next(stream)
        assert first.label == "2026-09-01"
        assert first.verdict == "pass"


class TestThePeriodColumn:
    def test_a_column_name_that_is_not_an_identifier_is_refused(self, book) -> None:
        """For the error message, not for safety. The dialect quotes every
        identifier, so this would compile to a column of that name and find
        nothing; what the refusal buys is an author who knows what to type."""
        with pytest.raises(ValidationError, match="not a column name"):
            list(
                Preview(execute=book, engine="duckdb").over(
                    NOT_NULL,
                    period_column="as_of_date FROM positions; DROP TABLE positions --",
                    periods=["2026-09-01"],
                )
            )

    def test_a_period_containing_a_quote_is_a_value_not_a_statement(self, book) -> None:
        """It reaches the compiler as a Literal and is rendered by the dialect,
        so it finds nothing rather than doing something."""
        [trial] = list(
            Preview(execute=book, engine="duckdb").over(
                NOT_NULL,
                period_column="as_of_date",
                periods=["2026-09-01' OR '1'='1"],
            )
        )
        assert trial.ran
        assert trial.verdict == "no_data"


class TestBusinessDates:
    def test_it_skips_weekends(self) -> None:
        # 2026-09-11 is a Friday.
        dates = business_dates(date(2026, 9, 11), days=6)
        assert dates == [
            date(2026, 9, 4),
            date(2026, 9, 7),
            date(2026, 9, 8),
            date(2026, 9, 9),
            date(2026, 9, 10),
            date(2026, 9, 11),
        ]

    def test_it_can_include_them(self) -> None:
        dates = business_dates(date(2026, 9, 7), days=3, weekdays_only=False)
        assert dates == [date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 7)]


class TestTheRateIsNeverFlattering:
    def test_no_rows_scanned_gives_no_rate_rather_than_zero(self) -> None:
        assert Trial(label="x", scanned_rows=0, violating_rows=0).rate is None

    def test_an_indeterminate_period_counts_as_an_alert(self) -> None:
        """A control that could not establish a pass is one somebody has to
        look at, and a backtest that treated it as quiet would understate the
        workload the author is signing up for."""
        assert Trial(label="x", verdict="indeterminate").would_alert
        assert not Trial(label="x", verdict="pass").would_alert
        assert not Trial(label="x", verdict="no_data").would_alert

    def test_a_screened_period_makes_the_whole_count_a_lower_bound(self) -> None:
        result = Backtest(
            trials=(
                Trial(label="a", verdict="pass", scanned_rows=10),
                Trial(
                    label="b",
                    verdict="indeterminate",
                    scanned_rows=10,
                    screen_is_complete=False,
                ),
            )
        )
        assert result.is_a_lower_bound
        assert "at least 1 alert(s)" in result.describe()


def test_a_reconciliation_is_refused_rather_than_previewed_as_clean(book) -> None:
    """A preview of RECONCILE ran one metric query and read as zero breaks.

    The matching engine judges a reconciliation over both sides, so a preview
    cannot establish anything about it, and must say so rather than pass.
    Found converting case study 6 to the SDK.
    """
    trial = Preview(execute=book, engine="duckdb").once(
        "RECONCILE positions AGAINST ledger ON (account) COMPARING qty = quantity"
    )
    assert "cannot be previewed" in trial.error
    assert not trial.ran and trial.verdict != "pass"
