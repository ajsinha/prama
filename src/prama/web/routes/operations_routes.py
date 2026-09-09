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

from prama.pql.ast import Dimension
from prama.score import Measurement, Method, score
from prama.semantic.values import Criticality
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes

#: Verdicts that are not a pass. ``error`` and ``skipped`` belong here with
#: ``fail``: a control that could not run has no verdict, and a list of
#: problems that quietly omitted it would report the controls that did run as
#: though they were all of them.
UNRESOLVED = ("fail", "error", "skipped", "indeterminate")

#: Where a record with no dimension of its own goes — one written before
#: evidence format 1.1. Deliberately a real dimension rather than a synthetic
#: "other": the score still has to add up, and the screen says how many landed
#: here rather than letting the bucket pass for a finding.
UNCLASSIFIED = "conformity"


class OperationsRoutes(UiRoutes):
    """The run-backed screens."""

    def register(self) -> None:
        self.page("/incidents", self.incident_list, name="incident_list")
        self.page("/reconciliation", self.reconciliation_list, name="reconciliation_list")
        self.page("/scorecards", self.scorecard_list, name="scorecard_list")
        self.page("/evidence", self.evidence_chain, name="evidence_chain")

    async def _observation(self, caller: Caller, uow: Uow) -> dict[str, Any]:
        """What, if anything, has been observed for this tenant.

        Three states, not two. ``no_runs`` means nothing has been examined;
        ``observed`` means it has; and a run that started and never reported is
        reported alongside either, because its controls have no verdict and
        every number on the page is silently missing them.
        """
        records = await uow.evidence.count_for(caller.tenant_id)
        unfinished = await uow.evidence_runs.unfinished(caller.tenant_id)
        return {
            "state": "observed" if records else "no_runs",
            "records": records,
            "declared_datasets": await uow.datasets.count_current(caller.tenant_id),
            "unfinished_runs": len(unfinished),
            "reason": (
                "No control has executed against this estate. Nothing on this page "
                "is a statement about data quality — it is a statement that nothing "
                "has been examined yet."
            )
            if not records
            else "",
        }

    async def incident_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """What is currently wrong, one row per control rather than per run.

        A control failing every hour for a week is one problem, and listing it
        168 times is how a triage queue becomes something nobody opens.
        """
        latest = await uow.evidence.latest_per_control(caller.tenant_id)
        incidents = [
            {
                "control_id": key,
                "dataset": record.dataset,
                "verdict": record.verdict,
                # The verdict at the width it was actually established. "passed"
                # after a full scan says the dataset is sound; after an
                # incremental run it says only that the rows examined were.
                "claim": record.claim,
                "coverage": record.coverage,
                "detail": record.detail,
                "finished_at": record.finished_at,
                "metrics": record.metrics,
                "sample_count": record.sample_count,
                "sequence": record.sequence,
            }
            for key, record in latest.items()
            if record.verdict in UNRESOLVED
        ]
        incidents.sort(key=lambda item: (item["verdict"] != "fail", item["finished_at"]))
        return render(
            request,
            "incidents/list.html",
            observation=await self._observation(caller, uow),
            incidents=incidents,
            passing=sum(1 for r in latest.values() if r.verdict == "pass"),
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
        )

    async def scorecard_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """A score per dataset, decomposed.

        Built from the *latest* record per control, never from every record: a
        score over the whole ledger weights an hourly control sixty times as
        heavily as a daily one, which measures the schedule rather than the
        data.
        """
        latest = await uow.evidence.latest_per_control(caller.tenant_id)
        by_dataset: dict[str, list[Any]] = {}
        for record in latest.values():
            if not record.dataset:
                continue
            by_dataset.setdefault(record.dataset, []).append(record)

        scores = []
        for dataset, records in sorted(by_dataset.items()):
            result = score(dataset, _measurements(records))
            scores.append(
                {
                    "subject": dataset,
                    "value": result.composite(Method.WEIGHTED),
                    "coverage": result.coverage,
                    "controls": result.controls,
                    "not_run": result.not_run,
                    "worst": result.worst,
                    "methods_disagree": result.methods_disagree,
                    "composites": {
                        method.value: value for method, value in result.composites.items()
                    },
                    "explanation": result.describe(),
                    "components": [
                        {
                            "dimension": part.dimension.value,
                            "value": part.score,
                            "description": part.describe(),
                        }
                        for part in result.dimensions
                    ],
                }
            )
        return render(
            request,
            "scorecards/list.html",
            observation=await self._observation(caller, uow),
            scores=scores,
            # True when every record scored carries its own dimension. A chain
            # written before evidence format 1.1 does not, and those records
            # land in the unclassified bucket rather than being spread across
            # the six by guesswork — so the screen can say which it is showing
            # instead of implying a breakdown it does not have.
            decomposed=all(
                record.dimensions for records in by_dataset.values() for record in records
            ),
            undecomposed=sum(
                1 for records in by_dataset.values() for record in records if not record.dimensions
            ),
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


def _measurements(records: list[Any]) -> list[Measurement]:
    """Every record for one dataset, as scoreable measurements.

    A record may name more than one dimension — a control can be about
    completeness *and* validity — and each gets its own measurement, so a
    control that covers two dimensions contributes to both rather than to
    whichever one happened to be listed first.
    """
    out: list[Measurement] = []
    for record in records:
        for dimension in record.dimensions or (UNCLASSIFIED,):
            out.append(_measurement(record, dimension))
    return out


def _measurement(record: Any, dimension: str) -> Measurement:
    """One evidence record as a scoreable measurement.

    A record that could not produce a verdict is passed through with
    ``ran=False`` rather than dropped. That is the whole reason the field
    exists: scoring a failed run as zero turns "we could not look" into "we
    looked and it was terrible", scoring it as one turns it into "we looked and
    it was perfect", and dropping it silently makes a dataset whose controls
    half failed to execute score the same as one where they all passed. Carried
    through, it lands in ``Score.not_run`` and the coverage figure beside the
    number.
    """
    scanned = int(record.metrics.get("scanned_rows", 0))
    ran = record.verdict not in ("error", "skipped", "indeterminate") and scanned > 0
    return Measurement(
        control=record.control_id or record.plan_id,
        dimension=_dimension(dimension),
        scanned=scanned,
        violations=int(record.metrics.get("violating_rows", 0)),
        criticality=Criticality(record.criticality),
        ran=ran,
    )


def _dimension(name: str) -> Dimension:
    """A stored dimension name as the enum, or the unclassified bucket.

    A name this build does not recognise lands in ``conformity`` rather than
    raising: a record from a future build is a reason to score it less
    precisely, not a reason to fail the whole scorecard.
    """
    try:
        return Dimension(name)
    except ValueError:
        return Dimension.CONFORMITY
