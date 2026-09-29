"""Reconciliations and their break queues, as the console and the API both read them.

One set of functions, called by the break workbench screen and by
``/api/v1/reconciliations`` and ``/api/v1/breaks``, so a program and a person
see the same queue in the same order and dispose of a break through the same
rules. Everything here reads what a control run recorded — the evidence ledger
and the break queue `prama.execute.run.ControlRun` fills. Nothing here runs a
reconciliation: a reconciliation is a control, and it runs the way every
control runs.

**A reconciliation and its queue are listed separately.** A verdict says
whether the two sides agreed; a queue says what people are doing about the
rows that did not. Merging them would let an empty queue read as a clean
reconciliation.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from prama.core.clock import utc_now
from prama.core.errors import NotFoundError, ValidationError
from prama.db.dao.recon import OUTSTANDING
from prama.recon.classify import BreakKind
from prama.recon.workbench import Row, in_working_order, row_of
from prama.recon.workflow import BreakQueue, Certificate, Comment, Item, State, certify

#: What `show` may be on the workbench.
SHOW = ("outstanding", "all")


# -- the break queue --------------------------------------------------------


async def workbench_rows(
    uow: Any, tenant_id: str, definition: str, *, show: str = "outstanding"
) -> tuple[list[Row], int]:
    """Every break for one reconciliation in working order, and how many have cleared.

    The cleared count is returned beside the rows because "forty cleared since
    yesterday" and "nothing changed" produce the same queue length.
    """
    states = None if show == "all" else OUTSTANDING
    found = await uow.breaks.for_definition(tenant_id, definition, states=states)
    cleared = await uow.breaks.for_definition(tenant_id, definition, states=("cleared",))
    return in_working_order(found, utc_now().date()), len(cleared)


async def workbench(
    uow: Any, tenant_id: str, definition: str, *, show: str = "outstanding"
) -> dict[str, Any]:
    """The workbench as data: the rows, and the groups the screen draws out of them."""
    if show not in SHOW:
        raise ValidationError(
            f"show must be one of {', '.join(SHOW)}, not {show!r}",
            remedy="`outstanding` is open and accepted breaks; `all` adds the cleared ones.",
        )
    rows, cleared = await workbench_rows(uow, tenant_id, definition, show=show)
    return {
        "definition": definition,
        "show": show,
        "rows": [row.to_dict() for row in rows],
        "cleared_count": cleared,
        # Identifiers rather than copies: the rows are already above, and a
        # second copy is one a client can update and the other not.
        "configuration": [row.id for row in rows if row.is_configuration],
        "stale": [row.id for row in rows if row.is_stale],
        "accepted": [row.id for row in rows if row.state == "accepted"],
        "by_state": dict(Counter(row.state for row in rows)),
        "by_owner": dict(
            Counter(row.owner or "unassigned" for row in rows if row.state != "accepted")
        ),
    }


async def get_break(uow: Any, tenant_id: str, break_id: str) -> Row:
    return row_of(await uow.breaks.in_tenant(break_id, tenant_id), utc_now().date())


async def assign(uow: Any, tenant_id: str, break_id: str, *, owner: str, by: str) -> Row:
    """Hand a break to somebody; the handover goes into its trail."""
    row = await uow.breaks.assign(break_id, tenant_id, owner=owner, by=by, at=utc_now().isoformat())
    return row_of(row, utc_now().date())


async def explain(uow: Any, tenant_id: str, break_id: str, *, text: str, by: str) -> Row:
    """Record what a person found out. Appends to the trail; never rewrites it."""
    row = await uow.breaks.explain(break_id, tenant_id, text=text, by=by, at=utc_now().isoformat())
    return row_of(row, utc_now().date())


async def accept(uow: Any, tenant_id: str, break_id: str, *, reason: str, by: str) -> Row:
    """Accept a break as a known reconciling item. It stays outstanding, and visible."""
    row = await uow.breaks.accept(
        break_id, tenant_id, reason=reason, by=by, at=utc_now().isoformat()
    )
    return row_of(row, utc_now().date())


# -- reconciliations ----------------------------------------------------------


def definition_of_control(pql: str) -> tuple[str, str, str] | None:
    """``(definition, dataset, against)`` for a RECONCILE control, else None.

    The definition name is the one the run files breaks under, derived by the
    same function the run uses — computed here a second way, the list and the
    workbench would name the same reconciliation differently and never meet.
    """
    if not " ".join(pql.upper().split()).startswith("RECONCILE"):
        return None
    from prama.ir.resolve import resolved
    from prama.pql import parse_control
    from prama.recon.pql import definition_of

    plan = resolved(parse_control(pql))
    if plan.assertion_kind != "reconcile":
        return None
    return definition_of(plan).name, plan.scope.dataset, str(plan.detail.get("against", ""))


def _result(record: Any) -> dict[str, Any]:
    rate = record.metrics.get("match_rate")
    return {
        "sequence": record.sequence,
        "verdict": record.verdict,
        "control_version": record.control_version,
        "engine": record.engine,
        "triggered_by": record.triggered_by,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        # None rather than 0.0 when the run did not record one: a
        # reconciliation over nothing has not matched 0% of anything.
        "match_rate": float(rate) if rate is not None else None,
        "breaks_needing_a_person": int(record.metrics.get("violating_rows", 0)),
        "metrics": dict(record.metrics),
        "detail": record.detail,
    }


async def _summary(uow: Any, tenant_id: str, version: Any, *, history: int = 0) -> dict[str, Any]:
    """One reconciliation; with *history*, that many of its latest results as well."""
    named = definition_of_control(version.pql)
    definition, dataset, against = named or ("", version.dataset, "")
    records = await uow.evidence.for_control(
        str(version.control_id), tenant_id=tenant_id, limit=max(1, history)
    )
    breaks = await uow.breaks.for_definition(tenant_id, definition) if definition else []
    summary = {
        "control_id": str(version.control_id),
        "identity": version.control.identity,
        "name": version.name,
        "status": version.status,
        "severity": version.severity,
        "pql": version.pql,
        "definition": definition,
        "dataset": dataset,
        "against": against,
        "latest": _result(records[0]) if records else None,
        # Counted over every state, cleared included: a reconciliation that
        # ran and cleared everything must not look like one that never ran.
        "breaks": dict(Counter(row.state for row in breaks)),
    }
    if history:
        # Newest first, the latest included.
        summary["history"] = [_result(record) for record in records]
    return summary


async def _reconcile_controls(uow: Any, tenant_id: str) -> list[Any]:
    found = []
    for status in ("active", "proposed", "suppressed"):
        for version in await uow.controls.of_status(tenant_id, status):
            if " ".join(version.pql.upper().split()).startswith("RECONCILE"):
                found.append(version)
    return found


async def reconciliations(uow: Any, tenant_id: str) -> dict[str, Any]:
    """Every RECONCILE control with its latest result, and every break queue.

    Queues with no control behind them are listed on their own — breaks from a
    reconciliation since retired, or observed by another path — because a
    queue nobody can find is a queue nobody works.
    """
    items = [
        await _summary(uow, tenant_id, version)
        for version in await _reconcile_controls(uow, tenant_id)
    ]
    claimed = {item["definition"] for item in items}
    queues = await uow.breaks.definitions(tenant_id)
    return {
        "reconciliations": items,
        "queues": queues,
        "unowned_queues": [name for name in queues if name not in claimed],
    }


async def reconciliation(
    uow: Any, tenant_id: str, control_id: str, *, history: int = 20
) -> dict[str, Any]:
    """One reconciliation: the control, its latest result and its recent runs."""
    version = await uow.controls.by_control_id(tenant_id, control_id)
    if version is None or definition_of_control(version.pql) is None:
        raise NotFoundError(
            f"there is no reconciliation {control_id!r}",
            remedy="List them with client.reconciliation.list(); a reconciliation is a "
            "RECONCILE control.",
            context={"control": control_id},
        )
    return await _summary(uow, tenant_id, version, history=max(1, history))


# -- the certificate ------------------------------------------------------------


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _item(row: Any) -> Item:
    return Item(
        key=row.break_key,
        kind=BreakKind(row.kind),
        difference=_decimal(row.difference),
        first_seen=date.fromisoformat(row.first_seen[:10]),
        last_seen=date.fromisoformat(row.last_seen[:10]),
        state=State(row.state),
        owner=row.owner,
        comments=tuple(
            Comment(at=str(c.get("at", "")), by=str(c.get("by", "")), text=str(c.get("text", "")))
            for c in row.comments_json or ()
        ),
        accepted_reason=row.accepted_reason,
    )


async def certificate(
    uow: Any,
    tenant_id: str,
    definition: str,
    *,
    signed_by: str,
    period_end: date | None = None,
) -> Certificate:
    """A statement of what is outstanding on this reconciliation, signed by the caller.

    Built from the persisted queue as it stands and the match rate the latest
    run recorded. Refused when no run recorded a match rate, rather than
    certified at an invented one: a certificate's headline number has to have
    been measured.
    """
    rows = await uow.breaks.for_definition(tenant_id, definition)
    latest = None
    for version in await _reconcile_controls(uow, tenant_id):
        named = definition_of_control(version.pql)
        if named and named[0] == definition:
            records = await uow.evidence.for_control(
                str(version.control_id), tenant_id=tenant_id, limit=1
            )
            if records and (latest is None or records[0].sequence > latest.sequence):
                latest = records[0]
    if not rows and latest is None:
        raise NotFoundError(
            f"there is no reconciliation {definition!r}",
            remedy="Use a definition name from client.reconciliation.list().",
            context={"definition": definition},
        )
    if latest is None or latest.metrics.get("match_rate") is None:
        raise ValidationError(
            f"no run of {definition!r} recorded a match rate, so there is nothing to certify",
            remedy="Run the reconciliation control (client.runs) and certify after it has run.",
            context={"definition": definition},
        )
    queue = BreakQueue()
    for row in rows:
        queue.update(_item(row))
    return certify(
        definition,
        queue,
        period_end=period_end or utc_now().date(),
        signed_by=signed_by,
        signed_at=utc_now().isoformat(),
        matched_rate=float(latest.metrics["match_rate"]),
    )


__all__ = [
    "SHOW",
    "accept",
    "assign",
    "certificate",
    "definition_of_control",
    "explain",
    "get_break",
    "reconciliation",
    "reconciliations",
    "workbench",
    "workbench_rows",
]
