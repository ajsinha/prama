"""The agent fleet's store: agents, enrolment tokens, the zone queues, gaps.

Every read takes the tenant, with two declared exceptions, each of which is the
step that *establishes* the tenant rather than one that ignores it:
`token_by_digest` (an enrolling agent holds a token and nothing else) and
`agent_for_message` (a signed message names its agent, and the signature, whose
key is derived from the tenant, is what proves which estate it belongs to).

Claims are conditional updates, so two agents asking at once cannot both take
the same assignment: the second update matches no row.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import CursorResult, delete, select, update

from prama.core.errors import NotFoundError
from prama.db.dao.base import Dao
from prama.db.models.fleet import FlAgent, FlAssignment, FlGap, FlToken

#: States in which an assignment still wants doing.
OPEN = ("queued", "claimed")


def _own(tenant_id: str, row: Any) -> None:
    """Refuse a row from another estate, however the caller came by it."""
    if row.tenant_id != tenant_id:
        raise NotFoundError(
            f"{type(row).__name__} {row.id!r} does not exist in this estate",
            remedy="Load it through this estate's own reads.",
            context={"tenant": tenant_id},
        )


def _rows(result: Any) -> int:
    """How many rows a conditional update matched."""
    return int(result.rowcount or 0) if isinstance(result, CursorResult) else 0


class FleetDao(Dao[FlAgent]):
    """Agents, tokens, assignments and gaps, one estate at a time."""

    model = FlAgent

    # -- enrolment tokens --------------------------------------------------

    async def create_token(
        self,
        tenant_id: str,
        *,
        digest: str,
        zone: str,
        name: str,
        issued_by: str | None,
        issued_at: str,
        expires_at: str,
    ) -> FlToken:
        row = FlToken(
            tenant_id=tenant_id,
            digest=digest,
            zone=zone,
            name=name,
            issued_by=issued_by,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._guarded_flush()
        return row

    async def token_by_digest(self, digest: str) -> FlToken | None:
        """The token with this digest, in whichever estate issued it.

        Unscoped by necessity and declared as such: the token is how an
        enrolling agent's estate is established.
        """
        result = await self._session.execute(select(FlToken).where(FlToken.digest == digest))
        return result.scalars().first()

    async def redeem(self, tenant_id: str, token: FlToken, *, agent: FlAgent, now: str) -> bool:
        """Mark *token* used by *agent*. False if somebody redeemed it first."""
        result = await self._session.execute(
            update(FlToken)
            .where(
                FlToken.id == token.id,
                FlToken.tenant_id == tenant_id,
                FlToken.redeemed_at.is_(None),
            )
            .values(redeemed_at=now, agent_id=agent.id)
            .execution_options(synchronize_session=False)
        )
        return _rows(result) == 1

    # -- agents ------------------------------------------------------------

    async def create_agent(
        self,
        tenant_id: str,
        *,
        name: str,
        zone: str,
        version: str,
        capabilities: dict[str, Any],
        enrolled_at: str,
    ) -> FlAgent:
        row = FlAgent(
            tenant_id=tenant_id,
            name=name,
            zone=zone,
            state="active",
            version=version,
            capabilities_json=capabilities,
            pending_findings=0,
            last_sequence=-1,
            enrolled_at=enrolled_at,
            last_seen_at=enrolled_at,
        )
        self._session.add(row)
        await self._guarded_flush()
        return row

    async def agent_for_message(self, agent_id: str) -> FlAgent | None:
        """The agent a signed message names, in whichever estate enrolled it.

        Unscoped by necessity and declared as such: the caller verifies the
        signature with a key derived from the row's own tenant before
        believing anything, so a message cannot borrow another estate.
        """
        return await self._session.get(FlAgent, agent_id)

    async def agent(self, tenant_id: str, agent_id: str) -> FlAgent | None:
        row = await self._session.get(FlAgent, agent_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def agents(self, tenant_id: str) -> list[FlAgent]:
        await self._session.flush()
        result = await self._session.execute(
            select(FlAgent)
            .where(FlAgent.tenant_id == tenant_id)
            .order_by(FlAgent.zone, FlAgent.name, FlAgent.id)
        )
        return list(result.scalars().all())

    async def set_state(self, tenant_id: str, agent: FlAgent, state: str) -> FlAgent:
        _own(tenant_id, agent)
        agent.state = state
        await self._guarded_flush()
        return agent

    async def seen(
        self,
        tenant_id: str,
        agent: FlAgent,
        *,
        now: str,
        version: str | None = None,
        capabilities: dict[str, Any] | None = None,
        pending_findings: int | None = None,
        last_sequence: int | None = None,
    ) -> FlAgent:
        """Record that *agent* called, and what it said about itself."""
        _own(tenant_id, agent)
        agent.last_seen_at = now
        if version is not None:
            agent.version = version
        if capabilities is not None:
            agent.capabilities_json = capabilities
        if pending_findings is not None:
            agent.pending_findings = pending_findings
        if last_sequence is not None:
            agent.last_sequence = last_sequence
        await self._guarded_flush()
        return agent

    # -- the zone queues ---------------------------------------------------

    async def queue(
        self,
        tenant_id: str,
        *,
        zone: str,
        control_id: str,
        control_version: int,
        plan_id: str,
        dataset: str,
        engine: str,
        pql: str,
        assignment: dict[str, Any],
        queued_at: str,
        queued_by: str | None,
        state: str = "queued",
        reasons: list[str] | None = None,
    ) -> FlAssignment:
        row = FlAssignment(
            tenant_id=tenant_id,
            zone=zone,
            control_id=control_id,
            control_version=control_version,
            plan_id=plan_id,
            dataset=dataset,
            engine=engine,
            pql=pql,
            assignment_json=assignment,
            state=state,
            reasons_json=list(reasons or ()),
            queued_by=queued_by,
            queued_at=queued_at,
            attempts=0,
        )
        self._session.add(row)
        await self._guarded_flush()
        return row

    async def open_for(
        self, tenant_id: str, zone: str, control_id: str, engine: str
    ) -> list[FlAssignment]:
        """This control's queued or claimed work for this zone and engine."""
        await self._session.flush()
        result = await self._session.execute(
            select(FlAssignment)
            .execution_options(populate_existing=True)
            .where(
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.zone == zone,
                FlAssignment.control_id == control_id,
                FlAssignment.engine == engine,
                FlAssignment.state.in_(OPEN),
            )
        )
        return list(result.scalars().all())

    async def discard_unassignable(
        self, tenant_id: str, zone: str, control_id: str, engine: str
    ) -> int:
        """Forget an earlier dispatch's "could not compile" for this control, before
        trying again: the new attempt's outcome replaces it rather than joining it."""
        result = await self._session.execute(
            delete(FlAssignment)
            .where(
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.zone == zone,
                FlAssignment.control_id == control_id,
                FlAssignment.engine == engine,
                FlAssignment.state == "unassignable",
            )
            .execution_options(synchronize_session=False)
        )
        return _rows(result)

    async def queued(self, tenant_id: str, zone: str) -> list[FlAssignment]:
        """The zone's queue, oldest first."""
        await self._session.flush()
        result = await self._session.execute(
            select(FlAssignment)
            .execution_options(populate_existing=True)
            .where(
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.zone == zone,
                FlAssignment.state == "queued",
            )
            .order_by(FlAssignment.queued_at, FlAssignment.id)
        )
        return list(result.scalars().all())

    async def claim(
        self,
        tenant_id: str,
        assignment: FlAssignment,
        *,
        agent_id: str,
        now: str,
        lease_until: str,
    ) -> bool:
        """Take *assignment* for *agent_id*. False if another agent got it first."""
        result = await self._session.execute(
            update(FlAssignment)
            .where(
                FlAssignment.id == assignment.id,
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.state == "queued",
            )
            .values(
                state="claimed",
                claimed_by=agent_id,
                claimed_at=now,
                lease_until=lease_until,
                attempts=FlAssignment.attempts + 1,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = _rows(result) == 1
        if claimed:
            await self._session.refresh(assignment)
        return claimed

    async def release_expired(self, tenant_id: str, *, now: str) -> int:
        """Return every claim whose lease has run out to the queue."""
        result = await self._session.execute(
            update(FlAssignment)
            .where(
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.state == "claimed",
                FlAssignment.lease_until < now,
            )
            .values(state="queued", claimed_by=None, claimed_at=None, lease_until=None)
            .execution_options(synchronize_session=False)
        )
        return _rows(result)

    async def release_claims_of(self, tenant_id: str, agent_id: str) -> int:
        """Return what *agent_id* holds to the queue: it will not be doing it."""
        result = await self._session.execute(
            update(FlAssignment)
            .where(
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.claimed_by == agent_id,
                FlAssignment.state == "claimed",
            )
            .values(state="queued", claimed_by=None, claimed_at=None, lease_until=None)
            .execution_options(synchronize_session=False)
        )
        return _rows(result)

    async def for_plan(self, tenant_id: str, zone: str, plan_id: str) -> list[FlAssignment]:
        """Every assignment of this plan to this zone, whatever its state."""
        await self._session.flush()
        result = await self._session.execute(
            select(FlAssignment)
            .execution_options(populate_existing=True)
            .where(
                FlAssignment.tenant_id == tenant_id,
                FlAssignment.zone == zone,
                FlAssignment.plan_id == plan_id,
            )
            .order_by(FlAssignment.queued_at, FlAssignment.id)
        )
        return list(result.scalars().all())

    async def mark_done(
        self, tenant_id: str, assignment: FlAssignment, *, now: str, evidence_sequence: int
    ) -> None:
        _own(tenant_id, assignment)
        assignment.state = "done"
        assignment.done_at = now
        assignment.lease_until = None
        assignment.evidence_sequence = evidence_sequence
        await self._guarded_flush()

    async def work(self, tenant_id: str) -> list[FlAssignment]:
        """Every assignment not yet done: queued, claimed, or unassignable."""
        await self._session.flush()
        result = await self._session.execute(
            select(FlAssignment)
            .execution_options(populate_existing=True)
            .where(FlAssignment.tenant_id == tenant_id, FlAssignment.state != "done")
            .order_by(FlAssignment.zone, FlAssignment.queued_at, FlAssignment.id)
        )
        return list(result.scalars().all())

    # -- gaps --------------------------------------------------------------

    async def record_gap(
        self,
        tenant_id: str,
        *,
        agent_id: str,
        first_sequence: int,
        last_sequence: int,
        dropped_at: str,
        reason: str,
        reported_at: str,
    ) -> bool:
        """Keep a reported gap. False when it was already kept: a redelivery."""
        await self._session.flush()
        existing = await self._session.execute(
            select(FlGap.id).where(
                FlGap.tenant_id == tenant_id,
                FlGap.agent_id == agent_id,
                FlGap.first_sequence == first_sequence,
                FlGap.last_sequence == last_sequence,
            )
        )
        if existing.first() is not None:
            return False
        self._session.add(
            FlGap(
                tenant_id=tenant_id,
                agent_id=agent_id,
                first_sequence=first_sequence,
                last_sequence=last_sequence,
                dropped_at=dropped_at,
                reason=reason[:4000],
                reported_at=reported_at,
            )
        )
        await self._guarded_flush()
        return True

    async def gaps(self, tenant_id: str, *, limit: int = 200) -> list[FlGap]:
        await self._session.flush()
        result = await self._session.execute(
            select(FlGap)
            .where(FlGap.tenant_id == tenant_id)
            .order_by(FlGap.reported_at.desc(), FlGap.id)
            .limit(limit)
        )
        return list(result.scalars().all())
