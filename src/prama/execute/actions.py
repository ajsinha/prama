"""What happens when a control fails.

An alert is the weakest thing a data quality platform can do, and for most of
the industry it is the only thing. It puts the finding in a queue behind
yesterday's findings, and the bad data carries on downstream while somebody
decides whether to read it. The controls that matter are the ones that *act*.

Four actions, and the differences between them are the whole point:

* **Alert** — tell somebody. The default, and honest about being the weakest.
* **Tag** — mark the data as suspect and let it through. For a consumer that
  can decide for itself, and for the case where stopping is more expensive than
  proceeding carefully.
* **Quarantine** — move the offending rows aside and let the rest through. The
  answer when nine hundred rows of a million are wrong and the batch is due.
* **Block** — stop the pipeline. The strongest, and the one that needs the most
  care, because a control that blocks and is wrong has caused an outage.

Two rules govern all of them.

**An action is declared, never inferred.** Severity does not imply blocking. A
critical control on a dataset nobody reads until Friday should not stop the
overnight batch, and only a person knows that. The language carries `ON FAIL`
for exactly this reason.

**Every action is reversible and recorded.** A block can be overridden, a
quarantine can be released, a tag can be cleared — and each of those is an
event with a name attached. An action nobody can undo is one people route
around, and a platform people route around is one that stops being consulted.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from datetime import datetime
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.ir.model import Verdict


class Action(enum.Enum):
    ALERT = "alert"
    TAG = "tag"
    QUARANTINE = "quarantine"
    BLOCK = "block"

    @property
    def stops_the_pipeline(self) -> bool:
        return self is Action.BLOCK

    @property
    def touches_the_data(self) -> bool:
        """Whether taking this action changes what a consumer sees.

        Alerting does not; the other three do, which is why each of them needs
        an override path and alerting does not.
        """
        return self is not Action.ALERT

    @property
    def explanation(self) -> str:
        return {
            Action.ALERT: "somebody is told; the data carries on unchanged",
            Action.TAG: "the data is marked as suspect and allowed through",
            Action.QUARANTINE: "the offending rows are set aside and the rest continues",
            Action.BLOCK: "the pipeline stops until somebody decides",
        }[self]


class Disposition(enum.Enum):
    """What became of an action once a person got to it."""

    OPEN = "open"
    OVERRIDDEN = "overridden"
    RELEASED = "released"
    RESOLVED = "resolved"
    EXPIRED = "expired"

    @property
    def is_closed(self) -> bool:
        return self is not Disposition.OPEN


@dataclasses.dataclass(frozen=True, slots=True)
class Override:
    """Somebody deciding to proceed anyway.

    Named, reasoned and timestamped. An override without a name is an outage
    nobody owns; an override without a reason is one nobody can learn from.
    """

    by: str
    reason: str
    at: datetime
    #: How long the override holds. An override with no expiry is a control
    #: that has been quietly switched off, and six months later nobody
    #: remembers it was ever on.
    until: datetime | None = None

    def is_effective_at(self, moment: datetime) -> bool:
        return self.until is None or moment < self.until

    def to_dict(self) -> dict[str, Any]:
        return {
            "by": self.by,
            "reason": self.reason,
            "at": self.at.isoformat(),
            "until": self.until.isoformat() if self.until else None,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Consequence:
    """An action taken, and what became of it."""

    action: Action
    plan_id: str
    dataset: str
    verdict: str
    #: Rows set aside, for a quarantine. A digest, not the rows: the rows are
    #: in the quarantine, and copying them here would double the exposure of
    #: exactly the data somebody decided to isolate.
    quarantine_ref: str = ""
    quarantined_rows: int = 0
    tag: str = ""
    reason: str = ""
    raised_at: datetime | None = None
    disposition: Disposition = Disposition.OPEN
    override: Override | None = None

    @property
    def is_blocking(self) -> bool:
        """Whether the pipeline is stopped *right now*."""
        return self.action.stops_the_pipeline and self.disposition is Disposition.OPEN

    def render(self) -> str:
        head = f"{self.dataset}: {self.verdict} → {self.action.value}"
        detail = f" ({self.action.explanation})"
        if self.action is Action.QUARANTINE and self.quarantined_rows:
            detail = f" — {self.quarantined_rows:,} row(s) set aside"
        lines = [head + detail]
        if self.reason:
            lines.append(f"  because: {self.reason}")
        if self.override is not None:
            until = (
                f" until {self.override.until.isoformat(timespec='minutes')}"
                if self.override.until
                else " with no expiry"
            )
            lines.append(f"  overridden by {self.override.by}{until}: {self.override.reason}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "plan_id": self.plan_id,
            "dataset": self.dataset,
            "verdict": self.verdict,
            "blocking": self.is_blocking,
            "quarantine_ref": self.quarantine_ref,
            "quarantined_rows": self.quarantined_rows,
            "tag": self.tag,
            "reason": self.reason,
            "raised_at": self.raised_at.isoformat() if self.raised_at else None,
            "disposition": self.disposition.value,
            "override": self.override.to_dict() if self.override else None,
        }


class Quarantine:
    """Where set-aside rows go.

    Kept apart from the evidence ledger on purpose: quarantined rows are the
    data, under whatever retention and residency the data has, while an
    evidence record is a fact about it kept for years. Storing them together
    would force one policy onto both.
    """

    def __init__(self) -> None:
        self._batches: dict[str, list[dict[str, Any]]] = {}
        self._released: set[str] = set()

    def put(self, reference: str, rows: list[dict[str, Any]]) -> str:
        self._batches[reference] = [dict(r) for r in rows]
        return reference

    def get(self, reference: str) -> list[dict[str, Any]]:
        return list(self._batches.get(reference, ()))

    def release(self, reference: str) -> list[dict[str, Any]]:
        """Let the rows back through, and remember that somebody did.

        Released rather than deleted: the rows rejoin the flow and the fact
        that they were once quarantined stays visible, because "this was let
        through on purpose" is exactly what an investigation needs six months
        later.
        """
        self._released.add(reference)
        return self.get(reference)

    def was_released(self, reference: str) -> bool:
        return reference in self._released

    def __len__(self) -> int:
        return len(self._batches)


class Enforcer:
    """Turns a verdict into a consequence, according to what was declared."""

    def __init__(self, quarantine: Quarantine | None = None, *, clock: Clock | None = None) -> None:
        self._quarantine = Quarantine() if quarantine is None else quarantine
        self._clock = clock or SystemClock()
        self._open: dict[str, Consequence] = {}

    @property
    def quarantine(self) -> Quarantine:
        return self._quarantine

    def enforce(
        self,
        *,
        plan_id: str,
        dataset: str,
        verdict: Verdict,
        action: Action,
        rows: list[dict[str, Any]] | None = None,
        reason: str = "",
        tag: str = "",
    ) -> Consequence | None:
        """Act on a verdict, or return None when there is nothing to do.

        Only a failure acts. An *indeterminate* verdict deliberately does not:
        it means the control demonstrated nothing, and blocking a pipeline
        because a scope was empty would be acting on the absence of evidence
        rather than on evidence.
        """
        if verdict is not Verdict.FAIL:
            return None
        now = self._clock.now()
        reference = ""
        count = 0
        if action is Action.QUARANTINE and rows:
            reference = f"quarantine:{plan_id[-16:]}:{int(now.timestamp())}"
            self._quarantine.put(reference, rows)
            count = len(rows)
        consequence = Consequence(
            action=action,
            plan_id=plan_id,
            dataset=dataset,
            verdict=verdict.value,
            quarantine_ref=reference,
            quarantined_rows=count,
            tag=tag or ("suspect" if action is Action.TAG else ""),
            reason=reason,
            raised_at=now,
        )
        if action.touches_the_data:
            self._open[plan_id] = consequence
        return consequence

    # -- getting out of it -------------------------------------------------

    def override(
        self, plan_id: str, *, by: str, reason: str, until: datetime | None = None
    ) -> Consequence | None:
        """Proceed anyway. Named, reasoned, and with an expiry if given.

        An action nobody can undo is one people route around, and a platform
        people route around stops being consulted.
        """
        consequence = self._open.get(plan_id)
        if consequence is None:
            return None
        updated = dataclasses.replace(
            consequence,
            disposition=Disposition.OVERRIDDEN,
            override=Override(by=by, reason=reason, at=self._clock.now(), until=until),
        )
        self._open[plan_id] = updated
        return updated

    def release(self, plan_id: str) -> Consequence | None:
        """Let a quarantined batch back through."""
        consequence = self._open.get(plan_id)
        if consequence is None or consequence.action is not Action.QUARANTINE:
            return None
        self._quarantine.release(consequence.quarantine_ref)
        updated = dataclasses.replace(consequence, disposition=Disposition.RELEASED)
        self._open[plan_id] = updated
        return updated

    def resolve(self, plan_id: str) -> Consequence | None:
        """The underlying problem was fixed."""
        consequence = self._open.get(plan_id)
        if consequence is None:
            return None
        updated = dataclasses.replace(consequence, disposition=Disposition.RESOLVED)
        self._open[plan_id] = updated
        return updated

    # -- what is in force --------------------------------------------------

    def blocking(self) -> list[Consequence]:
        """Everything currently stopping a pipeline.

        The list somebody looks at when a batch has not run. Expired overrides
        count as blocking again, which is the point of giving them an expiry.
        """
        now = self._clock.now()
        return [c for c in self._open.values() if self._in_force(c, now)]

    def is_blocked(self, dataset: str) -> bool:
        return any(c.dataset == dataset for c in self.blocking())

    def _in_force(self, consequence: Consequence, now: datetime) -> bool:
        if not consequence.action.stops_the_pipeline:
            return False
        if consequence.disposition is Disposition.OPEN:
            return True
        if consequence.disposition is Disposition.OVERRIDDEN and consequence.override:
            # An override that has run out restores the block rather than
            # lapsing into permission. An override with no expiry is a control
            # quietly switched off, and this is where that shows.
            return not consequence.override.is_effective_at(now)
        return False

    def report(self) -> dict[str, Any]:
        blocking = self.blocking()
        overridden = [c for c in self._open.values() if c.disposition is Disposition.OVERRIDDEN]
        return {
            "blocking": [c.to_dict() for c in blocking],
            "overridden": [c.to_dict() for c in overridden],
            "quarantined_batches": len(self._quarantine),
            "summary": (
                f"{len(blocking)} pipeline(s) stopped, {len(overridden)} action(s) "
                f"overridden, {len(self._quarantine)} quarantined batch(es)."
            ),
        }
