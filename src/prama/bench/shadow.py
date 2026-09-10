"""Live-shadow evaluation: the only measurement a buyer believes.

docs/15 §2.3 describes running Prama beside the incumbent for ninety days on the
same sources, taking no production actions, and having the customer's own
stewards adjudicate every alert **blind to which system raised it**.

The blinding is not a nicety. A steward who knows an alert came from the tool
being evaluated judges it differently — in both directions, and neither
direction is measurable afterwards. So this harness's central job is to make an
alert impossible to attribute while it is being judged, and to keep the mapping
so the numbers can be produced when judging is finished.

Three further rules, each of which a shadow run gets wrong by default:

* **An unadjudicated alert is not a false positive.** The obvious arithmetic —
  everything not confirmed is wrong — punishes a system for raising more than
  the stewards had time to look at, which is the system raising them fastest.
  Unjudged alerts are excluded from precision and their count is reported, so
  the figure carries how much of it was actually examined.
* **Both systems must be measured over the same window.** A tool that started
  three days late has three days of free silence. The window is stated and
  alerts outside it are dropped from both sides, loudly.
* **Precision without burden is half the answer.** Alerts per steward-week and
  wasted hours are what a buyer feels; a system can win on precision and still
  be unusable because it raises forty times as many.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Iterable, Sequence
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class ShadowAlert:
    """One alert, from one system, before anybody has judged it."""

    system: str
    dataset: str
    column: str
    raised_at: str
    detail: str = ""
    reference: str = ""

    @property
    def blind_id(self) -> str:
        """A stable identifier that does not reveal the system.

        Hashed over the *content* rather than assigned a sequence number: a
        sequence betrays which system was registered first, and a steward who
        notices that has been unblinded by the harness itself.
        """
        material = f"{self.dataset}|{self.column}|{self.raised_at}|{self.detail}|{self.reference}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


@dataclasses.dataclass(frozen=True, slots=True)
class Judgement:
    """A steward's verdict on one blinded alert."""

    blind_id: str
    #: ``real`` · ``false`` · ``unclear``
    verdict: str
    #: Minutes spent. Carried because wasted-hours is the number a buyer feels,
    #: and it cannot be recovered later.
    minutes: float = 0.0
    note: str = ""

    @property
    def is_decided(self) -> bool:
        return self.verdict in ("real", "false")


@dataclasses.dataclass(frozen=True, slots=True)
class SystemResult:
    """One system's numbers over the window."""

    system: str
    raised: int
    confirmed: int
    rejected: int
    unclear: int
    unjudged: int
    minutes_spent: float
    wasted_minutes: float
    steward_weeks: float

    @property
    def adjudicated(self) -> int:
        return self.confirmed + self.rejected

    @property
    def precision(self) -> float | None:
        """Confirmed over adjudicated. ``None`` when nothing was judged.

        Deliberately **not** confirmed over raised. Treating everything
        unjudged as wrong punishes the system that raised more than the
        stewards had time to look at — which is the system raising them
        fastest, and exactly backwards.
        """
        return None if self.adjudicated == 0 else self.confirmed / self.adjudicated

    @property
    def examined_share(self) -> float | None:
        """How much of what was raised anybody actually looked at.

        Reported beside precision always. A precision of 0.95 over four per cent
        of the alerts is a different claim from one over all of them, and only
        this number separates them.
        """
        return None if self.raised == 0 else self.adjudicated / self.raised

    @property
    def alerts_per_steward_week(self) -> float | None:
        return None if self.steward_weeks <= 0 else self.raised / self.steward_weeks

    @property
    def wasted_hours_per_week(self) -> float | None:
        if self.steward_weeks <= 0:
            return None
        return (self.wasted_minutes / 60.0) / self.steward_weeks

    def describe(self) -> str:
        if not self.raised:
            return f"{self.system}: raised nothing in this window"
        precision = self.precision
        share = self.examined_share
        if precision is None:
            return (
                f"{self.system}: {self.raised} alert(s), none adjudicated — "
                "precision is not measurable from this run"
            )
        assert share is not None
        parts = [
            f"{self.system}: precision {precision:.0%} over the {share:.0%} of "
            f"{self.raised} alert(s) that were judged"
        ]
        burden = self.alerts_per_steward_week
        wasted = self.wasted_hours_per_week
        if burden is not None:
            parts.append(f"{burden:.0f} alerts per steward-week")
        if wasted is not None:
            parts.append(f"{wasted:.1f} wasted hours a week")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "raised": self.raised,
            "confirmed": self.confirmed,
            "rejected": self.rejected,
            "unclear": self.unclear,
            "unjudged": self.unjudged,
            "precision": self.precision,
            "examined_share": self.examined_share,
            "alerts_per_steward_week": self.alerts_per_steward_week,
            "wasted_hours_per_week": self.wasted_hours_per_week,
            "message": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ShadowResult:
    """A whole shadow run, both systems, one window."""

    window_start: str
    window_end: str
    systems: tuple[SystemResult, ...] = ()
    #: Alerts dropped because they fell outside the window. Counted per system,
    #: because a tool that started three days late has three days of free
    #: silence and the comparison has to say so.
    outside_window: tuple[tuple[str, int], ...] = ()

    def of(self, system: str) -> SystemResult | None:
        return next((s for s in self.systems if s.system == system), None)

    def describe(self) -> str:
        head = f"{self.window_start} to {self.window_end}"
        if self.outside_window:
            dropped = ", ".join(f"{name}: {count}" for name, count in self.outside_window)
            head += (
                f" — alerts outside the window were dropped from both sides ({dropped}), "
                "because a tool that started late would otherwise get free silence"
            )
        return head + ". " + " | ".join(system.describe() for system in self.systems)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "systems": [system.to_dict() for system in self.systems],
            "outside_window": [
                {"system": name, "dropped": count} for name, count in self.outside_window
            ],
            "message": self.describe(),
        }


class Blinding:
    """Holds which system raised what, so the stewards cannot know.

    The mapping is kept here and nowhere the adjudication interface can reach.
    A harness that handed a steward a record carrying the system name — even in
    a field nobody displays — has unblinded the study, and nothing afterwards
    can measure the effect.
    """

    def __init__(self, alerts: Iterable[ShadowAlert] = ()) -> None:
        self._by_blind: dict[str, ShadowAlert] = {}
        for alert in alerts:
            self.register(alert)

    def register(self, alert: ShadowAlert) -> str:
        self._by_blind[alert.blind_id] = alert
        return alert.blind_id

    def __len__(self) -> int:
        return len(self._by_blind)

    def for_adjudication(self) -> list[dict[str, Any]]:
        """What a steward sees. Sorted by the blind id, never by arrival.

        Sorting by arrival groups a system's alerts together and a steward
        notices the pattern within an afternoon.
        """
        return [
            {
                "blind_id": alert.blind_id,
                "dataset": alert.dataset,
                "column": alert.column,
                "raised_at": alert.raised_at,
                "detail": alert.detail,
            }
            for alert in sorted(self._by_blind.values(), key=lambda a: a.blind_id)
        ]

    def systems(self) -> tuple[str, ...]:
        return tuple(sorted({alert.system for alert in self._by_blind.values()}))

    def resolve(self, blind_id: str) -> ShadowAlert | None:
        return self._by_blind.get(blind_id)

    def alerts(self) -> tuple[ShadowAlert, ...]:
        return tuple(self._by_blind.values())


def evaluate(
    blinding: Blinding,
    judgements: Sequence[Judgement],
    *,
    window_start: str,
    window_end: str,
    steward_weeks: float = 0.0,
) -> ShadowResult:
    """Turn a blinded run and its judgements into numbers.

    Alerts outside the window are dropped from *both* sides and counted, and
    unjudged alerts are excluded from precision rather than counted against the
    system that raised them.
    """
    by_blind = {judgement.blind_id: judgement for judgement in judgements}

    inside: dict[str, list[ShadowAlert]] = {}
    dropped: dict[str, int] = {}
    for alert in blinding.alerts():
        bucket = inside if window_start <= alert.raised_at <= window_end else None
        if bucket is None:
            dropped[alert.system] = dropped.get(alert.system, 0) + 1
            continue
        bucket.setdefault(alert.system, []).append(alert)

    results: list[SystemResult] = []
    for system in blinding.systems():
        alerts = inside.get(system, [])
        confirmed = rejected = unclear = unjudged = 0
        minutes = wasted = 0.0
        for alert in alerts:
            judgement = by_blind.get(alert.blind_id)
            if judgement is None:
                unjudged += 1
                continue
            minutes += judgement.minutes
            if judgement.verdict == "real":
                confirmed += 1
            elif judgement.verdict == "false":
                rejected += 1
                # Only a rejected alert wastes time. An alert that found
                # something took time and bought something for it.
                wasted += judgement.minutes
            else:
                unclear += 1
        results.append(
            SystemResult(
                system=system,
                raised=len(alerts),
                confirmed=confirmed,
                rejected=rejected,
                unclear=unclear,
                unjudged=unjudged,
                minutes_spent=minutes,
                wasted_minutes=wasted,
                steward_weeks=steward_weeks,
            )
        )

    return ShadowResult(
        window_start=window_start,
        window_end=window_end,
        systems=tuple(results),
        outside_window=tuple(sorted(dropped.items())),
    )


__all__ = [
    "Blinding",
    "Judgement",
    "ShadowAlert",
    "ShadowResult",
    "SystemResult",
    "evaluate",
]
