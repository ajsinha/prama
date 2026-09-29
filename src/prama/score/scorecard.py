"""Scorecards: a score per dataset and for the estate, decomposed, from evidence.

Built from the *latest* record per control, never from every record: a score
over the whole ledger weights an hourly control sixty times as heavily as a
daily one, which measures the schedule rather than the data.

Nothing here is typed in and nothing is a model's opinion. Each number derives
from recorded verdicts and row counts through `prama.score.composite`, and
every number carries its decomposition, its coverage and the controls that
could not run — a score that cannot be explained is a score nobody will act on.

The console's scorecard screen and ``/api/v1/scorecards`` both read through here.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from prama.core.errors import NotFoundError
from prama.pql.ast import Dimension
from prama.score.composite import Measurement, Method, score
from prama.semantic.values import Criticality

#: Where a record with no dimension of its own goes — one written before
#: evidence format 1.1. Deliberately a real dimension rather than a synthetic
#: "other": the score still has to add up, and the screen says how many landed
#: here rather than letting the bucket pass for a finding.
UNCLASSIFIED = "conformity"

#: The subject of the estate-wide card.
ESTATE = "estate"


def card(subject: str, records: Iterable[Any]) -> dict[str, Any]:
    """One scorecard: the composite, how it decomposes, and what it does not cover."""
    result = score(subject, _measurements(list(records)))
    return {
        "subject": subject,
        "value": result.composite(Method.WEIGHTED),
        "coverage": result.coverage,
        "controls": result.controls,
        "not_run": result.not_run,
        "worst": result.worst.to_dict() if result.worst else None,
        "methods_disagree": result.methods_disagree,
        "composites": {method.value: value for method, value in result.composites.items()},
        "explanation": result.describe(),
        "components": [{**part.to_dict(), "value": part.score} for part in result.dimensions],
    }


async def scorecards(uow: Any, tenant_id: str) -> dict[str, Any]:
    """A card per dataset, one for the estate, and whether the breakdown is real.

    ``decomposed`` is true when every record scored carries its own dimension.
    A chain written before evidence format 1.1 does not, and those records land
    in the unclassified bucket rather than being spread across the six by
    guesswork — so a reader can say which it is showing instead of implying a
    breakdown it does not have.
    """
    latest = await uow.evidence.latest_per_control(tenant_id)
    by_dataset: dict[str, list[Any]] = {}
    for record in latest.values():
        if not record.dataset:
            continue
        by_dataset.setdefault(record.dataset, []).append(record)
    scored = [record for records in by_dataset.values() for record in records]
    return {
        "scores": [card(dataset, records) for dataset, records in sorted(by_dataset.items())],
        "estate": card(ESTATE, scored),
        "decomposed": all(record.dimensions for record in scored),
        "undecomposed": sum(1 for record in scored if not record.dimensions),
    }


async def for_dataset(uow: Any, tenant_id: str, dataset: str) -> dict[str, Any]:
    """One dataset's card, or a not-found when no control has evidence for it."""
    latest = await uow.evidence.latest_per_control(tenant_id)
    records = [record for record in latest.values() if record.dataset == dataset]
    if not records:
        raise NotFoundError(
            f"no control has recorded evidence for {dataset!r}",
            remedy=(
                "Nothing has been examined, which is not the same as nothing being wrong. "
                "Activate and run a control on it, then ask again."
            ),
            context={"dataset": dataset},
        )
    return card(dataset, records)


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


__all__ = ["ESTATE", "UNCLASSIFIED", "card", "for_dataset", "scorecards"]
