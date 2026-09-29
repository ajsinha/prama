"""Incidents, reconciliation and scorecards: the screens backed by runs.

Every one of these reads the evidence ledger, and every one of them keeps the
distinction the ledger makes possible: "we looked and found nothing" and
"nothing has run" are different answers to the same question and must never
render the same way. An empty incident list shown as a clean incident list is
the single most dangerous screen a data quality product can ship.

That distinction is now a fact about the data rather than a placeholder: the
ledger either holds records for this tenant or it does not, and there is a
third state — a run that started and never reported — which is neither, and
which these screens surface rather than absorb.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from prama.evidence.service import observation
from prama.incident import triage
from prama.score import scorecard
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes


class OperationsRoutes(UiRoutes):
    """The run-backed screens."""

    def register(self) -> None:
        # Each screen names its own scope. There is no class-level `SUBJECT`
        # because these four serve four different subjects, and without one they
        # all fell back to `UiRoutes.DEFAULT_READ` — `declaration:read`. So a
        # caller granted the scope for browsing the dataset catalogue could also
        # read every incident, break, scorecard and evidence record.
        #
        # `TriageRoutes` sets `SUBJECT = "incident"` and got this right, which is
        # how the omission surfaced: the incident *detail* route required
        # `incident:read` while the incident *list* did not. QA round 4, UI-009.
        self.page("/incidents", self.incident_list, name="incident_list", scope="incident:read")
        self.page(
            "/reconciliation",
            self.reconciliation_list,
            name="reconciliation_list",
            scope="break:read",
        )
        self.page("/scorecards", self.scorecard_list, name="scorecard_list", scope="report:read")
        self.page("/evidence", self.evidence_chain, name="evidence_chain", scope="evidence:read")

    async def _observation(self, caller: Caller, uow: Uow) -> dict[str, Any]:
        """What, if anything, has been observed — see `prama.evidence.service.observation`."""
        return await observation(uow, caller.tenant_id)

    async def incident_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """What is currently wrong, one row per control rather than per run.

        A control failing every hour for a week is one problem, and listing it
        168 times is how a triage queue becomes something nobody opens.
        """
        incidents, passing = await triage.current(uow, caller.tenant_id)
        return render(
            request,
            "incidents/list.html",
            observation=await self._observation(caller, uow),
            incidents=incidents,
            passing=passing,
        )

    async def reconciliation_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """Reconciliation results, read from the same ledger as everything else."""
        latest = await uow.evidence.latest_per_control(caller.tenant_id)
        reconciliations = [
            {
                "control_id": key,
                "dataset": record.dataset,
                "verdict": record.verdict,
                "match_rate": _match_rate(record.metrics),
                "breaks": int(record.metrics.get("violating_rows", 0)),
                "scanned": int(record.metrics.get("scanned_rows", 0)),
                "finished_at": record.finished_at,
            }
            for key, record in latest.items()
            if "match_rate" in record.metrics or "matched_rows" in record.metrics
        ]
        reconciliations.sort(
            key=lambda item: item["match_rate"] if item["match_rate"] is not None else -1.0
        )
        return render(
            request,
            "reconciliation/list.html",
            observation=await self._observation(caller, uow),
            reconciliations=reconciliations,
            # Break queues are a different thing from reconciliation verdicts
            # and are listed as one. A verdict says whether the two sides
            # agreed; a queue says what people are doing about the ones that
            # did not, and merging them would let an empty queue read as a
            # clean reconciliation.
            queues=await uow.breaks.definitions(caller.tenant_id),
        )

    async def scorecard_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """A score per dataset, decomposed.

        Built from the *latest* record per control, never from every record: a
        score over the whole ledger weights an hourly control sixty times as
        heavily as a daily one, which measures the schedule rather than the
        data.
        """
        cards = await scorecard.scorecards(uow, caller.tenant_id)
        return render(
            request,
            "scorecards/list.html",
            observation=await self._observation(caller, uow),
            scores=cards["scores"],
            decomposed=cards["decomposed"],
            undecomposed=cards["undecomposed"],
        )

    async def evidence_chain(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """The ledger itself, and whether it still verifies.

        On a screen rather than only in a CLI, because "is our audit trail
        intact?" is a question an owner should be able to answer without
        asking an engineer — and because a verification nobody performs is a
        verification that does not exist.
        """
        verification = await uow.evidence.verify(caller.tenant_id)
        return render(
            request,
            "evidence/chain.html",
            observation=await self._observation(caller, uow),
            verification=verification,
            recent=await uow.evidence_runs.recent(caller.tenant_id, limit=20),
            records=(await uow.evidence.chain(caller.tenant_id))[-50:],
        )


def _match_rate(metrics: dict[str, float]) -> float | None:
    """The headline reconciliation number, or nothing.

    ``None`` rather than 0.0 when it cannot be computed: a reconciliation with
    no rows scored as 0% match reads as a total failure, and it is not a
    measurement at all.
    """
    if "match_rate" in metrics:
        return float(metrics["match_rate"])
    scanned = float(metrics.get("scanned_rows", 0))
    if not scanned:
        return None
    return float(metrics.get("matched_rows", 0)) / scanned
