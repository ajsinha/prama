"""Catalogue write-back.

Nobody opens a data quality tool to find out whether a table is trustworthy;
they open the catalogue, because that is where they were going anyway. So the
shape of what gets written is the whole design, and every test here is about one
of the four ways a badge lies.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses

import pytest

from prama.core.errors import ValidationError
from prama.integrate.catalog import (
    Badge,
    RecordingTarget,
    Standing,
    badges_from,
)

WHEN = "2026-09-10T06:00:00Z"


@dataclasses.dataclass
class Record:
    dataset: str
    verdict: str
    coverage: str = "full"
    record_hash: str = "ab" * 32


def badge(**kw) -> Badge:
    return Badge(
        dataset=kw.pop("dataset", "positions"),
        standing=kw.pop("standing", Standing.HEALTHY),
        established_at=kw.pop("established_at", WHEN),
        **kw,
    )


class TestABadgeCannotBeUndated:
    def test_a_badge_with_no_date_is_refused(self) -> None:
        """ "Trusted" on a table nobody has checked since March reads as current,
        and a reader has no way to tell."""
        with pytest.raises(ValidationError, match="no date"):
            Badge(dataset="d", standing=Standing.HEALTHY, established_at="")

    def test_the_date_appears_in_what_the_catalogue_shows(self) -> None:
        assert WHEN in badge().render()

    def test_a_catalogue_that_cannot_store_a_date_gets_no_badges(self) -> None:
        """Refused wholesale rather than written undated. An undated badge reads
        as current forever, which is worse than no badge at all."""
        target = RecordingTarget(supports=frozenset({"standing"}))
        report = target.publish([badge()])
        assert report.written == 0
        assert target.written == []
        # One systemic reason, so the reason is the finding rather than a list
        # of unlucky tables.
        assert "all 1 refused for the same reason" in report.describe()
        assert "reads as current forever" in report.describe()


class TestSilenceAndHealthDoNotRenderTheSame:
    @pytest.mark.parametrize(
        "standing,reassuring",
        [
            (Standing.HEALTHY, True),
            (Standing.FAILING, False),
            (Standing.NOT_ESTABLISHED, False),
            (Standing.UNPROVEN, False),
            (Standing.UNCOVERED, False),
        ],
    )
    def test_only_a_pass_is_reassuring(self, standing: Standing, reassuring: bool) -> None:
        assert standing.is_reassuring is reassuring

    def test_a_dataset_nothing_covers_gets_a_badge_saying_so(self) -> None:
        """A catalogue showing a badge on nine tables and nothing on the tenth
        invites a reader to assume the tenth is fine."""
        badges = badges_from({}, datasets=["positions", "trades"], established_at=WHEN)
        assert {b.dataset for b in badges} == {"positions", "trades"}
        assert all(b.standing is Standing.UNCOVERED for b in badges)
        assert "no control covers this" in badges[0].render()

    def test_an_unestablished_verdict_is_not_a_pass(self) -> None:
        """The temptation is to publish passes and stay quiet otherwise, which
        leaves a failing table looking unassessed."""
        badges = badges_from(
            {"c1": Record("positions", "indeterminate")},
            datasets=["positions"],
            established_at=WHEN,
        )
        assert badges[0].standing is Standing.NOT_ESTABLISHED
        assert "could not be established" in badges[0].render()

    def test_one_failing_control_makes_the_dataset_failing(self) -> None:
        badges = badges_from(
            {"c1": Record("positions", "pass"), "c2": Record("positions", "fail")},
            datasets=["positions"],
            established_at=WHEN,
        )
        assert badges[0].standing is Standing.FAILING
        assert "1 of 2 control(s) failing" in badges[0].render()


class TestCoverageIsNotOverstated:
    def test_a_partial_scan_says_so(self) -> None:
        """ "Passed" over the rows examined is a narrower claim than "passed"."""
        badges = badges_from(
            {"c1": Record("positions", "pass", coverage="incremental")},
            datasets=["positions"],
            established_at=WHEN,
        )
        assert badges[0].coverage != "full"
        assert "over the rows examined" in badges[0].render()

    def test_the_narrowest_contributing_scan_wins(self) -> None:
        """A badge claiming "full" because one control scanned everything, while
        another only sampled, claims more than was established."""
        badges = badges_from(
            {
                "c1": Record("positions", "pass", coverage="full"),
                "c2": Record("positions", "pass", coverage="incremental"),
            },
            datasets=["positions"],
            established_at=WHEN,
        )
        assert badges[0].coverage == "partial"

    def test_a_full_scan_does_not_add_a_caveat(self) -> None:
        badges = badges_from(
            {"c1": Record("positions", "pass")}, datasets=["positions"], established_at=WHEN
        )
        assert "over the rows examined" not in badges[0].render()


class TestNothingIsWrittenThatCannotBeTraced:
    def test_a_badge_carries_its_evidence(self) -> None:
        """The first response to a badge somebody disagrees with is "show me",
        and one that cannot answer gets ignored from then on."""
        badges = badges_from(
            {"c1": Record("positions", "fail")}, datasets=["positions"], established_at=WHEN
        )
        assert badges[0].evidence_reference

    def test_a_catalogue_without_the_field_says_it_dropped_it(self) -> None:
        """Nobody should believe the catalogue shows a reference it has no field
        for."""
        target = RecordingTarget(supports=frozenset({"standing", "established_at", "coverage"}))
        report = target.publish([badge(evidence_reference="abc")])
        assert report.written == 1
        assert "evidence_reference" in report.dropped_fields
        assert "cannot store" in report.describe()


class TestAPartialWriteIsReportedAsPartial:
    def test_one_rejection_does_not_stop_the_rest(self) -> None:
        """A catalogue rejecting one table must not leave the other thirty-nine
        showing yesterday's verdict with today's confidence."""
        target = RecordingTarget(refuse=["trades"])
        report = target.publish(
            [badge(dataset="positions"), badge(dataset="trades"), badge(dataset="ledger")]
        )
        assert report.written == 2
        assert len(report.refused) == 1

    def test_a_systemic_refusal_names_the_reason_not_the_tables(self) -> None:
        """When everything failed for one reason, listing the datasets makes a
        systemic problem look like a list of unlucky tables."""
        target = RecordingTarget(refuse=["positions", "trades"])
        described = target.publish([badge(dataset="positions"), badge(dataset="trades")]).describe()
        assert "all 2 refused for the same reason" in described

    def test_the_stale_ones_are_named_first(self) -> None:
        """Stale-but-present is worse than absent: it is a figure people act
        on."""
        target = RecordingTarget(refuse=["trades"])
        described = target.publish([badge(dataset="positions"), badge(dataset="trades")]).describe()
        assert described.startswith("1 dataset(s) were NOT updated")
        assert "stale badge: trades" in described

    def test_a_complete_write_says_so_plainly(self) -> None:
        report = RecordingTarget().publish([badge(), badge(dataset="trades")])
        assert report.complete
        assert report.describe() == "2 of 2 written."

    def test_offering_nothing_is_not_a_success(self) -> None:
        report = RecordingTarget().publish([])
        assert "nothing was offered" in report.describe()


class TestTheReferenceTarget:
    def test_it_exists_so_the_contract_can_be_tested(self) -> None:
        """An SPI whose only implementation is behind a vendor's login is an SPI
        nobody can test."""
        target = RecordingTarget()
        target.publish(
            badges_from(
                {"c1": Record("positions", "pass")},
                datasets=["positions"],
                established_at=WHEN,
            )
        )
        stored = target.badge_for("positions")
        assert stored is not None
        assert stored.standing is Standing.HEALTHY

    def test_the_dictionary_form_carries_the_rendered_sentence(self) -> None:
        payload = badge(standing=Standing.FAILING, controls=3, failing_controls=1).to_dict()
        assert payload["standing"] == "failing"
        assert payload["established_at"] == WHEN
        assert "1 of 3 control(s) failing" in payload["rendered"]
