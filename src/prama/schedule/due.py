"""What is due, and why the ones that are not are not.

The scheduler's job is a question with an obvious wrong answer. "Which controls
should run now?" invites a list; what an operator actually needs is a list
*and* an account of everything left out, because a control that silently stops
being scheduled is indistinguishable from one that is passing.

So :class:`Schedule` returns both, and every skip carries its reason. That is
the difference between a scheduler you can debug at 3am and one you have to
read the source of.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime
from typing import Any

from prama.core.calendars import CalendarRegistry
from prama.core.errors import ValidationError
from prama.core.log import get_logger
from prama.schedule.spec import parse
from prama.schedule.trigger import ManualTrigger, TriggerKind

_log = get_logger(__name__)

#: How far back a control with no evidence is treated as having last run.
#: ``None`` means "never", and a control that has never run is always due —
#: which is the answer that gets a newly accepted control checked tonight
#: rather than at its next natural boundary.
NEVER: datetime | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Due:
    """A control that should run now."""

    control_id: str
    dataset: str
    schedule: str
    last_run: datetime | None
    due_at: datetime | None

    @property
    def has_never_run(self) -> bool:
        return self.last_run is None


@dataclasses.dataclass(frozen=True, slots=True)
class Skipped:
    """A control that should not run now, and why.

    The reason is the point. "Not due until 06:30" and "its schedule does not
    parse" are the same absence from a run and completely different facts, and
    a scheduler that reported only the first list would let the second hide
    for months.
    """

    control_id: str
    dataset: str
    reason: str
    detail: str = ""

    @property
    def is_a_defect(self) -> bool:
        """Whether this skip is something somebody has to fix.

        ``not_due`` and ``manual`` are the scheduler working. ``unreadable`` is
        a control that will never run again and has no verdict to say so.
        """
        return self.reason == "unreadable"


@dataclasses.dataclass(frozen=True, slots=True)
class Plan:
    """What a run would do, before it does it."""

    due: tuple[Due, ...] = ()
    skipped: tuple[Skipped, ...] = ()

    @property
    def defects(self) -> tuple[Skipped, ...]:
        return tuple(item for item in self.skipped if item.is_a_defect)

    def describe(self) -> str:
        parts = [f"{len(self.due)} due"]
        if self.skipped:
            parts.append(f"{len(self.skipped)} not due")
        if self.defects:
            # Named separately and first among the problems: a control whose
            # schedule cannot be read will never run again, and nothing else
            # in the system will say so.
            parts.append(
                f"{len(self.defects)} with a schedule that cannot be read, "
                "which will never run until it is fixed"
            )
        return ", ".join(parts)


class Schedule:
    """Decides which of an estate's live controls are due.

    Takes the last-run times rather than reading them, so the decision is a
    pure function of (controls, history, now) and can be tested without a
    database or a clock.
    """

    def __init__(self, *, calendars: CalendarRegistry | None = None) -> None:
        self._calendars = calendars

    def plan(
        self,
        controls: list[Any],
        *,
        now: datetime,
        last_run: dict[str, datetime],
    ) -> Plan:
        due: list[Due] = []
        skipped: list[Skipped] = []

        for control in controls:
            control_id = str(control.control_id)
            schedule = control.schedule or ""
            try:
                trigger = parse(
                    schedule,
                    calendars=self._calendars,
                    offset_minutes=_stagger(control_id),
                )
            except ValidationError as exc:
                # Not silently defaulted to daily. A control whose schedule
                # cannot be read is a control somebody has to look at, and
                # quietly running it on a cadence nobody chose would hide that
                # for as long as it kept passing.
                _log.warning("control %s has an unreadable schedule: %s", control_id, exc)
                skipped.append(
                    Skipped(
                        control_id=control_id,
                        dataset=control.dataset,
                        reason="unreadable",
                        detail=str(exc),
                    )
                )
                continue

            if isinstance(trigger, ManualTrigger):
                skipped.append(
                    Skipped(control_id=control_id, dataset=control.dataset, reason="manual")
                )
                continue
            if trigger.kind is TriggerKind.ARRIVAL:
                # Arrival triggers fire on a feed landing, not on a clock. A
                # timer-driven pass must leave them alone rather than guess a
                # cadence for them.
                skipped.append(
                    Skipped(
                        control_id=control_id,
                        dataset=control.dataset,
                        reason="waits_for_arrival",
                    )
                )
                continue

            previous = last_run.get(control_id)
            if previous is None:
                # Never run. Due immediately, so a control accepted this
                # afternoon is checked tonight rather than at whatever boundary
                # its cadence would next reach.
                due.append(
                    Due(
                        control_id=control_id,
                        dataset=control.dataset,
                        schedule=schedule,
                        last_run=None,
                        due_at=None,
                    )
                )
                continue

            next_at = trigger.next_after(previous)
            if next_at is not None and next_at <= now:
                due.append(
                    Due(
                        control_id=control_id,
                        dataset=control.dataset,
                        schedule=schedule,
                        last_run=previous,
                        due_at=next_at,
                    )
                )
            else:
                skipped.append(
                    Skipped(
                        control_id=control_id,
                        dataset=control.dataset,
                        reason="not_due",
                        detail=f"next at {next_at.isoformat()}" if next_at else "",
                    )
                )

        return Plan(due=tuple(due), skipped=tuple(skipped))


def _stagger(control_id: str) -> int:
    """A stable per-control offset within the hour.

    Derived from the identifier, so it is the same on every node and across
    restarts — a random offset would re-stagger the estate on every deploy and
    make load unpredictable. Without it, every hourly control in the estate
    fires at the top of the hour and lands on the source together.
    """
    digest = hashlib.sha256(control_id.encode("utf-8")).digest()
    return digest[0] % 60
