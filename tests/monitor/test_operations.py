"""Drift, cold start, tournaments and cards: the operating side of a fleet.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.calibrate.validity import ValidityMonitor
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.monitor.cards import Outcome, PrecisionHistory, card_for
from prama.monitor.coldstart import ColdStart, Handover, PriorSource
from prama.monitor.detect import RobustDeviation
from prama.monitor.drift import (
    Acceptance,
    compare,
    find_changepoint,
    history_after,
)
from prama.monitor.season import Grouping, SeasonKey
from prama.monitor.tournament import Decision, Record, Tournament
from prama.semantic.values import Frequency, Optionality, Rhythm


def draws(count: int, centre: float, spread: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(centre, spread) for _ in range(count)]


# -- drift -------------------------------------------------------------------


def test_two_samples_from_one_distribution_are_not_a_shift() -> None:
    """A drift measure that fires here fires constantly."""
    assert not compare(draws(300, 1000, 50, 1), draws(300, 1000, 50, 2)).is_material


def test_a_real_shift_is_material_on_a_majority_of_measures() -> None:
    """A majority rather than any, because each measure has a failure mode the
    others do not share, and one firing alone is more often that measure's
    weakness than a real shift."""
    report = compare(draws(300, 1000, 50, 1), draws(300, 1250, 50, 2))
    assert report.is_material
    assert len(report.material) >= 3


def test_a_small_sample_is_refused_rather_than_reported() -> None:
    """PSI will report a shift between two draws from the same distribution."""
    report = compare(draws(20, 1000, 50, 1), draws(20, 1000, 50, 2))
    assert report.refusal
    assert not report.measures


def test_disagreement_between_measures_is_reported_as_the_signal_it_is() -> None:
    report = compare(draws(300, 1000, 50, 1), draws(300, 1000, 130, 2))
    if report.material and len(report.material) < len(report.measures):
        assert report.disagreement
        assert "only some of them look at" in report.disagreement


def test_the_earth_movers_distance_is_in_the_units_of_the_data() -> None:
    """Which makes it the one a person understands: "the typical row count
    moved by 4,100" is a sentence, where "PSI 0.31" needs training."""
    report = compare(draws(300, 1000, 50, 1), draws(300, 1250, 50, 2))
    wasserstein = next(m for m in report.measures if m.name == "wasserstein")
    assert 200 <= wasserstein.value <= 300


# -- accepting a new normal --------------------------------------------------


def test_a_changepoint_is_found_where_the_level_moved() -> None:
    series = draws(150, 1000, 50, 1) + draws(150, 1400, 50, 2)
    point = find_changepoint(series)
    assert point is not None
    assert 140 <= point.index <= 160
    assert "rose from about" in point.describe()


def test_accepting_a_new_normal_requires_a_reason() -> None:
    """Without one the record cannot distinguish a business change from
    somebody silencing an alert, which is the only question anybody asks about
    it later."""
    with pytest.raises(ValueError, match="requires a reason"):
        Acceptance(
            metric="m",
            at_index=150,
            at="2026-03-04",
            accepted_by="a.sinha",
            accepted_at="2026-03-04T10:00:00Z",
            reason="   ",
        )


def test_an_acceptance_annotates_the_chart_permanently() -> None:
    """The next person to ask "when did this change and who agreed?" gets an
    answer rather than nothing."""
    acceptance = Acceptance(
        metric="positions.row_count",
        at_index=150,
        at="2026-03-04",
        accepted_by="a.sinha",
        accepted_at="2026-03-04T10:00:00Z",
        reason="the EMEA desk was migrated onto this feed",
        before=1000,
        after=1400,
    )
    annotation = acceptance.annotation()
    assert "a.sinha" in annotation
    assert "EMEA desk was migrated" in annotation
    assert "1,000 → 1,400" in annotation


def test_the_old_regime_stops_being_evidence_after_an_acceptance() -> None:
    """Not hidden — discarded, and only from this calculation. What stops is
    treating the old regime as evidence about the new one, which is what makes
    a monitor alert every day for six months after a business change."""
    series = draws(150, 1000, 50, 1) + draws(150, 1400, 50, 2)
    acceptance = Acceptance(
        metric="m",
        at_index=150,
        at="2026-03-04",
        accepted_by="a.sinha",
        accepted_at="2026-03-04T10:00:00Z",
        reason="migration",
    )
    assert len(history_after(series, [acceptance])) == 150
    assert len(history_after(series, [])) == 300


# -- cold start --------------------------------------------------------------


def declaration() -> DatasetDeclaration:
    return DatasetDeclaration(
        name="exposures",
        domain_id="credit_risk",
        rhythm=Rhythm(
            frequency=Frequency.DAILY,
            expected_volume_min=1_000,
            expected_volume_max=50_000,
        ),
        attributes=(
            AttributeDeclaration(name="lei", semantic_type="lei"),
            AttributeDeclaration(name="amount", optionality=Optionality.MANDATORY),
            AttributeDeclaration(name="note"),
        ),
    )


def test_a_new_dataset_is_monitored_on_day_one() -> None:
    """The three months it takes to accumulate a window is exactly when a new
    feed is most likely to be wrong."""
    priors = ColdStart().for_dataset(declaration())
    assert len(priors) == 4
    assert any(prior.metric == "row_count" for prior in priors)


def test_a_semantic_type_is_the_strongest_prior_because_it_is_about_the_world() -> None:
    """An ISIN column that is 40% empty is wrong wherever it appears."""
    prior = ColdStart().for_attribute(declaration(), declaration().attributes[0])
    assert prior.source is PriorSource.SEMANTIC_TYPE
    assert prior.high <= 0.05
    assert not prior.admits(0.4)


def test_a_declared_mandatory_attribute_admits_nothing_missing() -> None:
    prior = ColdStart().for_attribute(declaration(), declaration().attributes[1])
    assert prior.source is PriorSource.DECLARATION
    assert prior.high == 0.0


def test_siblings_are_used_when_nothing_stronger_is_available() -> None:
    prior = ColdStart().for_attribute(
        declaration(), declaration().attributes[2], siblings=[0.02, 0.05, 0.08]
    )
    assert prior.source is PriorSource.SIBLINGS
    assert "comparable attributes" in prior.explanation


def test_the_estate_default_says_it_is_the_weakest_thing_available() -> None:
    prior = ColdStart().for_attribute(declaration(), declaration().attributes[2])
    assert prior.source is PriorSource.DEFAULT
    assert "the alternative is no monitoring at all" in prior.explanation


def test_a_prior_never_promises_a_false_alarm_rate() -> None:
    """Saying "0.01" next to it would be a lie of exactly the kind this wave
    exists to stop telling."""
    for prior in ColdStart().for_dataset(declaration()):
        assert not prior.is_calibrated
        assert "no false-alarm rate is promised" in prior.disclosure().lower()


def test_the_handover_from_prior_to_measurement_is_announced() -> None:
    """A monitor whose basis changes without saying so has, from the reader's
    point of view, started behaving differently for no reason."""
    prior = ColdStart().for_attribute(declaration(), declaration().attributes[0])
    handover = Handover(metric="lei.null_rate", from_prior=prior, observations=120)
    assert "now has 120 of its own observations" in handover.describe()
    assert "Until now it was judged against a prior" in handover.describe()


# -- tournament --------------------------------------------------------------


def test_a_challenger_is_held_until_it_has_been_scored_enough() -> None:
    """Below the minimum the comparison is between two samples of noise."""
    judgement = Tournament().judge(
        Record("champion", observations=1000, reviewed=50, confirmed=40),
        Record("challenger", observations=30),
    )
    assert judgement.decision is Decision.HOLD
    assert "samples of noise" in judgement.reason


def test_a_materially_better_challenger_is_promoted() -> None:
    judgement = Tournament().judge(
        Record("champion", observations=1000, reviewed=100, confirmed=60),
        Record("challenger", observations=1000, reviewed=100, confirmed=85),
    )
    assert judgement.decision is Decision.PROMOTE


def test_a_challenger_that_missed_something_the_champion_caught_needs_a_person() -> None:
    """From the desk that depended on that incident, the challenger made things
    worse. It may still be the better monitor, and that is a judgement about
    which failures matter rather than an average somebody can compute."""
    judgement = Tournament().judge(
        Record("champion", observations=1000, reviewed=100, confirmed=60),
        Record(
            "challenger",
            observations=1000,
            reviewed=100,
            confirmed=95,
            missed_that_other_caught=1,
        ),
    )
    assert judgement.decision is Decision.REFER
    assert "which failures matter" in judgement.reason


def test_a_marginal_improvement_is_not_an_improvement() -> None:
    """Promoting on it would mean promoting whichever challenger was
    luckiest."""
    judgement = Tournament().judge(
        Record("champion", observations=1000, reviewed=100, confirmed=60),
        Record("challenger", observations=1000, reviewed=100, confirmed=62),
    )
    assert judgement.decision is Decision.HOLD
    assert "luckiest" in judgement.reason


def test_a_materially_worse_challenger_is_retired() -> None:
    judgement = Tournament().judge(
        Record("champion", observations=1000, reviewed=100, confirmed=80),
        Record("challenger", observations=1000, reviewed=100, confirmed=50),
    )
    assert judgement.decision is Decision.RETIRE


def test_a_promoted_monitor_that_falls_behind_is_rolled_back() -> None:
    """The shadow period ends at promotion and the measurement does not.
    Waiting for somebody to notice is how it stays that way for a quarter."""
    reason = Tournament().should_roll_back(
        Record("new", observations=500, reviewed=40, confirmed=20),
        Record("old", observations=1000, reviewed=100, confirmed=80),
    )
    assert "Rolling back" in reason
    assert "production disagrees" in reason


# -- model cards -------------------------------------------------------------


def test_precision_rather_than_accuracy_because_accuracy_flatters_everything() -> None:
    """Accuracy on a monitor that alerts twice a year is 99.5% whatever it
    does, because it is dominated by the days nothing happened."""
    history = PrecisionHistory()
    for _ in range(10):
        history = history.with_alert()
    for confirmed in [True] * 7 + [False] * 2:
        history = history.with_outcome(Outcome(confirmed=confirmed))
    assert history.precision == pytest.approx(7 / 9)
    assert history.unreviewed == 1
    assert "still unreviewed" in history.describe()


def test_an_unreviewed_alert_is_counted_as_neither_right_nor_wrong() -> None:
    """Treating them as wrong understates the monitor and as right overstates
    it; the honest thing is to say how much of the record is unknown."""
    history = PrecisionHistory().with_alert().with_alert()
    assert history.precision is None
    assert "none of them reviewed yet" in history.describe()


def card():  # type: ignore[no-untyped-def]
    validity = ValidityMonitor(0.01)
    validity.observe_all([0.5] * 200)
    return card_for(
        "positions",
        "row_count",
        RobustDeviation(),
        alpha=0.01,
        validity=validity.report(),
        grouping=Grouping(key=SeasonKey(facets=(("day_of_week", "2"),)), members=tuple(range(23))),
        precision=PrecisionHistory(raised=34, confirmed=29, unreviewed=0),
        version="0.7.0",
    )


def test_the_card_states_what_the_monitor_is_blind_to() -> None:
    """A card that lists only strengths is the kind of document that gets
    quoted back after an incident nobody caught."""
    rendered = card().render()
    assert "Blind to" in rendered
    assert "trend or autocorrelation" in rendered


def test_the_card_carries_the_measured_precision_rather_than_a_claim() -> None:
    """ "34 alerts, 29 confirmed" is a fact; "high accuracy" is marketing, and
    an audit can tell the difference."""
    rendered = card().render()
    assert "34 alerts raised, 29 of the 34 reviewed were confirmed (85%)" in rendered


def test_the_card_says_when_the_budget_cannot_be_kept() -> None:
    """Twenty-three comparable observations cannot express a level of 0.01, and
    a card that printed the level anyway would be the lie this wave exists to
    stop."""
    rendered = card().render()
    assert "The promise cannot currently be kept" in rendered
    assert not card().budget_is_expressible


def test_the_card_is_derived_from_the_monitor_rather_than_written_about_it() -> None:
    """A hand-written card is accurate on the day it is written."""
    built = card()
    assert built.detector == RobustDeviation.name
    assert built.calibration_size == 23
    assert built.seasonal_facets == ("day_of_week",)
