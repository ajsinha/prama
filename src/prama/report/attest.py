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

import dataclasses
from typing import Any

from prama.core.clock import utc_now
from prama.core.errors import ValidationError
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


def sealing_key(config: Any) -> bytes:
    """The key an attestation is sealed with.

    The session secret, which a deployment must set and which is refused
    empty. A dedicated signing key belongs to Wave 10's key management; the
    distinction matters and is stated on the screen rather than implied by the
    word "signed".
    """
    secret: str = config.require_secret("security.session_secret")
    return secret.encode()


def default_period(start: str = "", end: str = "") -> tuple[str, str]:
    """The period a draft covers when none is given: this month, to today."""
    now = utc_now()
    return start or now.replace(day=1).date().isoformat(), end or now.date().isoformat()


async def draft(
    uow: Any, tenant_id: str, *, attester_id: str, scope: str, start: str = "", end: str = ""
) -> Attestation:
    """What would be attested to, before anybody signs it."""
    period_start, period_end = default_period(start, end)
    return await build(
        uow,
        tenant_id,
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        attester_id=attester_id,
        attester_name="",
        statement="",
        signed_at="",
    )


async def sign(
    uow: Any,
    tenant_id: str,
    *,
    key: bytes,
    attester_id: str,
    attester_name: str,
    statement: str,
    scope: str,
    period_start: str,
    period_end: str,
    dispositions: dict[str, str] | None = None,
    supersedes: str = "",
    supersedes_because: str = "",
) -> Any:
    """Derive the attestation again, seal it, and record it.

    Rebuilt from the ledger rather than from whatever the caller was shown, so
    what is signed is what the evidence says at the moment of signing — not
    what a page rendered some minutes earlier and a browser posted back.
    """
    if not attester_name.strip():
        raise ValidationError(
            "an attestation needs the name of the person signing it",
            remedy=(
                "A control attested by 'the team' is a control nobody "
                "attested. Give the name of the person accountable."
            ),
        )
    if not statement.strip():
        raise ValidationError(
            "an attestation needs a statement",
            remedy=(
                "Say what you are attesting to, in your own words. It is "
                "printed on the artefact and quoted back at review."
            ),
        )
    attestation = await build(
        uow,
        tenant_id,
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        attester_id=attester_id,
        attester_name=attester_name.strip(),
        statement=statement.strip(),
        signed_at=utc_now().isoformat(),
        dispositions=dispositions,
    )
    if supersedes:
        # Checked against the caller's own estate before it is recorded.
        # Signing from one estate while naming another estate's attestation id
        # used to succeed, and the record then claimed to supersede an
        # attestation its signer had no standing over (QA finding UI-122).
        # `in_tenant` raises a not-found for an id outside the estate, which is
        # the right answer twice over — it refuses, and it does not confirm
        # that the id exists somewhere else.
        await uow.attestations.in_tenant(supersedes, tenant_id)
        if not supersedes_because.strip():
            # The one record that says "what I previously attested no longer
            # stands" could once be written with nothing at all: an audit trail
            # with a hole in exactly the interesting place. QA round 4, UI-123.
            raise ValidationError(
                "superseding an attestation needs a reason",
                remedy=(
                    "Say why the earlier attestation no longer stands. "
                    "A withdrawal nobody explained is the one an examiner "
                    "will ask about first."
                ),
            )
        attestation = dataclasses.replace(
            attestation, supersedes=supersedes, supersedes_because=supersedes_because
        )
    return await uow.attestations.sign(
        attestation, seal=attestation.seal(key), supersedes=supersedes or None
    )


def row_view(row: Any) -> dict[str, Any]:
    """A signed attestation's register entry."""
    return {
        "id": str(row.id),
        "attester_id": row.attester_id,
        "attester_name": row.attester_name,
        "statement": row.statement,
        "scope": row.scope,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "coverage": dict(row.coverage_json or {}),
        "exceptions": list(row.exceptions_json or []),
        "evidence_root": row.evidence_root,
        "evidence_records": row.evidence_records,
        "content_hash": row.content_hash,
        "seal": row.seal,
        "signed_at": row.signed_at,
        "supersedes": row.supersedes,
        "supersedes_because": row.supersedes_because,
        "superseded_by": row.superseded_by,
        "version": row.version,
    }


def _counts(metrics: dict[str, float]) -> str:
    scanned = int(metrics.get("scanned_rows", 0))
    if "distinct_keys" in metrics:
        return f"{scanned - int(metrics['distinct_keys']):,} duplicate(s) in {scanned:,} rows"
    if "violating_rows" in metrics:
        return f"{int(metrics['violating_rows']):,} of {scanned:,} rows"
    return ""
