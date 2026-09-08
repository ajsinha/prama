"""Breaks as work, and the certificate that closes a period.

`FR-REC-008` and `FR-REC-011`. A break population is not a report; it is a
queue. Somebody owns each item, it ages, it gets commentary, and at period end
somebody signs a statement about what was still outstanding — which is the
artefact an auditor asks for and the reason reconciliation software gets bought
rather than written in a spreadsheet.

**Ageing is measured from when the break first appeared, not from today's
run.** A break that has been open for forty days has been re-detected forty
times, and a system that stamps each detection with today's date reports it as
new every morning. Getting this wrong is what makes a reconciliation queue
impossible to prioritise: everything is one day old.

**A break that stops appearing is closed as cleared, not deleted.** The
distinction matters at period end: "we had four hundred breaks and they
cleared" and "we had four hundred breaks" are the same sentence in a system
that forgets, and only one of them is reassuring.

**The certificate states what was outstanding, not that everything was fine.**
A certificate that can only be issued clean is a certificate nobody issues; one
that names the residue and who accepted it is a document somebody signs at
month end and an auditor can read a year later.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from prama.core import pjson
from prama.recon.classify import Break, BreakKind

#: A break older than this is escalated whatever its size. Age is its own kind
#: of severity: a small break nobody has explained in a month is a process that
#: is not working, and the amount is beside the point.
STALE_DAYS = 30


class State(enum.Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    EXPLAINED = "explained"
    #: Stopped appearing. Not deleted — "we had four hundred breaks and they
    #: cleared" and "we had four hundred breaks" are the same sentence in a
    #: system that forgets.
    CLEARED = "cleared"
    #: Explained, accepted, and expected to persist. A carried break is the
    #: honest outcome for a known reconciling item, and hiding it is how a
    #: reconciliation quietly stops reconciling.
    ACCEPTED = "accepted"

    @property
    def is_open(self) -> bool:
        return self in (State.OPEN, State.ASSIGNED, State.EXPLAINED)


@dataclasses.dataclass(frozen=True, slots=True)
class Comment:
    at: str
    by: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "by": self.by, "text": self.text}


@dataclasses.dataclass(frozen=True, slots=True)
class Item:
    """One break, tracked across the runs it appears in."""

    key: str
    kind: BreakKind
    difference: Decimal
    #: The run that first produced it. Ageing runs from here, not from the
    #: latest sighting — a break re-detected for forty days is forty days old,
    #: and a system that stamps each detection with today reports it as new
    #: every morning.
    first_seen: date
    last_seen: date
    state: State = State.OPEN
    owner: str = ""
    comments: tuple[Comment, ...] = ()
    accepted_reason: str = ""

    def age(self, as_of: date) -> int:
        return (as_of - self.first_seen).days

    def is_stale(self, as_of: date, *, threshold: int = STALE_DAYS) -> bool:
        return self.state.is_open and self.age(as_of) >= threshold

    def seen_again(self, when: date, difference: Decimal) -> Item:
        """Re-detected. The first-seen date does not move, which is the point."""
        return dataclasses.replace(
            self,
            last_seen=when,
            difference=difference,
            state=State.OPEN if self.state is State.CLEARED else self.state,
        )

    def assigned_to(self, owner: str, at: str) -> Item:
        return dataclasses.replace(
            self,
            owner=owner,
            state=State.ASSIGNED,
            comments=(*self.comments, Comment(at=at, by="system", text=f"assigned to {owner}")),
        )

    def explained(self, by: str, at: str, text: str) -> Item:
        return dataclasses.replace(
            self,
            state=State.EXPLAINED,
            comments=(*self.comments, Comment(at=at, by=by, text=text)),
        )

    def accepted(self, by: str, at: str, reason: str) -> Item:
        if not reason.strip():
            raise ValueError(
                "accepting a break requires a reason. A carried break with no "
                "explanation is indistinguishable from one nobody looked at, and the "
                "certificate has to tell them apart"
            )
        return dataclasses.replace(
            self,
            state=State.ACCEPTED,
            accepted_reason=reason,
            comments=(*self.comments, Comment(at=at, by=by, text=reason)),
        )

    def cleared(self, when: date) -> Item:
        return dataclasses.replace(self, state=State.CLEARED, last_seen=when)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind.value,
            "difference": str(self.difference),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "state": self.state.value,
            "owner": self.owner,
            "accepted_reason": self.accepted_reason,
            "comments": [comment.to_dict() for comment in self.comments],
        }


class BreakQueue:
    """Breaks tracked across runs, so ageing means something."""

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}

    def observe(self, breaks: Sequence[Break], *, when: date) -> None:
        """Fold one run's breaks into the queue.

        Anything previously open and absent from this run has cleared. That is
        inferred rather than announced, because no reconciliation tells you a
        break has gone — it simply stops reporting it, and a queue that waits
        to be told never closes anything.
        """
        seen = set()
        for found in breaks:
            seen.add(found.key)
            existing = self._items.get(found.key)
            if existing is None:
                self._items[found.key] = Item(
                    key=found.key,
                    kind=found.kind,
                    difference=found.difference,
                    first_seen=when,
                    last_seen=when,
                )
            else:
                self._items[found.key] = existing.seen_again(when, found.difference)

        for key, item in self._items.items():
            if key not in seen and item.state.is_open:
                self._items[key] = item.cleared(when)

    def get(self, key: str) -> Item | None:
        return self._items.get(key)

    def update(self, item: Item) -> None:
        self._items[item.key] = item

    def open_items(self) -> tuple[Item, ...]:
        return tuple(item for item in self._items.values() if item.state.is_open)

    def outstanding(self) -> tuple[Item, ...]:
        """Open plus accepted: everything that has not gone away.

        Accepted items belong here. A reconciliation that reports zero
        outstanding because the residue was accepted is reporting the thing the
        acceptance was supposed to make visible.
        """
        return tuple(
            item
            for item in self._items.values()
            if item.state.is_open or item.state is State.ACCEPTED
        )

    def stale(self, as_of: date, *, threshold: int = STALE_DAYS) -> tuple[Item, ...]:
        """Open breaks old enough to be a process problem.

        Age is its own severity. A small break nobody has explained in a month
        says the process is not working, and the amount is beside the point.
        """
        return tuple(
            sorted(
                (
                    item
                    for item in self._items.values()
                    if item.is_stale(as_of, threshold=threshold)
                ),
                key=lambda item: item.first_seen,
            )
        )

    def by_owner(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.open_items():
            counts[item.owner or "unassigned"] = counts.get(item.owner or "unassigned", 0) + 1
        return counts

    def ageing(self, as_of: date) -> dict[str, int]:
        """The buckets a reconciliation manager actually reads."""
        buckets = {"0-7": 0, "8-30": 0, "31-90": 0, "90+": 0}
        for item in self.open_items():
            age = item.age(as_of)
            if age <= 7:
                buckets["0-7"] += 1
            elif age <= 30:
                buckets["8-30"] += 1
            elif age <= 90:
                buckets["31-90"] += 1
            else:
                buckets["90+"] += 1
        return buckets

    def __len__(self) -> int:
        return len(self._items)


@dataclasses.dataclass(frozen=True, slots=True)
class Certificate:
    """A signed statement of what was outstanding when a period closed.

    Not a statement that everything was fine. A certificate that can only be
    issued clean is a certificate nobody issues; one that names the residue and
    who accepted it is a document somebody signs at month end and an auditor
    can read a year later.
    """

    reconciliation: str
    period_end: date
    signed_by: str
    signed_at: str
    matched_rate: float
    outstanding: tuple[Item, ...]
    #: Total difference still outstanding, and separately the part somebody has
    #: explicitly accepted. A single number would let an accepted residue and
    #: an unexplained one look identical.
    outstanding_total: Decimal
    accepted_total: Decimal
    unexplained_total: Decimal
    #: The break population's own summary, so the certificate does not restate
    #: it and drift.
    population: str = ""

    @property
    def is_clean(self) -> bool:
        return not self.outstanding

    @property
    def content_hash(self) -> str:
        """What a signature is over.

        Excludes the signature itself and includes everything else, so a
        certificate whose numbers were edited after signing does not verify.
        """
        return hashlib.sha256(
            pjson.canonical(
                {
                    "reconciliation": self.reconciliation,
                    "period_end": self.period_end.isoformat(),
                    "matched_rate": round(self.matched_rate, 6),
                    "outstanding": [item.to_dict() for item in self.outstanding],
                    "outstanding_total": str(self.outstanding_total),
                    "accepted_total": str(self.accepted_total),
                    "unexplained_total": str(self.unexplained_total),
                }
            )
        ).hexdigest()

    def render(self) -> str:
        lines = [
            f"# Reconciliation certificate — {self.reconciliation}",
            "",
            f"**Period ending** {self.period_end.isoformat()}",
            f"**Signed by** {self.signed_by} at {self.signed_at}",
            f"**Match rate** {self.matched_rate:.2%}",
            "",
        ]
        if self.is_clean:
            lines.append("Nothing was outstanding at period end.")
        else:
            lines.extend(
                [
                    f"**{len(self.outstanding)} items outstanding**, totalling "
                    f"{self.outstanding_total:,.2f}, of which "
                    f"{self.accepted_total:,.2f} has been explicitly accepted and "
                    f"{self.unexplained_total:,.2f} has not.",
                    "",
                ]
            )
            for item in self.outstanding:
                explanation = (
                    f" — accepted: {item.accepted_reason}"
                    if item.state.value == "accepted"
                    else f" — {item.state.value}, {item.age(self.period_end)} days old"
                )
                lines.append(
                    f"- {item.key}: {item.difference:,.2f} ({item.kind.value}){explanation}"
                )
        if self.population:
            lines.extend(["", f"**Population.** {self.population}"])
        lines.extend(["", f"**Certificate hash** `{self.content_hash[:32]}`"])
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reconciliation": self.reconciliation,
            "period_end": self.period_end.isoformat(),
            "signed_by": self.signed_by,
            "signed_at": self.signed_at,
            "matched_rate": round(self.matched_rate, 6),
            "clean": self.is_clean,
            "outstanding": [item.to_dict() for item in self.outstanding],
            "outstanding_total": str(self.outstanding_total),
            "accepted_total": str(self.accepted_total),
            "unexplained_total": str(self.unexplained_total),
            "content_hash": self.content_hash,
            "markdown": self.render(),
        }


def certify(
    name: str,
    queue: BreakQueue,
    *,
    period_end: date,
    signed_by: str,
    signed_at: str,
    matched_rate: float,
    population: str = "",
) -> Certificate:
    """Close a period over whatever is actually outstanding."""
    outstanding = queue.outstanding()
    accepted = sum(
        (item.difference for item in outstanding if item.state is State.ACCEPTED),
        Decimal(0),
    )
    total = sum((item.difference for item in outstanding), Decimal(0))
    return Certificate(
        reconciliation=name,
        period_end=period_end,
        signed_by=signed_by,
        signed_at=signed_at,
        matched_rate=matched_rate,
        outstanding=tuple(sorted(outstanding, key=lambda item: (-abs(item.difference), item.key))),
        outstanding_total=total,
        accepted_total=accepted,
        unexplained_total=total - accepted,
        population=population,
    )
