"""The break queue, persisted.

``prama.recon.workflow.BreakQueue`` already holds the semantics — ageing from
first sighting, clearing by absence, accepted breaks staying visible — and this
is that behaviour against a store rather than a dictionary. Deliberately the
same rules and not a second opinion about them: two implementations of "when
did this break start" is how a queue reports one age on a screen and another in
a certificate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select

from prama.core.errors import ConflictError, ValidationError
from prama.db.dao.base import Dao
from prama.db.models.recon import RecBreak

#: States in which a break is still somebody's problem.
OPEN = ("open", "assigned", "explained")

#: Everything that has not gone away. ``accepted`` belongs here: a
#: reconciliation reporting zero outstanding because the residue was accepted
#: is hiding exactly the thing the acceptance was supposed to make visible.
OUTSTANDING = (*OPEN, "accepted")


class BreakDao(Dao[RecBreak]):
    """Reconciliation breaks, tracked across the runs they appear in."""

    model = RecBreak

    async def observe(
        self,
        breaks: Sequence[Any],
        *,
        tenant_id: str,
        definition: str,
        when: str,
    ) -> tuple[int, int, int]:
        """Fold one run's breaks into the queue.

        Returns ``(new, seen_again, cleared)``. Counted and returned rather
        than logged, because "nothing changed" and "forty cleared and forty
        appeared" produce the same queue length, and a screen that reports only
        the length cannot tell them apart.

        Anything previously open and absent from this run has cleared. Inferred
        rather than announced: no reconciliation tells you a break has gone, it
        simply stops reporting it, and a queue that waits to be told never
        closes anything.
        """
        existing = {row.break_key: row for row in await self.for_definition(tenant_id, definition)}
        seen: set[str] = set()
        new = again = 0

        for found in breaks:
            key = str(found.key)
            seen.add(key)
            row = existing.get(key)
            if row is None:
                self.add(_row_for(found, tenant_id=tenant_id, definition=definition, when=when))
                new += 1
                continue
            # first_seen is not touched. A break re-detected for forty days is
            # forty days old; stamping each sighting with today reports every
            # break as new every morning and nothing ever ages.
            row.last_seen = when
            row.kind = found.kind.value
            row.left_value = _text(found.left)
            row.right_value = _text(found.right)
            row.difference = _text(found.difference)
            row.because = found.because
            row.normalisation_json = list(found.normalisation)
            row.aggregated = 1 if found.aggregated else 0
            if row.state == "cleared":
                # It came back. Re-opened rather than left cleared, and the
                # original first_seen survives — a break that recurs after
                # being closed is an old problem, not a new one.
                row.state = "open"
                row.cleared_at = None
            again += 1

        cleared = 0
        for key, row in existing.items():
            if key not in seen and row.state in OPEN:
                row.state = "cleared"
                row.cleared_at = when
                cleared += 1

        await self._session.flush()
        return new, again, cleared

    async def for_definition(
        self, tenant_id: str, definition: str, *, states: Sequence[str] | None = None
    ) -> list[RecBreak]:
        await self._session.flush()
        stmt = select(RecBreak).where(
            RecBreak.tenant_id == tenant_id, RecBreak.definition == definition
        )
        if states is not None:
            stmt = stmt.where(RecBreak.state.in_(states))
        return list((await self._session.execute(stmt.order_by(RecBreak.first_seen))).scalars())

    async def outstanding(self, tenant_id: str, definition: str) -> list[RecBreak]:
        return await self.for_definition(tenant_id, definition, states=OUTSTANDING)

    async def definitions(self, tenant_id: str) -> list[str]:
        """Reconciliations this tenant has breaks for, cleared ones included.

        Cleared included on purpose: a reconciliation that ran and cleared
        everything must still appear, or a clean result is indistinguishable
        from one that never ran.
        """
        await self._session.flush()
        stmt = (
            select(RecBreak.definition)
            .where(RecBreak.tenant_id == tenant_id)
            .distinct()
            .order_by(RecBreak.definition)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def in_tenant(self, break_id: str, tenant_id: str) -> RecBreak:
        """One break, provided it belongs to this tenant.

        Reported as absent rather than forbidden when it does not: which break
        identifiers exist in another tenant is not this caller's business
        either.
        """
        from prama.core.errors import NotFoundError

        row = await self.require(break_id)
        if row.tenant_id != tenant_id:
            raise NotFoundError(
                f"there is no break {break_id!r}",
                remedy="Check the identifier against the break list.",
                context={"break": break_id},
            )
        return row

    async def assign(
        self, break_id: str, tenant_id: str, *, owner: str, by: str, at: str
    ) -> RecBreak:
        """Hand a break to somebody, and record that it was handed over.

        The handover goes into the comment trail as well as into ``owner``.
        The current owner alone answers "whose is this"; only the trail answers
        "who gave it to them and when", which is the question asked about a
        break that sat with the wrong team for a month.
        """
        row = await self.in_tenant(break_id, tenant_id)
        if not owner.strip():
            raise ValidationError(
                "a break assigned to nobody is a break nobody is working",
                remedy="Name the person or the team taking it.",
                context={"break": break_id},
            )
        previous = row.owner
        row.owner = owner.strip()
        if row.state == "open":
            row.state = "assigned"
        row.comments_json = [
            *(row.comments_json or []),
            {
                "at": at,
                "by": by,
                "text": (
                    f"Reassigned from {previous} to {row.owner}"
                    if previous
                    else f"Assigned to {row.owner}"
                ),
            },
        ]
        await self._session.flush()
        return row

    async def explain(
        self, break_id: str, tenant_id: str, *, text: str, by: str, at: str
    ) -> RecBreak:
        """Record what somebody found out. Appends; never rewrites."""
        row = await self.in_tenant(break_id, tenant_id)
        if not text.strip():
            raise ValidationError(
                "an explanation with no text explains nothing",
                remedy="Say what was found, even if the finding is 'still looking'.",
                context={"break": break_id},
            )
        row.comments_json = [*(row.comments_json or []), {"at": at, "by": by, "text": text.strip()}]
        if row.state in ("open", "assigned"):
            row.state = "explained"
        await self._session.flush()
        return row

    async def accept(
        self, break_id: str, tenant_id: str, *, reason: str, by: str, at: str
    ) -> RecBreak:
        """Accept a break as a known reconciling item.

        The reason is required. An accepted break with no reason is
        indistinguishable from one somebody clicked away, and the difference is
        the whole value of the state.
        """
        row = await self.in_tenant(break_id, tenant_id)
        if not reason.strip():
            raise ValidationError(
                "a break cannot be accepted without a reason",
                remedy=(
                    "Say why this difference is expected. An acceptance with no "
                    "reason cannot be defended when somebody asks about it in a year."
                ),
                context={"break": break_id},
            )
        if row.state == "cleared":
            raise ConflictError(
                "this break has already cleared, so there is nothing to accept",
                remedy="Accepting a break that has gone would carry a difference nobody has.",
                context={"break": break_id},
            )
        row.state = "accepted"
        row.accepted_reason = reason.strip()
        row.comments_json = [
            *(row.comments_json or []),
            {"at": at, "by": by, "text": f"Accepted: {reason.strip()}"},
        ]
        await self._session.flush()
        return row

    async def delete(self, instance: RecBreak) -> None:
        """Refused. A queue that forgets reports the same number as a clean one."""
        raise ConflictError(
            "a break cannot be deleted",
            remedy=(
                "Breaks clear by absence when the reconciliation stops reporting "
                "them, and are accepted when they are expected to persist. "
                '"We had four hundred breaks and they cleared" and "we had four '
                'hundred breaks" must not be the same sentence.'
            ),
            context={"break": str(instance.id)},
        )


def _row_for(found: Any, *, tenant_id: str, definition: str, when: str) -> RecBreak:
    return RecBreak(
        tenant_id=tenant_id,
        definition=definition,
        break_key=str(found.key),
        kind=found.kind.value,
        left_value=_text(found.left),
        right_value=_text(found.right),
        difference=_text(found.difference),
        because=found.because,
        normalisation_json=list(found.normalisation),
        aggregated=1 if found.aggregated else 0,
        first_seen=when,
        last_seen=when,
    )


def _text(value: Any) -> str:
    """A side, as text.

    Empty for a missing side, which is not zero: "nothing on the right" and
    "zero on the right" are different breaks, and rendering the first as the
    second turns a missing record into a balanced one.
    """
    return "" if value is None else str(value)


__all__ = ["OPEN", "OUTSTANDING", "BreakDao"]
