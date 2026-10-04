"""Live-shadow evaluation.

docs/corpus/15 §2.3: run beside the incumbent for ninety days, take no production
actions, and have the customer's own stewards adjudicate every alert **blind to
which system raised it**.

The blinding is the design. A steward who knows which alert came from the tool
being evaluated judges it differently — in both directions, and neither is
measurable afterwards — so most of these tests are about an alert being
impossible to attribute while it is being judged.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.bench.shadow import Blinding, Judgement, ShadowAlert, evaluate

WINDOW = {"window_start": "2026-06-01", "window_end": "2026-08-31"}


def alert(system: str = "prama", **kw) -> ShadowAlert:
    return ShadowAlert(
        system=system,
        dataset=kw.pop("dataset", "positions"),
        column=kw.pop("column", "notional"),
        raised_at=kw.pop("raised_at", "2026-07-01"),
        detail=kw.pop("detail", ""),
        **kw,
    )


class TestTheBlinding:
    def test_what_a_steward_sees_carries_no_system(self) -> None:
        """A harness that handed a steward a record carrying the system name —
        even in a field nobody displays — has unblinded the study, and nothing
        afterwards can measure the effect."""
        blinding = Blinding([alert("prama"), alert("incumbent", column="quantity")])
        for row in blinding.for_adjudication():
            assert "system" not in row
            assert "prama" not in repr(row)
            assert "incumbent" not in repr(row)

    def test_the_identifier_does_not_betray_arrival_order(self) -> None:
        """A sequence number betrays which system was registered first, and a
        steward who notices has been unblinded by the harness itself."""
        first = alert("prama", detail="a")
        second = alert("incumbent", detail="b")
        forwards = Blinding([first, second]).for_adjudication()
        backwards = Blinding([second, first]).for_adjudication()
        assert [row["blind_id"] for row in forwards] == [row["blind_id"] for row in backwards]

    def test_the_queue_is_not_ordered_by_arrival(self) -> None:
        """Sorting by arrival groups a system's alerts together and a steward
        notices the pattern within an afternoon."""
        blinding = Blinding(
            [alert("prama", detail=f"p{n}") for n in range(5)]
            + [alert("incumbent", detail=f"i{n}") for n in range(5)]
        )
        identifiers = [row["blind_id"] for row in blinding.for_adjudication()]
        assert identifiers == sorted(identifiers)

    def test_the_mapping_survives_for_scoring(self) -> None:
        blinding = Blinding([alert("prama")])
        [row] = blinding.for_adjudication()
        resolved = blinding.resolve(row["blind_id"])
        assert resolved is not None
        assert resolved.system == "prama"


class TestUnjudgedIsNotFalse:
    def test_precision_is_over_what_was_judged(self) -> None:
        """Treating everything unjudged as wrong punishes the system that
        raised more than the stewards had time to look at — which is the system
        raising them fastest, and exactly backwards."""
        alerts = [alert(detail=str(n)) for n in range(10)]
        blinding = Blinding(alerts)
        judged = [
            Judgement(alerts[0].blind_id, "real"),
            Judgement(alerts[1].blind_id, "false"),
        ]
        result = evaluate(blinding, judged, **WINDOW).of("prama")
        assert result is not None
        assert result.precision == 0.5
        assert result.unjudged == 8

    def test_the_examined_share_is_reported_beside_it(self) -> None:
        """Precision of 0.95 over four per cent of the alerts is a different
        claim from one over all of them, and only this number separates them."""
        alerts = [alert(detail=str(n)) for n in range(10)]
        result = evaluate(Blinding(alerts), [Judgement(alerts[0].blind_id, "real")], **WINDOW).of(
            "prama"
        )
        assert result is not None
        assert result.examined_share == 0.1
        assert "over the 10% of 10 alert(s) that were judged" in result.describe()

    def test_nothing_judged_gives_no_precision_rather_than_zero(self) -> None:
        result = evaluate(Blinding([alert()]), [], **WINDOW).of("prama")
        assert result is not None
        assert result.precision is None
        assert "not measurable from this run" in result.describe()

    def test_unclear_counts_as_neither(self) -> None:
        """A steward who could not tell has not said the alert was wrong."""
        one = alert(detail="a")
        result = evaluate(Blinding([one]), [Judgement(one.blind_id, "unclear")], **WINDOW).of(
            "prama"
        )
        assert result is not None
        assert result.unclear == 1
        assert result.precision is None


class TestTheWindowIsTheSameForBoth:
    def test_alerts_outside_it_are_dropped_from_both_sides(self) -> None:
        """A tool that started three days late has three days of free
        silence."""
        blinding = Blinding(
            [
                alert("prama", raised_at="2026-05-01"),
                alert("prama", raised_at="2026-07-01"),
                alert("incumbent", raised_at="2026-09-30", column="q"),
            ]
        )
        result = evaluate(blinding, [], **WINDOW)
        assert dict(result.outside_window) == {"prama": 1, "incumbent": 1}
        assert result.of("prama").raised == 1
        assert result.of("incumbent").raised == 0

    def test_the_drop_is_stated_in_the_summary(self) -> None:
        blinding = Blinding([alert("prama", raised_at="2026-05-01")])
        described = evaluate(blinding, [], **WINDOW).describe()
        assert "outside the window were dropped from both sides" in described
        assert "free silence" in described


class TestBurdenIsHalfTheAnswer:
    def test_alerts_per_steward_week_is_reported(self) -> None:
        """A system can win on precision and still be unusable because it
        raises forty times as many."""
        alerts = [alert(detail=str(n)) for n in range(40)]
        result = evaluate(Blinding(alerts), [], steward_weeks=4.0, **WINDOW).of("prama")
        assert result is not None
        assert result.alerts_per_steward_week == 10.0

    def test_only_a_rejected_alert_wastes_time(self) -> None:
        """An alert that found something took time and bought something for
        it."""
        good, bad = alert(detail="a"), alert(detail="b")
        result = evaluate(
            Blinding([good, bad]),
            [
                Judgement(good.blind_id, "real", minutes=30),
                Judgement(bad.blind_id, "false", minutes=30),
            ],
            steward_weeks=1.0,
            **WINDOW,
        ).of("prama")
        assert result is not None
        assert result.minutes_spent == 60
        assert result.wasted_minutes == 30
        assert result.wasted_hours_per_week == 0.5

    def test_burden_is_none_when_no_effort_was_recorded(self) -> None:
        """Dividing by an unstated number of steward-weeks would invent a
        figure."""
        result = evaluate(Blinding([alert()]), [], **WINDOW).of("prama")
        assert result is not None
        assert result.alerts_per_steward_week is None
        assert result.wasted_hours_per_week is None


class TestBothSystemsAreScored:
    def test_each_gets_its_own_result(self) -> None:
        mine = alert("prama", detail="a")
        theirs = alert("incumbent", detail="b")
        blinding = Blinding([mine, theirs])
        result = evaluate(
            blinding,
            [
                Judgement(mine.blind_id, "real"),
                Judgement(theirs.blind_id, "false"),
            ],
            **WINDOW,
        )
        assert result.of("prama").precision == 1.0
        assert result.of("incumbent").precision == 0.0

    def test_the_summary_carries_both(self) -> None:
        blinding = Blinding([alert("prama"), alert("incumbent", column="q")])
        described = evaluate(blinding, [], **WINDOW).describe()
        assert "prama" in described
        assert "incumbent" in described

    def test_the_dictionary_form_is_machine_readable(self) -> None:
        one = alert("prama")
        payload = evaluate(Blinding([one]), [Judgement(one.blind_id, "real")], **WINDOW).to_dict()
        assert payload["window_start"] == "2026-06-01"
        assert payload["systems"][0]["precision"] == 1.0
        assert "message" in payload
