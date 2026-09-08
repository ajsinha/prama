"""Alerts that reach the right person once.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from prama.alert.route import (
    Alert,
    Change,
    Delivery,
    Fault,
    Role,
    Router,
)

BASE = datetime(2026, 4, 1, 6, 0)

CONTACTS = {
    ("positions", Role.STEWARD): "s.owner",
    ("positions", Role.CUSTODIAN): "c.runner",
    ("positions", Role.OWNER): "o.accountable",
    ("orphan", Role.OWNER): "o.accountable",
}


def alert(**overrides: object) -> Alert:
    base: dict[str, object] = {
        "identity": "a1",
        "dataset": "positions",
        "fault": Fault.VALUE,
        "what": "62% of counterparty LEIs are malformed",
        "severity": 0.8,
        "at": BASE,
    }
    base.update(overrides)
    return Alert(**base)  # type: ignore[arg-type]


# -- the same incident must not alert every run ------------------------------


def test_a_persistent_incident_alerts_once() -> None:
    """A feed broken for three days and checked hourly has produced
    seventy-two alerts, and the seventy-second is indistinguishable from the
    first."""
    router = Router(CONTACTS)
    first = router.dispatch(alert())
    assert first.change is Change.OPENED
    assert first.sent

    for hour in range(1, 6):
        repeat = router.dispatch(alert(at=BASE + timedelta(hours=hour)))
        assert repeat.change is Change.UNCHANGED
        assert not repeat.sent


def test_a_worsening_incident_says_what_changed() -> None:
    """The messages after the first exist to say what changed, not to repeat
    what did not."""
    router = Router(CONTACTS)
    router.dispatch(alert(severity=0.5))
    worse = router.dispatch(alert(severity=0.9, at=BASE + timedelta(minutes=30)))
    assert worse.change is Change.WORSENED
    assert worse.sent


def test_an_improving_incident_is_also_worth_a_message() -> None:
    router = Router(CONTACTS)
    router.dispatch(alert(severity=0.9))
    better = router.dispatch(alert(severity=0.6, at=BASE + timedelta(minutes=30)))
    assert better.change is Change.IMPROVED
    assert better.sent


def test_a_forgotten_incident_resurfaces_within_a_working_day() -> None:
    """Quiet is not silence."""
    router = Router(CONTACTS)
    router.dispatch(alert())
    later = router.dispatch(alert(at=BASE + timedelta(hours=7)))
    assert later.sent


def test_the_fingerprint_does_not_move_when_the_message_does() -> None:
    """A count or a percentage changing between runs would make every run a new
    alert, which is the failure this module is about."""
    assert alert(what="62% malformed").fingerprint == alert(what="63% malformed").fingerprint


def test_resolution_is_told_because_nobody_ever_gets_told() -> None:
    """ "That thing is fixed" is the message people most want and least often
    get, and its absence is why nobody believes a dashboard."""
    router = Router(CONTACTS)
    router.dispatch(alert())
    resolved = router.resolve(alert(at=BASE + timedelta(hours=2)))
    assert resolved.change is Change.RESOLVED
    assert resolved.sent


def test_a_resolved_incident_can_reopen() -> None:
    router = Router(CONTACTS)
    router.dispatch(alert())
    router.resolve(alert(at=BASE + timedelta(hours=1)))
    again = router.dispatch(alert(at=BASE + timedelta(hours=2)))
    assert again.change is Change.OPENED
    assert again.sent


# -- routing follows the fault -----------------------------------------------


def test_a_broken_feed_goes_to_the_custodian_and_a_wrong_meaning_to_the_steward() -> None:
    """Sending each to the other is how an incident spends its first hour, and
    severity says nothing about which it is."""
    router = Router(CONTACTS)
    arrival = router.dispatch(alert(fault=Fault.ARRIVAL))
    definition = router.dispatch(alert(identity="a2", fault=Fault.DEFINITION))
    assert arrival.recipients[0].identity == "c.runner"
    assert definition.recipients[0].identity == "s.owner"


def test_a_calibration_problem_is_pramas_and_not_the_business_s() -> None:
    """Telling a steward that a monitor stopped being calibrated teaches them
    to ignore Prama's messages."""
    assert Fault.CALIBRATION.route_to is Role.CUSTODIAN


def test_an_unassigned_role_falls_back_to_the_owner_rather_than_nowhere() -> None:
    """The owner is accountable and can reassign; nobody is a black hole."""
    router = Router(CONTACTS)
    dispatched = router.dispatch(alert(dataset="orphan", fault=Fault.SCHEMA))
    assert dispatched.recipients[0].identity == "o.accountable"


def test_an_alert_with_no_recipient_at_all_says_so_rather_than_vanishing() -> None:
    router = Router({})
    dispatched = router.dispatch(alert())
    assert not dispatched.sent
    assert "an alert with no recipient is a finding nobody will see" in dispatched.reason


def test_every_role_can_say_what_it_handles() -> None:
    for role in Role:
        assert role.handles


# -- digest ------------------------------------------------------------------


def test_a_low_severity_finding_waits_for_the_digest() -> None:
    """Forty low-severity findings at three in the morning is not forty alerts,
    and it is also not silence."""
    router = Router(CONTACTS)
    dispatched = router.dispatch(alert(severity=0.2))
    assert dispatched.delivery is Delivery.DIGEST
    assert dispatched.sent


def test_something_that_blocks_a_submission_wakes_somebody_whatever_its_severity() -> None:
    """A high-severity finding nobody can act on until the vendor opens is not
    an immediate alert, and a low-severity one blocking a submission in an hour
    is."""
    router = Router(CONTACTS)
    dispatched = router.dispatch(
        alert(severity=0.2, consequence="blocks the FR Y-14Q submission at 17:00")
    )
    assert dispatched.delivery is Delivery.IMMEDIATE
    assert "blocks a submission" in dispatched.reason


def test_the_digest_gathers_what_did_not_need_waking_anybody() -> None:
    router = Router(CONTACTS)
    dispatches = router.dispatch_all(
        [alert(identity=f"a{index}", severity=0.2) for index in range(40)]
    )
    digest = router.digest(dispatches, at=BASE + timedelta(hours=3))
    assert len(digest) == 40
    assert "40 findings across 1 datasets" in digest.compose()


def test_an_empty_digest_says_nothing_to_report() -> None:
    router = Router(CONTACTS)
    assert "nothing to report" in router.digest([], at=BASE).compose()


# -- composition -------------------------------------------------------------


def test_the_message_carries_what_to_do_rather_than_only_what_happened() -> None:
    """The difference costs nothing to produce and everything to omit."""
    composed = alert(
        consequence="FINREP line 23 is downstream",
        likely_cause="the vendor mapping changed at 05:30 — read change c9",
    ).compose()
    assert "62% of counterparty LEIs are malformed" in composed
    assert "FINREP line 23 is downstream" in composed
    assert "Likeliest cause" in composed


def test_an_incident_says_how_many_findings_it_stands_for() -> None:
    assert "(48 findings, one incident)" in alert(covers=48).compose()


def test_a_degraded_monitor_discloses_on_the_alert_itself() -> None:
    """The person reading this at three in the morning is not on the
    dashboard."""
    composed = alert(
        disclosure="uncalibrated — this monitor promised 1% and is running at 12%"
    ).compose()
    assert "⚠" in composed
    assert "uncalibrated" in composed
