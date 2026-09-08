"""Trailer and manifest integrity.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

from prama.connect.feed import (
    IntegrityStatus,
    ManifestChecker,
    TrailerChecker,
    TrailerSpec,
)


def rows(count: int, amount: str = "100.00") -> list[str]:
    return [f"ROW,{n},{amount}" for n in range(1, count + 1)]


class TestRecordCount:
    def test_a_matching_count_passes(self) -> None:
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
        finding = checker.check("f.csv", [*rows(3), "TRLR,3"])
        assert finding.status is IntegrityStatus.MATCHED
        assert finding.is_healthy

    def test_a_short_file_is_caught_when_nothing_else_would_catch_it(self) -> None:
        # Every row that arrived is valid. Only the trailer knows two are gone.
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
        finding = checker.check("f.csv", [*rows(3), "TRLR,5"])
        assert finding.status is IntegrityStatus.COUNT_MISMATCH
        assert finding.shortfall == 2
        assert "3" in finding.render() and "5" in finding.render()
        assert finding.status.severity == "critical"

    def test_a_header_row_is_not_a_record(self) -> None:
        # Without this the check reports a one-row surplus on every delivery of
        # every headed CSV, and the team mutes it inside a week.
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, header_lines=1))
        finding = checker.check("f.csv", ["id,seq,amount", *rows(3), "TRLR,3"])
        assert finding.status is IntegrityStatus.MATCHED

    def test_a_trailing_newline_is_not_a_record(self) -> None:
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
        finding = checker.check("f.csv", [*rows(3), "TRLR,3", ""])
        assert finding.status is IntegrityStatus.MATCHED

    def test_a_trailer_that_counts_itself_is_honoured(self) -> None:
        # Both conventions are in the wild; assuming one silently breaks the
        # other by exactly one row.
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, counts_itself=True))
        assert checker.check("f.csv", [*rows(3), "TRLR,4"]).status is IntegrityStatus.MATCHED

    def test_a_missing_trailer_reads_as_truncation(self) -> None:
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1))
        finding = checker.check("f.csv", rows(3))
        assert finding.status is IntegrityStatus.TRAILER_MISSING
        assert "re-send" in finding.status.next_action

    def test_an_unparseable_trailer_blames_the_declaration_not_the_data(self) -> None:
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=9))
        finding = checker.check("f.csv", [*rows(3), "TRLR,3"])
        assert finding.status is IntegrityStatus.TRAILER_UNREADABLE
        assert "layout" in finding.status.next_action

    def test_no_declared_trailer_is_not_a_failure(self) -> None:
        finding = TrailerChecker(TrailerSpec()).check("f.csv", rows(3))
        assert finding.status is IntegrityStatus.MATCHED


class TestHashTotal:
    def test_a_matching_total_passes(self) -> None:
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
        finding = checker.check("f.csv", [*rows(3), "TRLR,3,300.00"])
        assert finding.status is IntegrityStatus.MATCHED
        assert finding.observed_total == Decimal("300.00")

    def test_the_summed_column_is_separate_from_the_trailer_field(self) -> None:
        # The trailer is TRLR,<count>,<total> but the amount lives in column 4
        # of the data. Reusing the trailer's index would sum the wrong column
        # and fail on files that are perfectly correct.
        spec = TrailerSpec(marker="TRLR", count_field=1, total_field=2, amount_field=4)
        data = ["ROW,1,x,y,10.50", "ROW,2,x,y,20.25"]
        assert TrailerChecker(spec).check("f.csv", [*data, "TRLR,2,30.75"]).status is (
            IntegrityStatus.MATCHED
        )

    def test_amounts_that_do_not_add_up_are_a_different_failure_from_a_short_file(self) -> None:
        # Right number of rows, wrong values: a restatement or a corruption,
        # and the next action is reconciliation rather than a re-send.
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
        finding = checker.check("f.csv", [*rows(3), "TRLR,3,999.00"])
        assert finding.status is IntegrityStatus.TOTAL_MISMATCH
        assert "reconcile" in finding.status.next_action

    def test_money_is_summed_exactly(self) -> None:
        # 0.1 + 0.2 != 0.3 in binary floating point. A hash total check exists
        # to detect small discrepancies, so it must not manufacture one.
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
        data = ["ROW,1,0.10", "ROW,2,0.20"]
        assert (
            TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
            .check("f.csv", [*data, "TRLR,2,0.30"])
            .status
            is IntegrityStatus.MATCHED
        )
        assert checker.check("f.csv", [*data, "TRLR,2,0.30"]).observed_total == Decimal("0.30")

    def test_a_sender_who_truncates_the_total_can_declare_the_tolerance(self) -> None:
        spec = TrailerSpec(marker="TRLR", count_field=1, total_field=2, total_tolerance="0.01")
        data = ["ROW,1,10.004", "ROW,2,10.004"]
        assert TrailerChecker(spec).check("f.csv", [*data, "TRLR,2,20.00"]).status is (
            IntegrityStatus.MATCHED
        )

    def test_an_unreadable_total_is_reported_as_such(self) -> None:
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
        finding = checker.check("f.csv", [*rows(3), "TRLR,3,not-a-number"])
        assert finding.status is IntegrityStatus.TRAILER_UNREADABLE

    def test_the_count_is_checked_before_the_total(self) -> None:
        # A short file also fails the total. Reporting TOTAL_MISMATCH would send
        # someone to reconcile values when the real answer is "rows are missing".
        checker = TrailerChecker(TrailerSpec(marker="TRLR", count_field=1, total_field=2))
        finding = checker.check("f.csv", [*rows(3), "TRLR,5,500.00"])
        assert finding.status is IntegrityStatus.COUNT_MISMATCH


class TestManifest:
    def test_a_complete_batch_passes(self) -> None:
        files = ["a.csv", "b.csv", "c.csv"]
        finding = ManifestChecker().check("batch.mft", files, files)
        assert finding.status is IntegrityStatus.MATCHED

    def test_a_partial_batch_names_what_is_missing(self) -> None:
        # Four of five files produce numbers that are wrong and look right.
        finding = ManifestChecker().check(
            "batch.mft", ["a.csv", "b.csv", "c.csv"], ["a.csv", "c.csv"]
        )
        assert finding.status is IntegrityStatus.MANIFEST_INCOMPLETE
        assert finding.missing_files == ("b.csv",)
        assert "b.csv" in finding.render()

    def test_extra_files_do_not_make_a_batch_incomplete(self) -> None:
        # Another feed's file in the same directory is not this batch's problem.
        finding = ManifestChecker().check("batch.mft", ["a.csv"], ["a.csv", "unrelated.csv"])
        assert finding.status is IntegrityStatus.MATCHED
