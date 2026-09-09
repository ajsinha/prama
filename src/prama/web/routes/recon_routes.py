"""The break workbench: two systems side by side, and what people did about it.

The list screen says a reconciliation has four hundred breaks. This one is
where somebody works them, and its whole job is to stop the queue being worked
in the order that feels urgent.

**Sorted by kind, not by size.** A hundred-million-euro timing break is less
urgent than a thousand-euro genuine one — the first clears itself and the
second is somebody's missing trade. Sorting by magnitude puts the queue in
exactly the wrong order and looks authoritative doing it, so the ordering here
is: genuine differences, then everything else that needs a person, then the
configuration faults, then the ones that clear themselves.

**Configuration faults are separated out.** Sign, duplicate and FX breaks are
usually somebody's setup being wrong. Routing them to a data steward wastes the
steward's day and leaves the setup wrong, so they are grouped and labelled as
what they are.

**Accepted breaks stay on the screen.** A carried reconciling item that
disappears once accepted is how a reconciliation quietly stops reconciling.

**The normalisation trail is shown beside every break.** The first question
about any difference is whether it is real or a translation error, and a
workbench that shows the two amounts without showing what was done to them
invites the reader to answer it wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.clock import utc_now
from prama.core.errors import PramaError
from prama.db.dao.recon import OPEN, OUTSTANDING
from prama.recon.classify import BreakKind
from prama.recon.workflow import STALE_DAYS
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash, flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

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


class ReconRoutes(UiRoutes):
    """The workbench and its three dispositions."""

    def register(self) -> None:
        self.page("/reconciliation/{definition}", self.break_workbench, name="break_workbench")
        self.page(
            "/reconciliation/breaks/{break_id}/assign",
            self.break_assign,
            name="break_assign",
            methods=["POST"],
        )
        self.page(
            "/reconciliation/breaks/{break_id}/explain",
            self.break_explain,
            name="break_explain",
            methods=["POST"],
        )
        self.page(
            "/reconciliation/breaks/{break_id}/accept",
            self.break_accept,
            name="break_accept",
            methods=["POST"],
        )

    async def break_workbench(
        self,
        request: Request,
        definition: str,
        caller: Caller,
        uow: Uow,
        show: str = "outstanding",
    ) -> Any:
        """Every break for one reconciliation, in the order it should be worked."""
        states = None if show == "all" else OUTSTANDING
        found = await uow.breaks.for_definition(caller.tenant_id, definition, states=states)
        today = utc_now().date()
        rows = sorted(
            (_row(item, today) for item in found),
            key=lambda row: (row.urgency, -row.age_days, row.key),
        )
        cleared = await uow.breaks.for_definition(caller.tenant_id, definition, states=("cleared",))
        return render(
            request,
            "reconciliation/workbench.html",
            definition=definition,
            rows=rows,
            show=show,
            # Named rather than left to the reader to notice from an absence:
            # "forty cleared since yesterday" and "nothing changed" produce the
            # same queue length.
            cleared_count=len(cleared),
            # Grouped, because sending a configuration fault to a data steward
            # wastes their day and leaves the setup wrong.
            configuration=[row for row in rows if row.is_configuration],
            stale=[row for row in rows if row.is_stale],
            accepted=[row for row in rows if row.state == "accepted"],
        )

    async def break_assign(
        self,
        request: Request,
        break_id: str,
        caller: Caller,
        uow: Uow,
        definition: Annotated[str, Form()] = "",
        owner: Annotated[str, Form()] = "",
    ) -> Any:
        return await self._act(
            request,
            definition,
            lambda: uow.breaks.assign(
                break_id,
                caller.tenant_id,
                owner=owner,
                by=caller.principal_id or "",
                at=utc_now().isoformat(),
            ),
            "Assigned.",
        )

    async def break_explain(
        self,
        request: Request,
        break_id: str,
        caller: Caller,
        uow: Uow,
        definition: Annotated[str, Form()] = "",
        text: Annotated[str, Form()] = "",
    ) -> Any:
        return await self._act(
            request,
            definition,
            lambda: uow.breaks.explain(
                break_id,
                caller.tenant_id,
                text=text,
                by=caller.principal_id or "",
                at=utc_now().isoformat(),
            ),
            "Noted.",
        )

    async def break_accept(
        self,
        request: Request,
        break_id: str,
        caller: Caller,
        uow: Uow,
        definition: Annotated[str, Form()] = "",
        reason: Annotated[str, Form()] = "",
    ) -> Any:
        return await self._act(
            request,
            definition,
            lambda: uow.breaks.accept(
                break_id,
                caller.tenant_id,
                reason=reason,
                by=caller.principal_id or "",
                at=utc_now().isoformat(),
            ),
            "Accepted as a known reconciling item. It stays on this screen.",
        )

    async def _act(self, request: Request, definition: str, action: Any, said: str) -> Any:
        """One disposition, then back to the workbench.

        The three handlers differ only in which DAO call they make and what
        they say afterwards; writing the redirect and the failure handling
        three times is how two of them end up swallowing an error the third
        reports.
        """
        try:
            await action()
        except PramaError as exc:
            flash_error_and_log(request, "That could not be recorded", exc)
        else:
            flash(request, said)
        return redirect_to(request, "break_workbench", definition=definition)


def _row(item: Any, today: date) -> Row:
    kind = BreakKind(item.kind)
    return Row(
        id=str(item.id),
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
        age_days=_days_since(item.first_seen, today),
        clears_itself=kind.clears_itself,
        is_configuration=kind.is_configuration,
        urgency=URGENCY[kind],
    )


def _days_since(stamp: str, today: date) -> int:
    try:
        return max(0, (today - date.fromisoformat(stamp[:10])).days)
    except ValueError:
        # An unreadable stamp is zero rather than a crash, and zero rather than
        # a large number: an age this screen cannot compute must not become an
        # escalation nobody can explain.
        return 0


__all__ = ["URGENCY", "ReconRoutes", "Row"]
