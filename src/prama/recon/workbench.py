"""A break as the workbench shows it, and the order a queue should be worked in.

Shared by the console's break workbench and the API, so the two cannot rank a
queue differently. Before this module existed the ordering and every derived
field lived inside the console route, and an API serving the same queue would
have had to restate them — which is how two screens come to disagree about
which break is most urgent.

**Sorted by kind, not by size.** A hundred-million-euro timing break is less
urgent than a thousand-euro genuine one — the first clears itself and the
second is somebody's missing trade. Sorting by magnitude puts the queue in
exactly the wrong order and looks authoritative doing it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from datetime import date
from typing import Any

from prama.db.dao.recon import OPEN
from prama.recon.classify import BreakKind
from prama.recon.workflow import STALE_DAYS

#: The order a queue should be worked in. Not by size — a huge timing break is
#: less urgent than a small genuine one, and sorting by magnitude puts the
#: queue in exactly the wrong order while looking authoritative.
URGENCY = {
    BreakKind.GENUINE: 0,
    BreakKind.MISSING: 1,
    BreakKind.EXTRA: 1,
    BreakKind.ROUNDING: 2,
    BreakKind.SIGN: 3,
    BreakKind.DUPLICATE: 3,
    BreakKind.FX: 3,
    BreakKind.TIMING: 4,
}


@dataclasses.dataclass(frozen=True, slots=True)
class Row:
    """One break as the workbench shows it.

    A value object rather than the ORM row, because every derived field here —
    the age, the urgency, whether the setup is the fault — is a judgement the
    template must not be able to make differently from the one the sorting
    made.
    """

    id: str
    definition: str
    key: str
    kind: str
    label: str
    left: str
    right: str
    difference: str
    because: str
    normalisation: tuple[str, ...]
    aggregated: bool
    first_seen: str
    last_seen: str
    state: str
    owner: str
    accepted_reason: str
    comments: tuple[dict[str, Any], ...]
    age_days: int
    clears_itself: bool
    is_configuration: bool
    urgency: int

    @property
    def is_stale(self) -> bool:
        """Old enough that the age is the finding.

        A small break nobody has explained in a month says the process is not
        working, and the amount is beside the point.
        """
        return self.state in OPEN and self.age_days >= STALE_DAYS

    @property
    def is_one_sided(self) -> bool:
        """Whether one side has nothing at all.

        Kept distinct from a zero. "Nothing on the right" and "zero on the
        right" are different breaks, and rendering the first as the second
        turns a missing record into a balanced one.
        """
        return not self.left or not self.right

    def to_dict(self) -> dict[str, Any]:
        """The row, with its derived flags, for a program rather than a template."""
        return {
            **{f.name: getattr(self, f.name) for f in dataclasses.fields(self)},
            "normalisation": list(self.normalisation),
            "comments": list(self.comments),
            "is_stale": self.is_stale,
            "is_one_sided": self.is_one_sided,
        }


def row_of(item: Any, today: date) -> Row:
    """A stored break as a workbench row."""
    kind = BreakKind(item.kind)
    return Row(
        id=str(item.id),
        definition=str(item.definition),
        key=item.break_key,
        kind=item.kind,
        label=kind.label,
        left=item.left_value,
        right=item.right_value,
        difference=item.difference,
        because=item.because,
        normalisation=tuple(item.normalisation_json or ()),
        aggregated=bool(item.aggregated),
        first_seen=item.first_seen,
        last_seen=item.last_seen,
        state=item.state,
        owner=item.owner,
        accepted_reason=item.accepted_reason,
        comments=tuple(item.comments_json or ()),
        # From first_seen, always. A break re-detected for forty days is forty
        # days old, and ageing from the latest sighting reports every break as
        # new every morning.
        age_days=days_since(item.first_seen, today),
        clears_itself=kind.clears_itself,
        is_configuration=kind.is_configuration,
        urgency=URGENCY[kind],
    )


def in_working_order(items: Iterable[Any], today: date) -> list[Row]:
    """Rows in the order they should be worked: kind first, then age, then key."""
    return sorted(
        (row_of(item, today) for item in items),
        key=lambda row: (row.urgency, -row.age_days, row.key),
    )


def days_since(stamp: str, today: date) -> int:
    try:
        return max(0, (today - date.fromisoformat(stamp[:10])).days)
    except ValueError:
        # An unreadable stamp is zero rather than a crash, and zero rather than
        # a large number: an age this screen cannot compute must not become an
        # escalation nobody can explain.
        return 0


__all__ = ["URGENCY", "Row", "days_since", "in_working_order", "row_of"]
