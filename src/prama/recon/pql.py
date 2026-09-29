"""A PQL ``RECONCILE`` plan, run by the reconciliation engine and judged like any control.

The plan names two datasets, a key, an amount and a tolerance. The engine
matches the rows, compares within the tolerance and classifies every
difference into a break. This turns that into the metrics the shared `judge`
reads — `violating_rows` is the count of breaks that need a person (a value
difference, a missing row), so a timing difference that clears itself does not
fail the control — and hands the breaks
back for the workbench. The control plane's run and an agent beside the data
both call it, so a reconciliation means one thing wherever it runs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from prama.core.errors import ValidationError
from prama.recon.engine import Definition, Reconciliation, Run, Side
from prama.recon.match import MatchKey
from prama.semantic.relationships import Tolerance


def definition_of(plan: Any) -> Definition:
    from prama.recon.normalise import AmountSpec

    detail = plan.detail
    keys = [tuple(k) for k in detail.get("keys") or []]
    target = str(detail.get("target_currency") or "")
    left_spec = AmountSpec(currency_column=str(detail.get("currency_column") or ""))
    right_spec = AmountSpec(currency=target)
    return Definition(
        name=f"{plan.scope.dataset} against {detail['against']}",
        left=Side(name=plan.scope.dataset, amount_column=str(detail["amount"][0]), spec=left_spec),
        right=Side(
            name=str(detail["against"]), amount_column=str(detail["amount"][1]), spec=right_spec
        ),
        target_currency=target,
        key=MatchKey(left=tuple(k[0] for k in keys), right=tuple(k[1] for k in keys)),
        tolerance=Tolerance(
            absolute=Decimal(detail["absolute"]) if detail.get("absolute") else None,
            relative=Decimal(detail["relative"]) / 100 if detail.get("relative") else None,
            currency=detail.get("currency") or None,
        ),
        date_window=int(detail.get("offset_days") or 0),
    )


def rates_from(rows: Sequence[dict[str, Any]], target: str, business_date: date) -> Any:
    """A rate source from a rates dataset: columns currency, rate (to *target*),
    and optionally as_of. Without as_of, each rate is taken as of the run's date."""
    from prama.recon.normalise import RateSource

    source = RateSource(source="rates dataset")
    for row in rows:
        lowered = {str(k).lower(): v for k, v in row.items()}
        when = lowered.get("as_of")
        day = date.fromisoformat(str(when)[:10]) if when else business_date
        source.add(str(lowered["currency"]).upper(), target, day, str(lowered["rate"]))
    return source


def measure(
    plan: Any,
    left: Sequence[dict[str, Any]],
    right: Sequence[dict[str, Any]],
    *,
    business_date: date,
    rates: Sequence[dict[str, Any]] | None = None,
) -> tuple[dict[str, float], Run]:
    """Metrics for `judge`, and the run (with its breaks) for the workbench."""
    target = str(plan.detail.get("target_currency") or "")
    source = rates_from(rates or [], target, business_date) if target else None
    run = Reconciliation(definition_of(plan), rates=source).run(
        left, right, business_date=business_date
    )
    if not run.completed:
        raise ValidationError(
            run.headline(),
            remedy="A reconciliation missing some of its rows is a wrong one; fix the input.",
        )
    report = run.match
    metrics = {
        "scanned_rows": float(report.left_rows + len(report.unmatched_right)),
        "violating_rows": float(len(run.population.needs_a_person)),
        "matched_pairs": float(len(report.pairs)),
        "missing_in_counterpart": float(len(report.unmatched_left)),
        "missing_here": float(len(report.unmatched_right)),
        "breaks": float(len(run.population)),
    }
    # The headline number, recorded so a reader of the evidence — the
    # reconciliation list, a period-end certificate — does not have to
    # reconstruct it from counts that measure something else (`scanned_rows`
    # counts left rows, not both sides). Absent rather than 1.0 over two empty
    # sides: a reconciliation over nothing has not matched anything.
    if report.match_rate is not None:
        metrics["match_rate"] = float(report.match_rate)
    return metrics, run
