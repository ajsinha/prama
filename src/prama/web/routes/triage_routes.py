"""One incident, in full: what failed, which rows, and since when.

The list screen answers "what is wrong". This one answers the three questions a
steward asks next, in the order they ask them: *show me the rows*, *when did
this start*, and *what does this control actually say*. Everything here is read
from the evidence ledger, so a page that shows nothing is showing that the
ledger holds nothing rather than that the data is clean.

The sample panel is the part that is easy to get wrong, and it is wrong in a way
that reads as helpful. Failing rows are **bounded** — a control that fails four
thousand rows keeps fifty — and they are on their own retention clock, years
shorter than the record that names them. So four situations have to be told
apart, and three of them look identical if you only check whether there are rows
to show:

* **Never collected.** The control asked for counts, not rows. Not a defect,
  and not a gap in retention.
* **No longer held.** They were collected and are gone: expired, or erased on
  request. Which of the two cannot be recovered from the store, so the screen
  says both rather than guessing one — the record still states truthfully how
  many rows failed, and can no longer show which.
* **Present, and a sample.** Fifty rows of four thousand. Rendering them without
  that ratio invites a reader to work the list and believe they are done, which
  is the specific failure this panel exists to prevent.
* **Present, and complete.** All of them, because there were few enough.

Masked columns are named. A sample with a column silently removed is a sample a
reader will draw conclusions from without knowing what is missing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import Request

from prama.core.errors import NotFoundError
from prama.ir.resolve import resolved
from prama.pql import parse_control
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes

#: How many past runs the history shows. Enough to see when a failure started
#: without turning the page into a log: the question is "since when", and the
#: answer stops being legible somewhere around a hundred rows.
HISTORY = 60


@dataclasses.dataclass(frozen=True, slots=True)
class Sample:
    """The failing rows, and everything true about them that is not the rows.

    A value object rather than a dictionary because every one of these fields
    is a qualification the template must not be able to forget: the reason
    there are no rows, the ratio the shown rows represent, and the columns that
    were withheld.
    """

    #: ``never_collected`` · ``no_longer_held`` · ``present``
    state: str
    rows: tuple[dict[str, Any], ...] = ()
    columns: tuple[str, ...] = ()
    masked: tuple[str, ...] = ()
    #: Rows kept, which is not rows that failed.
    kept: int = 0
    #: Rows that failed, from the record's own metrics.
    failing: int = 0
    digest: str = ""
    expires_at: str = ""

    @property
    def is_complete(self) -> bool:
        """Whether these rows are all the failing rows.

        ``kept >= failing``, and not "we kept fifty and fifty is the limit":
        a control that failed exactly fifty rows out of a limit of fifty is
        complete, and telling that reader their list is partial sends them
        looking for rows that do not exist.
        """
        return self.state == "present" and self.kept >= self.failing > 0

    @property
    def withheld(self) -> int:
        return max(0, self.failing - self.kept)

    def describe(self) -> str:
        if self.state == "never_collected":
            return (
                "This control records counts rather than rows, so no failing rows "
                "were ever kept. The counts are not an approximation of them."
            )
        if self.state == "no_longer_held":
            return (
                f"The {self.failing:,} failing rows are no longer held — they either "
                "reached the end of their retention or were erased on request. The "
                "record still states how many failed; it can no longer show which."
            )
        if self.is_complete:
            return f"All {self.kept:,} failing rows."
        return (
            f"{self.kept:,} of {self.failing:,} failing rows. The other "
            f"{self.withheld:,} were not kept, so working this list is not the "
            "same as working the failure."
        )


class TriageRoutes(UiRoutes):
    """The one-incident screen."""

    def register(self) -> None:
        self.page("/incidents/{control_id}", self.incident_detail, name="incident_detail")

    async def incident_detail(
        self, request: Request, control_id: str, caller: Caller, uow: Uow
    ) -> Any:
        history = await uow.evidence.for_control(control_id, limit=HISTORY)
        # Scoped after the fetch rather than trusted: the ledger indexes by
        # control, and an identifier out of a URL belongs to whoever typed it
        # until it has been checked against the caller's tenant.
        history = [r for r in history if r.tenant_id == caller.tenant_id]
        version = await uow.controls.by_control_id(caller.tenant_id, control_id)

        if not history and version is None:
            raise NotFoundError(
                f"there is no control {control_id!r}",
                remedy="Check the identifier against the incident list.",
                context={"control": control_id},
            )

        latest = history[0] if history else None
        return render(
            request,
            "incidents/detail.html",
            control_id=control_id,
            version=version,
            sentence=_sentence(version),
            latest=latest,
            history=history,
            # Named separately from the history so the template cannot show a
            # "since" that is really "the oldest run we still hold". A failure
            # whose start is off the end of the window is an unknown start.
            began=_began(history),
            history_is_truncated=len(history) >= HISTORY,
            sample=await _sample(uow, latest, caller.tenant_id),
        )


async def _sample(uow: Any, record: Any, tenant_id: str) -> Sample:
    failing = int(record.metrics.get("violating_rows", 0)) if record else 0
    if record is None or not record.samples_digest:
        return Sample(state="never_collected", failing=failing)

    stored = await uow.samples.get(record.samples_digest)
    if stored is None or stored.tenant_id != tenant_id:
        return Sample(state="no_longer_held", failing=failing, digest=record.samples_digest)

    rows = tuple(stored.rows_json or ())
    return Sample(
        state="present",
        rows=rows,
        # From the rows themselves, in the order the first row presents them.
        # A column list taken from the control would show columns the sample
        # does not carry, which reads as data that went missing.
        columns=tuple(rows[0].keys()) if rows else (),
        masked=tuple(stored.masked_json or ()),
        kept=stored.row_count,
        failing=failing,
        digest=record.samples_digest,
        expires_at=stored.expires_at or "",
    )


def _sentence(version: Any) -> str:
    """The control as the sentence a data owner reads.

    Taken from the lowered plan's description — the same structure the SQL is
    derived from — rather than from a stored description column. A second
    English renderer is how a screen ends up explaining one control and running
    another.

    A control that will not lower says so rather than showing nothing: a blank
    explanation beside a failing control is read as "this control is trivial",
    which is the opposite of true.
    """
    if version is None:
        return ""
    try:
        return str(resolved(parse_control(version.pql)).description)
    except Exception as exc:  # the stored text is authority; a failure is news
        return f"This control's stored text cannot be explained: {exc}"


def _began(history: list[Any]) -> str:
    """When the current run of failures started, or blank if it is not known.

    Walks back from the most recent record while the verdict is still not a
    pass. If it reaches the end of the window without finding a pass, the start
    is *older than what is held* — and blank is the honest answer, because a
    date that is really "the oldest run we still have" reads as the date the
    problem began.
    """
    if not history or history[0].verdict == "pass":
        return ""
    began = ""
    for record in history:
        if record.verdict == "pass":
            return began
        began = record.finished_at
    return ""


__all__ = ["HISTORY", "Sample", "TriageRoutes"]
