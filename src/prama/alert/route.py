"""Alerts that reach the right person once, saying what to do.

`FR-ALR-001`…`009`. Everything upstream of here has been about producing the
right finding. This module is about the finding surviving contact with a
person, and almost every way alerting fails is a way of not doing that.

**The same incident must not alert every run.** A feed that has been broken for
three days and is checked hourly has produced seventy-two alerts, and the
seventy-second is indistinguishable from the first. A persistent incident is
one alert with a state that changes — opened, still open, escalated, resolved —
and the messages after the first exist to say what changed, not to repeat what
did not.

**Routing follows the fault, not the severity.** A broken schema goes to the
custodian who runs the pipeline; a wrong definition goes to the steward who
owns the meaning. Sending each to the other is how an incident spends its first
hour, and severity says nothing about which it is. Wave 6's declaration already
records both roles, which is why they are separate fields there.

**A digest is for things that do not need waking anybody**, and the test is not
severity but whether the recipient could act now if they read it. Forty
low-severity findings at three in the morning is not forty alerts, and it is
also not silence: it is one message at nine.

**What to do beats what happened.** "positions.counterparty_lei validity 62%"
is a fact. "62% of counterparty LEIs are malformed; the feed's vendor mapping
changed at 05:30; FINREP line 23 is downstream" is a fact with a next step in
it, and the difference costs nothing to produce and everything to omit.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from prama.security.egress import Gate, ResidencyRefused

#: How long an alert stays quiet after being sent, unless something changes.
#: Long enough that an hourly check does not become an hourly alert, short
#: enough that a forgotten incident resurfaces within a working day.
DEFAULT_QUIET = timedelta(hours=6)

#: Below this, an alert waits for the digest. Not a severity threshold — see
#: :meth:`Alert.needs_immediate`.
DIGEST_CEILING = 0.5


class Role(enum.Enum):
    """Who to tell, chosen by what kind of fault it is.

    Severity says nothing about which of these it is, which is why routing on
    severity sends half of everything to the wrong person.
    """

    #: Owns the meaning. A wrong definition, a mis-declared domain, a business
    #: rule that no longer matches the business.
    STEWARD = "steward"
    #: Runs the pipeline. A broken schema, a feed that did not arrive, a job
    #: that failed.
    CUSTODIAN = "custodian"
    #: Accountable for the data. Told about things that breach a service level
    #: or an obligation, and not about the ones being handled.
    OWNER = "owner"

    @property
    def handles(self) -> str:
        return {
            Role.STEWARD: "what the data means",
            Role.CUSTODIAN: "how the data arrives",
            Role.OWNER: "whether the promise about it is being kept",
        }[self]


class Fault(enum.Enum):
    """What kind of problem this is, which decides who hears about it."""

    ARRIVAL = "arrival"
    SCHEMA = "schema"
    VALUE = "value"
    DEFINITION = "definition"
    RECONCILIATION = "reconciliation"
    CALIBRATION = "calibration"

    @property
    def route_to(self) -> Role:
        return {
            Fault.ARRIVAL: Role.CUSTODIAN,
            Fault.SCHEMA: Role.CUSTODIAN,
            # A value problem is usually a source problem, and the steward is
            # the one who can say whether the value is wrong or the rule is.
            Fault.VALUE: Role.STEWARD,
            Fault.DEFINITION: Role.STEWARD,
            Fault.RECONCILIATION: Role.STEWARD,
            # A monitor that has stopped being calibrated is Prama's problem,
            # not the business's, and telling a steward about it teaches them
            # to ignore Prama's messages.
            Fault.CALIBRATION: Role.CUSTODIAN,
        }[self]


class Delivery(enum.Enum):
    IMMEDIATE = "immediate"
    DIGEST = "digest"
    #: Sent nowhere. Recorded, visible on the dashboard, and not pushed —
    #: which is different from suppressed, because the finding still exists.
    QUIET = "quiet"


@dataclasses.dataclass(frozen=True, slots=True)
class Recipient:
    identity: str
    role: Role
    channel: str = "email"
    #: Where this recipient's channel delivers. Needed because an alert body
    #: quotes failing values, so sending one is a movement of the tenant's data
    #: and not merely a notification.
    region: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "role": self.role.value,
            "channel": self.channel,
            "region": self.region,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Alert:
    """One thing worth telling somebody, composed to be acted on."""

    identity: str
    dataset: str
    fault: Fault
    #: What happened, in the business's terms.
    what: str
    #: Why it matters — the downstream consequence, when one is known.
    consequence: str = ""
    #: The likeliest cause and how to check it, from the RCA.
    likely_cause: str = ""
    #: Severity on 0..1, from the score or the monitor. Used for ordering and
    #: for the digest test, never on its own for routing.
    severity: float = 0.5
    at: datetime | None = None
    #: Set when this monitor's own calibration has degraded. Carried onto the
    #: alert rather than left on a dashboard, because the person reading this
    #: at three in the morning is not on the dashboard.
    disclosure: str = ""
    #: Where the alerting dataset's data belongs. The residency question is
    #: about the subject, and an egress that knows its destination but not its
    #: subject's home cannot answer it.
    jurisdiction: str = ""
    #: Findings this stands for, when it is an incident.
    covers: int = 1

    @property
    def fingerprint(self) -> str:
        """What makes two alerts the same alert.

        The dataset and the fault, not the message. A message that changes
        slightly between runs — a count, a percentage — would make every run a
        new alert, which is the failure this whole module is about.
        """
        return hashlib.sha256(
            f"{self.dataset}|{self.fault.value}|{self.identity}".encode()
        ).hexdigest()[:16]

    @property
    def needs_immediate(self) -> bool:
        """Whether this should wake somebody.

        The test is not severity alone. A high-severity finding nobody can act
        on until the vendor opens is not an immediate alert, and a
        low-severity one blocking a submission in an hour is. Severity is a
        component; consequence is the rest.
        """
        if self.consequence and "blocks" in self.consequence.lower():
            return True
        return self.severity >= DIGEST_CEILING

    def compose(self) -> str:
        """The message. What to do, not only what happened."""
        parts = [self.what]
        if self.covers > 1:
            parts.append(f"({self.covers} findings, one incident)")
        if self.consequence:
            parts.append(self.consequence)
        if self.likely_cause:
            parts.append(f"Likeliest cause: {self.likely_cause}")
        if self.disclosure:
            parts.append(f"⚠ {self.disclosure}")
        return " ".join(part.rstrip(".") + "." for part in parts if part)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "dataset": self.dataset,
            "fault": self.fault.value,
            "severity": round(self.severity, 4),
            "fingerprint": self.fingerprint,
            "needs_immediate": self.needs_immediate,
            "covers": self.covers,
            "at": self.at.isoformat() if self.at else None,
            "message": self.compose(),
        }


class Change(enum.Enum):
    """What happened to an alert that had already been sent."""

    OPENED = "opened"
    #: Still open and nothing has changed. The message nobody needs, and the
    #: reason a quiet period exists.
    UNCHANGED = "unchanged"
    WORSENED = "worsened"
    IMPROVED = "improved"
    RESOLVED = "resolved"

    @property
    def worth_sending(self) -> bool:
        """Whether this state change is worth another message.

        Everything except "still broken". A persistent incident is one alert
        whose state changes; the messages after the first exist to say what
        changed, not to repeat what did not.
        """
        return self is not Change.UNCHANGED


@dataclasses.dataclass(frozen=True, slots=True)
class Dispatch:
    """One alert, and what was decided about sending it."""

    alert: Alert
    delivery: Delivery
    change: Change
    recipients: tuple[Recipient, ...] = ()
    reason: str = ""

    @property
    def sent(self) -> bool:
        return self.delivery is not Delivery.QUIET and self.change.worth_sending

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert": self.alert.to_dict(),
            "delivery": self.delivery.value,
            "change": self.change.value,
            "sent": self.sent,
            "recipients": [person.to_dict() for person in self.recipients],
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Digest:
    """Everything that did not need waking anybody, in one message."""

    at: datetime
    dispatches: tuple[Dispatch, ...] = ()

    def __len__(self) -> int:
        return len(self.dispatches)

    def compose(self) -> str:
        if not self.dispatches:
            return "nothing to report"
        by_dataset: dict[str, int] = {}
        for dispatch in self.dispatches:
            key = dispatch.alert.dataset
            by_dataset[key] = by_dataset.get(key, 0) + 1
        head = (
            f"{len(self.dispatches)} findings across {len(by_dataset)} datasets since "
            f"the last digest"
        )
        worst = sorted(self.dispatches, key=lambda item: -item.alert.severity)[:5]
        return head + ". " + " ".join(f"{item.alert.compose()}" for item in worst)

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "count": len(self.dispatches),
            "message": self.compose(),
        }


class Router:
    """Decides who hears about what, and whether they hear it twice."""

    def __init__(
        self,
        contacts: Mapping[tuple[str, Role], str],
        *,
        quiet: timedelta = DEFAULT_QUIET,
        channels: Mapping[Role, str] | None = None,
        channel_regions: Mapping[str, str] | None = None,
        gate: Gate | None = None,
    ) -> None:
        #: (dataset, role) → person. Missing entries fall back to the owner,
        #: and an alert with nobody at all is reported rather than dropped.
        self._contacts = dict(contacts)
        self._quiet = quiet
        self._channels = dict(channels or {})
        #: channel → where it delivers. A region belongs to the channel, not to
        #: the person: the same steward reachable on an in-region chat tool and
        #: on an external pager is two different residency answers.
        self._channel_regions = dict(channel_regions or {})
        self._sent: dict[str, tuple[datetime, float]] = {}
        #: The residency check. Optional, because most deployments have no
        #: obligation and a required argument would be one every caller passes
        #: None to — but where there is a rule, an alert body quoting failing
        #: values is data leaving, and it is checked before it goes.
        self._gate = gate

    def dispatch(self, alert: Alert) -> Dispatch:
        """One alert, routed and deduplicated."""
        change = self._change(alert)
        recipients = self._recipients(alert)

        if not recipients:
            return Dispatch(
                alert=alert,
                delivery=Delivery.QUIET,
                change=change,
                reason=(
                    f"nobody is recorded as {alert.fault.route_to.value} for "
                    f"{alert.dataset}, and an alert with no recipient is a finding "
                    f"nobody will see. Assign one"
                ),
            )

        blocked = self._residency_refusals(alert, recipients)
        if blocked:
            # Not dropped and not partly sent: an alert delivered to some of
            # its recipients and silently withheld from others is worse than
            # either, because the ones who got it assume everyone did.
            return Dispatch(
                alert=alert,
                delivery=Delivery.QUIET,
                change=change,
                recipients=recipients,
                reason=(
                    "withheld on residency: " + "; ".join(blocked) + ". The alert body "
                    "quotes failing values, so sending it moves the tenant's data"
                ),
            )

        if not change.worth_sending:
            return Dispatch(
                alert=alert,
                delivery=Delivery.QUIET,
                change=change,
                recipients=recipients,
                reason=(
                    f"already open and unchanged; the last message went out within "
                    f"the {self._quiet} quiet period"
                ),
            )

        if alert.at is not None:
            self._sent[alert.fingerprint] = (alert.at, alert.severity)

        delivery = Delivery.IMMEDIATE if alert.needs_immediate else Delivery.DIGEST
        return Dispatch(
            alert=alert,
            delivery=delivery,
            change=change,
            recipients=recipients,
            reason=(
                "blocks a submission"
                if delivery is Delivery.IMMEDIATE and "blocks" in alert.consequence.lower()
                else (
                    f"severity {alert.severity:.2f}"
                    + (
                        " is above the immediate threshold"
                        if delivery is Delivery.IMMEDIATE
                        else " does not need waking anybody, and is not nothing either"
                    )
                )
            ),
        )

    def _residency_refusals(self, alert: Alert, recipients: Sequence[Recipient]) -> list[str]:
        """Which recipients this alert may not reach, and why."""
        if self._gate is None:
            return []
        refused = []
        for person in recipients:
            try:
                self._gate.require(
                    "alert-delivery",
                    destination=person.region,
                    jurisdiction=alert.jurisdiction,
                    subject=f"an alert about {alert.dataset}",
                )
            except ResidencyRefused as refusal:
                refused.append(f"{person.identity} ({refusal.message})")
        return refused

    def dispatch_all(self, alerts: Sequence[Alert]) -> tuple[Dispatch, ...]:
        return tuple(self.dispatch(alert) for alert in alerts)

    def digest(self, dispatches: Sequence[Dispatch], *, at: datetime) -> Digest:
        return Digest(
            at=at,
            dispatches=tuple(item for item in dispatches if item.delivery is Delivery.DIGEST),
        )

    def resolve(self, alert: Alert) -> Dispatch:
        """Tell people it is over.

        Sent even when the opening alert was a digest item, because "that thing
        is fixed" is the message people most want and least often get, and its
        absence is why nobody believes a dashboard.
        """
        self._sent.pop(alert.fingerprint, None)
        recipients = self._recipients(alert)

        blocked = self._residency_refusals(alert, recipients)
        if blocked:
            # The same gate `dispatch` applies, for the same reason. It was
            # missing here, so an alert correctly withheld on residency was
            # followed by a resolution that went out regardless (QA finding
            # INC-071) — the residency rule holding for the bad news and not
            # for the good.
            #
            # A resolution is not a smaller disclosure than an alert. It names
            # the dataset and the control, and "this is fixed now" tells a
            # reader what was wrong a moment ago. Whether the body quotes a
            # value is not the question; that the message crosses the boundary
            # at all is.
            return Dispatch(
                alert=alert,
                delivery=Delivery.QUIET,
                change=Change.RESOLVED,
                recipients=recipients,
                reason=(
                    "withheld on residency: " + "; ".join(blocked) + ". A resolution "
                    "names the dataset and the control it was raised on, so it moves "
                    "the tenant's data as surely as the alert did"
                ),
            )

        return Dispatch(
            alert=alert,
            delivery=Delivery.IMMEDIATE if alert.needs_immediate else Delivery.DIGEST,
            change=Change.RESOLVED,
            recipients=recipients,
            reason="resolved",
        )

    # -- deduplication -----------------------------------------------------

    def _change(self, alert: Alert) -> Change:
        previous = self._sent.get(alert.fingerprint)
        if previous is None:
            return Change.OPENED
        when, severity = previous
        if alert.at is not None and alert.at - when >= self._quiet:
            # The quiet period has expired. A forgotten incident should
            # resurface within a working day rather than never.
            return Change.WORSENED if alert.severity > severity else Change.OPENED
        if alert.severity > severity + 0.1:
            return Change.WORSENED
        if alert.severity < severity - 0.1:
            return Change.IMPROVED
        return Change.UNCHANGED

    def _recipients(self, alert: Alert) -> tuple[Recipient, ...]:
        role = alert.fault.route_to
        people: list[Recipient] = []
        primary = self._contacts.get((alert.dataset, role))
        if primary:
            people.append(self._recipient(primary, role))
        elif self._contacts.get((alert.dataset, Role.OWNER)):
            # Falling back to the owner rather than dropping it. The owner is
            # accountable and can reassign; nobody is a black hole.
            people.append(self._recipient(self._contacts[(alert.dataset, Role.OWNER)], Role.OWNER))
        return tuple(people)

    def _recipient(self, identity: str, role: Role) -> Recipient:
        channel = self._channels.get(role, "email")
        return Recipient(
            identity=identity,
            role=role,
            channel=channel,
            region=self._channel_regions.get(channel, ""),
        )
