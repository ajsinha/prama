"""Assembling an attestation from the evidence, rather than from a form.

The temptation with a sign-off screen is to let somebody type the numbers. This
does the opposite: the coverage, the exceptions and the evidence root are all
*derived* from the ledger, and the only thing the attester supplies is the
sentence and their name.

That is the whole safeguard. An attestation whose figures were typed is a
statement about what the attester believed; one whose figures were derived is a
statement about what happened, which is what a regulator is asking for.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.report.attestation import Attestation, Coverage, Exception_

#: Verdicts that are not a pass, and what each means for a sign-off. An
#: attestation may carry any of them — the attester signs that they looked, not
#: that everything passed — but each has to appear as an exception rather than
#: be folded into a total.
UNRESOLVED = {
    "fail": "failed",
    "error": "could not be executed",
    "skipped": "was skipped",
    "indeterminate": "could not be established",
}


async def build(
    uow: Any,
    tenant_id: str,
    *,
    scope: str,
    period_start: str,
    period_end: str,
    attester_id: str,
    attester_name: str,
    statement: str,
    signed_at: str,
    dispositions: dict[str, str] | None = None,
) -> Attestation:
    """Everything an attestation needs, read from the ledger and the estate.

    ``dispositions`` are the attester's own words about each exception, keyed
    by control id. Supplying none is permitted and is itself informative: an
    exception signed without a word is one nobody explained.
    """
    dispositions = dispositions or {}
    records = await uow.evidence.in_period(tenant_id, period_start, period_end)
    root, count = await uow.evidence.period_root(tenant_id, period_start, period_end)
    live = await uow.controls.live(tenant_id)

    # The latest verdict per control *within the period*. A control that ran
    # nightly gets one line, not thirty, and the line is its state at the end
    # of the period rather than the first time it was checked.
    latest: dict[str, Any] = {}
    for record in records:
        key = record.control_id or record.plan_id
        if not key:
            continue
        seen = latest.get(key)
        if seen is None or record.sequence > seen.sequence:
            latest[key] = record

    exceptions: list[Exception_] = []
    passed = 0
    tally = dict.fromkeys(UNRESOLVED, 0)
    for key, record in sorted(latest.items()):
        if record.verdict == "pass":
            passed += 1
            continue
        tally[record.verdict] = tally.get(record.verdict, 0) + 1
        exceptions.append(
            Exception_(
                control_id=key,
                dataset=record.dataset,
                verdict=record.verdict,
                detail=record.detail
                or _counts(record.metrics)
                or UNRESOLVED.get(record.verdict, record.verdict),
                disposition=dispositions.get(key, ""),
            )
        )

    # Live controls that produced nothing in the period. Not an "exception" —
    # there is no verdict to except from — but the number that decides whether
    # the attestation means anything, so it is counted separately and printed.
    never_ran = sum(1 for control in live if str(control.control_id) not in latest)

    coverage = Coverage(
        controls_in_scope=max(len(live), len(latest)),
        controls_run=len(latest),
        passed=passed,
        failed=tally.get("fail", 0),
        not_established=tally.get("indeterminate", 0) + tally.get("skipped", 0),
        errored=tally.get("error", 0),
        never_ran=never_ran,
    )
    return Attestation(
        attester_id=attester_id,
        attester_name=attester_name,
        statement=statement,
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        coverage=coverage,
        evidence_root=root,
        evidence_records=count,
        exceptions=tuple(exceptions),
        signed_at=signed_at,
        tenant_id=tenant_id,
    )


def _counts(metrics: dict[str, float]) -> str:
    scanned = int(metrics.get("scanned_rows", 0))
    if "distinct_keys" in metrics:
        return f"{scanned - int(metrics['distinct_keys']):,} duplicate(s) in {scanned:,} rows"
    if "violating_rows" in metrics:
        return f"{int(metrics['violating_rows']):,} of {scanned:,} rows"
    return ""
