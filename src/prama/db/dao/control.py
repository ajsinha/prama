"""The control estate's access layer.

One rule shapes this file: **the PQL text is the authority, and everything else
is derived from it here.** ``plan_id``, ``severity``, ``dimensions`` and the
content hash are computed when a version is written and are never accepted from
a caller. They exist as columns so the estate can be queried without parsing
every control; they are not a second place to state the same fact.

That matters more than it sounds. A caller who could supply a severity could
store a control whose text says ``SEVERITY minor`` and whose row says
``critical`` — and the row is what the alert router reads. Nothing would look
wrong until an incident was routed to the wrong person at three in the morning.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from prama.core.errors import ValidationError
from prama.core.provenance import content_hash
from prama.db.dao.base import Dao
from prama.db.dao.versioned import VersionedDao
from prama.db.models.control import CtlControl, CtlControlVersion, CtlRejection
from prama.db.temporal import Provenance, TemporalQuery
from prama.ir.resolve import resolved
from prama.pql import parse_control
from prama.pql.errors import PqlError


def derived_fields(pql: str) -> dict[str, Any]:
    """Everything the text determines, computed once, in one place.

    Parsing and lowering here rather than trusting the caller is what keeps the
    row and the text from disagreeing. A control that will not parse is refused
    outright: storing it would mean an estate containing a control nothing can
    execute, discovered at run time by a scheduler with nowhere to report it.
    """
    try:
        control = parse_control(pql)
    except PqlError as exc:
        raise ValidationError(
            "that control does not parse, so it cannot be stored",
            remedy=(
                "Fix the PQL first. A control that cannot be parsed cannot be executed, "
                f"and storing it would hide that until it was due to run. {exc}"
            ),
            cause=exc,
        ) from exc

    fields: dict[str, Any] = {
        "name": control.name or "",
        "dataset": control.target or "",
        "severity": control.severity.value,
        "dimensions_json": [dimension.value for dimension in control.dimensions],
        "content_hash": content_hash(control.render()),
        "plan_id": "",
    }
    try:
        fields["plan_id"] = resolved(control).plan_id
    except Exception:
        # A control that parses but cannot be lowered for this build is stored
        # without a plan id rather than refused. The text is still the
        # authority and still reviewable; what is lost is the ability to
        # execute it, and that is visible as an empty plan_id rather than as a
        # control that quietly never runs.
        fields["plan_id"] = ""
    return fields


class ControlDao(VersionedDao[CtlControl, CtlControlVersion]):
    """Controls, bitemporal like every other declaration."""

    model = CtlControl
    version_model = CtlControlVersion
    entity_key = "control_id"

    async def by_identity(self, tenant_id: str, identity: str) -> CtlControlVersion | None:
        """The current version of the control with this identity, if any.

        The lookup that makes regeneration idempotent: a generator asks this
        before proposing, and amends what it finds instead of creating a
        duplicate nobody recognises.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(CtlControlVersion)
            .join(CtlControl, CtlControl.id == CtlControlVersion.control_id)
            .where(CtlControl.tenant_id == tenant_id, CtlControl.identity == identity),
            CtlControlVersion,
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def by_control_id(self, tenant_id: str, control_id: str) -> CtlControlVersion | None:
        """The current version of one control, by its identifier.

        Scoped by tenant, like every lookup that takes an identifier from a
        URL. The version rather than the control row, because everything a
        screen wants to show — the PQL, the severity, the dimensions — lives on
        the version, and a caller handed the control row would have to go
        looking for the current one and could get it wrong.
        """
        found = await self._current_where(tenant_id, CtlControl.id == control_id)
        return found[0] if found else None

    async def declare(
        self,
        *,
        tenant_id: str,
        identity: str,
        pql: str,
        origin: str = "declaration",
        rule: str = "",
        source_ref: str = "",
        provenance: dict[str, Any] | None = None,
        status: str = "proposed",
        criticality: int = 4,
        schedule: str = "",
        owner_id: str | None = None,
        authored_by: str | None = None,
        approved_by: str | None = None,
        reason: str = "",
        valid_from: datetime | None = None,
    ) -> tuple[CtlControl, CtlControlVersion]:
        """Record a control, or amend the one that already has this identity.

        Idempotent by identity rather than by text, which is the whole point:
        re-running a generator after a threshold changed amends the control,
        and re-running it after nothing changed does nothing at all.
        """
        fields = derived_fields(pql)
        existing = await self.by_identity(tenant_id, identity)
        if existing is not None:
            if existing.content_hash == fields["content_hash"]:
                # Nothing changed. Writing a new version anyway would fill the
                # history with entries that differ only in their timestamp,
                # and make a genuine change impossible to find in the diff.
                return existing.control, existing
            version = await self.amend(
                existing.control_id,
                provenance=Provenance(
                    authored_by=authored_by,
                    approved_by=approved_by,
                    reason=reason or "the control changed",
                ),
                pql=pql,
                origin=origin,
                rule=rule,
                source_ref=source_ref,
                provenance_json=provenance or {},
                status=status,
                criticality=criticality,
                schedule=schedule,
                owner_id=owner_id,
                **fields,
            )
            return existing.control, version

        return await self.create(
            tenant_id=tenant_id,
            identity_fields={"identity": identity},
            provenance=Provenance(
                authored_by=authored_by,
                approved_by=approved_by,
                reason=reason or "initial declaration",
            ),
            valid_from=valid_from,
            pql=pql,
            origin=origin,
            rule=rule,
            source_ref=source_ref,
            provenance_json=provenance or {},
            status=status,
            criticality=criticality,
            schedule=schedule,
            owner_id=owner_id,
            **fields,
        )

    async def activate(
        self, control_id: str, *, approved_by: str, reason: str = ""
    ) -> CtlControlVersion:
        """Accept a proposal: the control begins to run.

        An amend rather than a correct. The control genuinely was a proposal
        until somebody approved it, and the evidence produced before that
        moment — none, since a proposal does not run — should resolve to the
        proposed version.
        """
        return await self.amend(
            control_id,
            provenance=Provenance(approved_by=approved_by, reason=reason or "accepted"),
            status="active",
        )

    async def suppress(
        self, control_id: str, *, until: str, because: str, by: str | None = None
    ) -> CtlControlVersion:
        """Silence a control, with an expiry and a reason.

        Both required, and required by the schema rather than by this method:
        a control silenced indefinitely with no stated reason is one nobody
        will ever turn back on, and "temporarily" muting a control is the
        commonest way an estate quietly stops checking something.
        """
        if not until.strip() or not because.strip():
            raise ValidationError(
                "suppressing a control needs both an expiry and a reason",
                remedy=(
                    "Say when it should start running again and why it is being "
                    "silenced. A control muted with neither is one nobody turns "
                    "back on, and the estate stops checking something without "
                    "anyone deciding to."
                ),
            )
        return await self.amend(
            control_id,
            provenance=Provenance(authored_by=by, reason=f"suppressed: {because}"),
            status="suppressed",
            suppressed_until=until,
            suppressed_because=because,
        )

    async def retire(
        self, control_id: str, *, provenance: Provenance | None = None
    ) -> CtlControlVersion:
        """Stop running a control without deleting it.

        Never deleted: the evidence it produced has to stay attributable to
        something, and a record naming a control that no longer exists is an
        audit trail with a hole in it.
        """
        return await self.amend(
            control_id,
            provenance=provenance or Provenance(reason="retired"),
            status="retired",
        )

    # -- reading -----------------------------------------------------------

    async def live(self, tenant_id: str) -> list[CtlControlVersion]:
        """Controls that will actually run.

        ``proposed`` and ``suppressed`` are excluded, and their exclusion is
        the point: both are states a reader mistakes for running, and a
        coverage figure that counted them would claim protection the estate
        does not have.
        """
        return await self._current_where(tenant_id, CtlControlVersion.status == "active")

    async def for_dataset(self, tenant_id: str, dataset: str) -> list[CtlControlVersion]:
        return await self._current_where(tenant_id, CtlControlVersion.dataset == dataset)

    async def of_status(self, tenant_id: str, status: str) -> list[CtlControlVersion]:
        return await self._current_where(tenant_id, CtlControlVersion.status == status)

    async def silenced_past_expiry(self, tenant_id: str, now: str) -> list[CtlControlVersion]:
        """Controls whose suppression has run out and that nobody re-enabled.

        A report rather than an automatic un-suppression: turning a control
        back on by itself would surprise whoever silenced it, and leaving it
        silent for ever is how "temporary" becomes permanent. Naming them is
        the only honest option.
        """
        return await self._current_where(
            tenant_id,
            CtlControlVersion.status == "suppressed",
            CtlControlVersion.suppressed_until.is_not(None),
            CtlControlVersion.suppressed_until <= now,
        )

    async def _current_where(self, tenant_id: str, *conditions: Any) -> list[CtlControlVersion]:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(CtlControlVersion)
            .join(CtlControl, CtlControl.id == CtlControlVersion.control_id)
            .where(CtlControl.tenant_id == tenant_id, *conditions),
            CtlControlVersion,
        ).order_by(CtlControlVersion.criticality, CtlControlVersion.name)
        return list((await self._session.execute(stmt)).scalars().all())


class RejectionDao(Dao[CtlRejection]):
    """Proposals somebody turned down."""

    model = CtlRejection

    async def record(
        self,
        *,
        tenant_id: str,
        identity: str,
        content_hash: str = "",
        reason: str = "incorrect",
        note: str = "",
        rejected_by: str | None = None,
        rejected_at: str,
    ) -> CtlRejection:
        rejection = CtlRejection(
            tenant_id=tenant_id,
            identity=identity,
            content_hash=content_hash,
            reason=reason,
            note=note,
            rejected_by=rejected_by,
            rejected_at=rejected_at,
        )
        self.add(rejection)
        await self._session.flush()
        return rejection

    async def was_rejected(self, tenant_id: str, identity: str, content_hash: str) -> bool:
        """Whether this exact proposal has already been refused.

        Keyed on the content as well as the identity, and that distinction is
        what keeps the check useful: rejecting a control does not reject every
        future version of it. A materially different rewrite of the same rule
        is a new question and deserves to be asked again — while an unchanged
        re-proposal, which is what a nightly generator produces, does not.
        """
        await self._session.flush()
        stmt = select(CtlRejection.id).where(
            CtlRejection.tenant_id == tenant_id,
            CtlRejection.identity == identity,
            CtlRejection.content_hash == content_hash,
        )
        return (await self._session.execute(stmt)).first() is not None

    async def for_tenant(self, tenant_id: str, *, limit: int = 500) -> list[CtlRejection]:
        await self._session.flush()
        stmt = (
            select(CtlRejection)
            .where(CtlRejection.tenant_id == tenant_id)
            .order_by(CtlRejection.rejected_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())
