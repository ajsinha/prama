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

from typing import Any

from fastapi import Request

from prama.incident import triage
from prama.incident.triage import HISTORY, Sample
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes


class TriageRoutes(UiRoutes):
    SUBJECT = "incident"
    """The one-incident screen. What it shows is assembled in `prama.incident.triage`,
    which ``/api/v1/incidents/{control_id}`` reads too."""

    def register(self) -> None:
        self.page("/incidents/{control_id}", self.incident_detail, name="incident_detail")

    async def incident_detail(
        self, request: Request, control_id: str, caller: Caller, uow: Uow
    ) -> Any:
        return render(
            request,
            "incidents/detail.html",
            **await triage.detail(uow, caller.tenant_id, control_id),
        )


__all__ = ["HISTORY", "Sample", "TriageRoutes"]
