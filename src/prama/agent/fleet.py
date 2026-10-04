"""The agent fleet, persisted: the server's side of docs/design/agent-fleet-http.md.

`prama.agent.coordinator` is the same conversation held in memory, for a single
process and its tests. This is the one the server runs: agents, tokens, the
zone queues and reported gaps live in the database (`fl_*` tables), so a
restart loses no agent, no claim and no hole in the evidence, and findings go
into the tenant's own evidence ledger, where the chain covers them.

What it refuses matters more than what it accepts, and each refusal is a rule:

* **An agent's zone is the token's**, fixed when an administrator issued it. The
  agent never names one, so it cannot ask for another zone's work.
* **A token is redeemed once**, and not after it expires. A replayable token is
  a credential that never expires.
* **No key is stored.** An agent's key is
  ``HMAC-SHA256(fleet secret, "agent:" + tenant_id + ":" + agent_id)``, derived
  when needed, so a copy of the database cannot sign as any agent, and the
  tenant is bound into every signature.
* **A message is believed only after its signature verifies**, over the
  canonical form the kernel's `signable()` gives the message rebuilt from what
  arrived. Unknown, suspended and revoked agents get a `Refusal`, which is the
  answer, not an HTTP error; a revoked agent's is permanent.
* **Work is claimed**, by a conditional update, so two agents in a zone never
  both take it; a claim not reported within its lease goes back to the queue.
* **Delivery is at-least-once**, so a report is deduplicated by the agent's own
  sequence exactly as the in-memory coordinator does: at or below the last
  accepted is a duplicate, a jump is named with the sequence that was expected.
* **Findings about work outside the agent's zone are not recorded.** A record
  whose plan was never assigned to the zone is rejected by sequence, so a
  compromised agent cannot write evidence about datasets it was never given.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from prama_kernel.agent.capability import AgentCapabilities, Unassignable, fits
from prama_kernel.agent.protocol import Assignment, Hello, Receipt, Refusal, Report
from prama_kernel.agent.signing import verify_payload

from prama.agent.assign import assignment_for
from prama.core.clock import Clock, SystemClock
from prama.core.config import Configuration
from prama.core.errors import (
    ConflictError,
    NotFoundError,
    SecretMissingError,
    UnauthorisedError,
    ValidationError,
)
from prama.core.log import get_logger

_log = get_logger(__name__)

#: Prefix of an enrolment token, so a leaked one is recognisable for what it is.
TOKEN_PREFIX = "pft_"

#: The longest an enrolment token may be issued for: a month. A token is
#: carried by hand or by a deployment tool; one that lived longer would be a
#: standing credential.
MAX_TOKEN_HOURS = 24 * 30


@dataclasses.dataclass(frozen=True, slots=True)
class FleetSettings:
    """The ``fleet:`` section of the configuration, read once."""

    secret: str = ""
    token_hours: float = 1.0
    lease_seconds: int = 900
    poll_seconds: int = 30
    stale_minutes: int = 15

    @classmethod
    def from_config(cls, config: Configuration) -> FleetSettings:
        return cls(
            # The fleet's own secret, falling back to the session secret, so an
            # installation that has one secret configured has a working fleet.
            secret=config.get_str("fleet.secret", "")
            or config.get_str("security.session_secret", ""),
            token_hours=config.get_float("fleet.token_hours", 1.0),
            lease_seconds=config.get_int("fleet.lease_seconds", 900),
            poll_seconds=config.get_int("fleet.poll_seconds", 30),
            stale_minutes=config.get_int("fleet.stale_minutes", 15),
        )


def derive_key(secret: str, tenant_id: str, agent_id: str) -> bytes:
    """An agent's signing key. Never stored; the same inputs give the same key."""
    if not secret:
        raise SecretMissingError(
            "no fleet secret is configured, so no agent key can be derived",
            remedy=(
                "Set fleet.secret (or security.session_secret) in "
                "config/application.local.yaml, which is not tracked. Never in "
                "application.yaml."
            ),
        )
    return hmac.new(
        secret.encode("utf-8"), f"agent:{tenant_id}:{agent_id}".encode(), hashlib.sha256
    ).digest()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds")


def _parse(stamp: str | None) -> datetime | None:
    return datetime.fromisoformat(stamp) if stamp else None


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _plan(pql: str) -> Any:
    """The plan a stored control text lowers to: the same path a run takes."""
    from prama.ir.resolve import resolved
    from prama.pql import parse_control

    return resolved(parse_control(pql))


def agent_view(agent: Any) -> dict[str, Any]:
    """An agent as an administrator sees it. Never a key: there is none to show."""
    return {
        "id": agent.id,
        "agent_id": agent.id,
        "name": agent.name,
        "zone": agent.zone,
        "state": agent.state,
        "version": agent.version,
        "capabilities": dict(agent.capabilities_json or {}),
        "enrolled_at": agent.enrolled_at,
        "last_seen_at": agent.last_seen_at,
        "pending_findings": agent.pending_findings,
        "last_sequence": agent.last_sequence,
    }


def _assignment_view(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "zone": row.zone,
        "control_id": row.control_id,
        "control_version": row.control_version,
        "plan_id": row.plan_id,
        "dataset": row.dataset,
        "engine": row.engine,
        "state": row.state,
        "claimed_by": row.claimed_by,
        "lease_until": row.lease_until,
        "reasons": list(row.reasons_json or ()),
    }


class Fleet:
    """The fleet's operations inside one unit of work."""

    def __init__(self, uow: Any, settings: FleetSettings, *, clock: Clock | None = None) -> None:
        self._uow = uow
        self._settings = settings
        self._clock = clock or SystemClock()
        #: The evidence records `report` put in the ledger, for the caller to
        #: alert on once they have committed (`prama.alert.pipeline`).
        self.reported: list[Any] = []

    # -- administration ----------------------------------------------------

    async def issue_token(
        self,
        tenant_id: str,
        zone: str,
        *,
        name: str = "",
        hours: float | None = None,
        issued_by: str | None = None,
    ) -> dict[str, Any]:
        """A one-use enrolment token for *zone*. The plaintext is returned once."""
        zone = zone.strip()
        if not zone:
            raise ValidationError(
                "an enrolment token needs a zone",
                remedy=(
                    "Name the zone the agent will belong to. Work is assigned by zone, "
                    "so an agent without one could be given any dataset's work."
                ),
            )
        lifetime = self._settings.token_hours if hours is None else float(hours)
        if not 0 < lifetime <= MAX_TOKEN_HOURS:
            raise ValidationError(
                f"an enrolment token lives more than 0 and at most {MAX_TOKEN_HOURS} hours",
                remedy="Issue it for as long as installing the agent will take, and no longer.",
                context={"hours": lifetime},
            )
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        now = self._clock.now()
        expires = now + timedelta(hours=lifetime)
        await self._uow.fleet.create_token(
            tenant_id,
            digest=_digest(token),
            zone=zone,
            name=name.strip(),
            issued_by=issued_by,
            issued_at=_iso(now),
            expires_at=_iso(expires),
        )
        return {"token": token, "zone": zone, "name": name.strip(), "expires_at": _iso(expires)}

    async def agents(self, tenant_id: str) -> list[dict[str, Any]]:
        return [agent_view(a) for a in await self._uow.fleet.agents(tenant_id)]

    async def suspend(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        agent = await self._require(tenant_id, agent_id)
        if agent.state == "revoked":
            raise ConflictError(
                "a revoked agent cannot be suspended; it is already stopped for good",
                remedy="Enrol a new agent if the zone needs one.",
                context={"agent_id": agent_id},
            )
        await self._uow.fleet.set_state(tenant_id, agent, "suspended")
        # Its work goes back to the zone: a suspended agent's reports are
        # refused, so anything it holds would otherwise wait out the lease.
        await self._uow.fleet.release_claims_of(tenant_id, agent.id)
        return agent_view(agent)

    async def resume(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        agent = await self._require(tenant_id, agent_id)
        if agent.state == "revoked":
            raise ConflictError(
                "a revoked agent is not reinstated",
                remedy=(
                    "Issue a new enrolment token and enrol the agent again. Revocation "
                    "that could be undone would be a suspension with a stronger name."
                ),
                context={"agent_id": agent_id},
            )
        await self._uow.fleet.set_state(tenant_id, agent, "active")
        return agent_view(agent)

    async def revoke(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        agent = await self._require(tenant_id, agent_id)
        await self._uow.fleet.set_state(tenant_id, agent, "revoked")
        await self._uow.fleet.release_claims_of(tenant_id, agent.id)
        return agent_view(agent)

    async def dispatch(
        self,
        tenant_id: str,
        zone: str,
        *,
        engine: str,
        datasets: list[str] | None = None,
        by: str | None = None,
    ) -> dict[str, Any]:
        """Queue the active controls on *datasets* (all, if None) for *zone*.

        Compiled here, by the server, for *engine*: an agent executes a query it
        was given and never compiles its own. A control already queued or
        claimed for the zone and engine is not queued twice.
        """
        zone, engine = zone.strip(), engine.strip()
        if not zone or not engine:
            raise ValidationError(
                "dispatch needs a zone and an engine",
                remedy="Name the zone whose agents run the work, and the engine they query.",
            )
        now = _iso(self._clock.now())
        await self._uow.fleet.release_expired(tenant_id, now=now)
        wanted = {d.strip() for d in datasets or () if d.strip()}
        live = await self._uow.controls.live(tenant_id)
        if datasets is not None:
            live = [c for c in live if str(c.dataset) in wanted]
        agents = [
            a
            for a in await self._uow.fleet.agents(tenant_id)
            if a.zone == zone and a.state == "active"
        ]

        queued: list[dict[str, Any]] = []
        already: list[dict[str, Any]] = []
        unassignable: list[dict[str, Any]] = []
        for version in live:
            control_id = str(version.control_id)
            existing = await self._uow.fleet.open_for(tenant_id, zone, control_id, engine)
            if existing:
                already.append(_assignment_view(existing[0]))
                continue
            await self._uow.fleet.discard_unassignable(tenant_id, zone, control_id, engine)
            try:
                plan = _plan(str(version.pql))
                assignment = assignment_for(plan, engine, control_id=control_id)
            except Exception as exc:  # a control that will not compile is a finding
                reasons = [f"could not be compiled for {engine}: {exc}"]
                row = await self._uow.fleet.queue(
                    tenant_id,
                    zone=zone,
                    control_id=control_id,
                    control_version=int(version.version),
                    plan_id="",
                    dataset=str(version.dataset),
                    engine=engine,
                    pql=str(version.pql),
                    assignment={},
                    queued_at=now,
                    queued_by=by,
                    state="unassignable",
                    reasons=reasons,
                )
                unassignable.append(
                    {
                        **Unassignable(
                            plan_id="",
                            dataset=str(version.dataset),
                            zone=zone,
                            reasons=tuple(reasons),
                        ).to_dict(),
                        "control_id": control_id,
                        "assignment_id": row.id,
                        "queued": False,
                    }
                )
                continue
            row = await self._uow.fleet.queue(
                tenant_id,
                zone=zone,
                control_id=control_id,
                control_version=int(version.version),
                plan_id=plan.plan_id,
                dataset=plan.scope.dataset,
                engine=engine,
                pql=str(version.pql),
                assignment=assignment.to_dict(),
                queued_at=now,
                queued_by=by,
            )
            queued.append(_assignment_view(row))
            hole = _no_agent_fits(plan, engine, zone, agents)
            if hole is not None:
                # Queued all the same: an agent that can run it may enrol or
                # upgrade. Said now, so the hole is not discovered by its silence.
                unassignable.append(
                    {
                        **hole.to_dict(),
                        "control_id": control_id,
                        "assignment_id": row.id,
                        "queued": True,
                    }
                )
        return {
            "zone": zone,
            "engine": engine,
            "queued": queued,
            "already_queued": already,
            "unassignable": unassignable,
        }

    async def health(self, tenant_id: str) -> dict[str, Any]:
        """Which agents are talking, what is waiting, and what cannot run.

        Read-only: an expired claim is counted as expired here and returned to
        the queue by the next call that hands out or dispatches work.
        """
        now = self._clock.now()
        agents = await self._uow.fleet.agents(tenant_id)
        horizon = now - timedelta(minutes=self._settings.stale_minutes)
        stale = [
            agent_view(a)
            for a in agents
            if a.state == "active" and ((_parse(a.last_seen_at) or horizon) <= horizon)
        ]
        # Every zone with an agent in it or work for it, so an idle zone reads
        # as zero rather than being absent.
        zones: dict[str, dict[str, int]] = {
            zone: _zone_counts() for zone in sorted({a.zone for a in agents})
        }
        unassignable: list[dict[str, Any]] = []
        plans: dict[str, Any] = {}
        for row in await self._uow.fleet.work(tenant_id):
            counts = zones.setdefault(row.zone, _zone_counts())
            if row.state == "unassignable":
                counts["unassignable"] += 1
                unassignable.append(_assignment_view(row))
                continue
            if row.state == "claimed":
                lease = _parse(row.lease_until)
                counts["expired_claims" if lease is not None and lease < now else "claimed"] += 1
                continue
            counts["queued"] += 1
            if row.pql not in plans:
                try:
                    plans[row.pql] = _plan(row.pql)
                except Exception:  # dispatched once, so it compiled then
                    plans[row.pql] = None
            in_zone = [a for a in agents if a.zone == row.zone and a.state == "active"]
            plan = plans[row.pql]
            hole = (
                _no_agent_fits(plan, row.engine, row.zone, in_zone)
                if plan is not None
                else Unassignable(
                    plan_id=row.plan_id,
                    dataset=row.dataset,
                    zone=row.zone,
                    reasons=("the control no longer lowers to a plan",),
                )
            )
            if hole is not None:
                counts["unassignable"] += 1
                unassignable.append({**_assignment_view(row), "reasons": list(hole.reasons)})

        gaps = [
            {
                "agent_id": g.agent_id,
                "first_sequence": g.first_sequence,
                "last_sequence": g.last_sequence,
                "count": g.last_sequence - g.first_sequence + 1,
                "dropped_at": g.dropped_at,
                "reason": g.reason,
                "reported_at": g.reported_at,
            }
            for g in await self._uow.fleet.gaps(tenant_id)
        ]
        by_state = {
            state: sum(1 for a in agents if a.state == state)
            for state in ("active", "suspended", "revoked")
        }
        parts = [f"{len(agents)} agent(s)"]
        if stale:
            parts.append(
                f"{len(stale)} silent for more than {self._settings.stale_minutes} minutes"
            )
        if unassignable:
            parts.append(f"{len(unassignable)} assignment(s) nothing in their zone can run")
        if gaps:
            parts.append(f"{sum(g['count'] for g in gaps)} finding(s) lost in reported gaps")
        return {
            "agents": len(agents),
            **by_state,
            "stale": stale,
            "stale_after_minutes": self._settings.stale_minutes,
            "zones": zones,
            "unassignable": unassignable,
            "gaps": gaps,
            "summary": ", ".join(parts) + ".",
        }

    # -- the agent's side --------------------------------------------------

    async def enrol(
        self, token: str, *, name: str, version: str, capabilities: dict[str, Any]
    ) -> dict[str, Any]:
        """Redeem *token* for an agent identity and its key, shown once."""
        row = await self._uow.fleet.token_by_digest(_digest(token.strip()))
        now = self._clock.now()
        if row is None:
            raise UnauthorisedError(
                "that enrolment token is not one this server issued",
                remedy="Ask an administrator for a new token (POST /fleet/tokens).",
            )
        if row.redeemed_at is not None:
            raise UnauthorisedError(
                "that enrolment token has already been used",
                remedy=(
                    "Ask for a new token. A token is redeemed once, because a replayable "
                    "one is a credential that never expires."
                ),
                context={"zone": row.zone},
            )
        expires = _parse(row.expires_at)
        if expires is None or now >= expires:
            raise UnauthorisedError(
                f"that enrolment token expired at {row.expires_at}",
                remedy="Ask for a new token, and enrol soon after it is issued.",
                context={"zone": row.zone},
            )
        declared = AgentCapabilities.from_dict(dict(capabilities or {})).to_dict()
        tenant_id = row.tenant_id
        agent = await self._uow.fleet.create_agent(
            tenant_id,
            name=(name or row.name or f"{row.zone} agent").strip()[:128],
            zone=row.zone,
            version=(version or "")[:64],
            capabilities=declared,
            enrolled_at=_iso(now),
        )
        if not await self._uow.fleet.redeem(tenant_id, row, agent=agent, now=_iso(now)):
            # Somebody redeemed it between the read and this update. Raising
            # rolls back the agent created above with it.
            raise UnauthorisedError(
                "that enrolment token has already been used",
                remedy="Ask for a new token.",
                context={"zone": row.zone},
            )
        key = derive_key(self._settings.secret, tenant_id, agent.id)
        _log.info("agent %s enrolled into zone %s", agent.id, agent.zone)
        return {
            "agent_id": agent.id,
            "key": key.hex(),
            "zone": agent.zone,
            "name": agent.name,
            "poll_after_seconds": self._settings.poll_seconds,
        }

    async def hello(
        self, body: dict[str, Any], *, agent_header: str | None, signature: str | None
    ) -> dict[str, Any]:
        """An agent announcing itself; answered with the work it should take."""
        try:
            message = Hello.from_dict(body)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                f"that is not a Hello message: {exc}",
                remedy="Send the Hello message as its to_dict() gives it, whole.",
            ) from exc
        agent, refusal = await self._authenticate(
            message.agent_id, agent_header, message.signable(), signature
        )
        if refusal is not None:
            return refusal.to_dict()
        tenant_id = agent.tenant_id
        now = self._clock.now()
        await self._uow.fleet.release_expired(tenant_id, now=_iso(now))
        await self._uow.fleet.seen(
            tenant_id,
            agent,
            now=_iso(now),
            version=message.version[:64],
            capabilities=message.capabilities.to_dict(),
            pending_findings=max(0, message.pending_findings),
        )
        slots = max(0, min(message.free_slots, message.capabilities.max_concurrency))
        lease_until = _iso(now + timedelta(seconds=self._settings.lease_seconds))
        taken: list[Assignment] = []
        cannot: list[dict[str, Any]] = []
        plans: dict[str, Any] = {}
        for row in await self._uow.fleet.queued(tenant_id, agent.zone):
            if len(taken) >= slots:
                break
            if row.pql not in plans:
                try:
                    plans[row.pql] = _plan(row.pql)
                except Exception as exc:  # it compiled at dispatch; say what changed
                    plans[row.pql] = exc
            plan = plans[row.pql]
            if isinstance(plan, Exception):
                cannot.append(
                    Unassignable(
                        plan_id=row.plan_id,
                        dataset=row.dataset,
                        zone=row.zone,
                        reasons=(f"the control no longer lowers to a plan: {plan}",),
                    ).to_dict()
                )
                continue
            fitness = fits(plan, message.capabilities, engine=row.engine)
            if not fitness.assignable:
                # Left queued for an agent that can run it, and said here so
                # this agent's operator sees the hole their zone has.
                cannot.append(
                    Unassignable(
                        plan_id=row.plan_id,
                        dataset=row.dataset,
                        zone=row.zone,
                        reasons=fitness.reasons,
                        remedy=fitness.remedy,
                    ).to_dict()
                )
                continue
            if await self._uow.fleet.claim(
                tenant_id, row, agent_id=agent.id, now=_iso(now), lease_until=lease_until
            ):
                taken.append(Assignment.from_dict(dict(row.assignment_json)))
        return Receipt(
            accepted_through=agent.last_sequence,
            assignments=tuple(taken),
            unassignable=tuple(cannot),
            poll_after_seconds=self._settings.poll_seconds,
        ).to_dict()

    async def report(
        self, body: dict[str, Any], *, agent_header: str | None, signature: str | None
    ) -> dict[str, Any]:
        """Findings arriving from an agent, deduplicated and put in the ledger."""
        try:
            message = Report.from_dict(body)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                f"that is not a Report message: {exc}",
                remedy="Send the Report message as its to_dict() gives it, whole.",
            ) from exc
        agent, refusal = await self._authenticate(
            message.agent_id, agent_header, message.signable(), signature
        )
        if refusal is not None:
            return refusal.to_dict()
        tenant_id = agent.tenant_id
        now = _iso(self._clock.now())

        highest = agent.last_sequence
        duplicates = 0
        rejected: list[tuple[int, str]] = []
        for record in message.records:
            if record.sequence <= highest:
                # Already have it: after a lost acknowledgement, the ordinary case.
                duplicates += 1
                continue
            if record.sequence != highest + 1 and highest >= 0:
                # A hole, named; the record is still kept, because refusing it
                # would lose evidence that did arrive to punish evidence that
                # did not. The same rule as prama.agent.coordinator.
                rejected.append(
                    (
                        record.sequence,
                        f"expected sequence {highest + 1}; {record.sequence - highest - 1} "
                        f"finding(s) from this agent are missing",
                    )
                )
            highest = record.sequence
            rows = await self._uow.fleet.for_plan(tenant_id, agent.zone, record.plan_id)
            if not rows:
                rejected.append(
                    (
                        record.sequence,
                        f"not recorded: plan {record.plan_id or '(none)'} was never assigned "
                        f"to zone {agent.zone}",
                    )
                )
                continue
            target = next(
                (r for r in rows if r.state == "claimed" and r.claimed_by == agent.id),
                next((r for r in rows if r.state == "queued"), None),
            )
            named = target or rows[-1]
            linked = await self._uow.evidence.append(
                dataclasses.replace(
                    record,
                    # What the server knows, not what the message says: the
                    # control this plan was dispatched for, and who sent it.
                    control_id=named.control_id,
                    control_version=named.control_version,
                    triggered_by=f"agent:{agent.id}",
                    tenant_id=tenant_id,
                ),
                tenant_id=tenant_id,
            )
            self.reported.append(linked)
            if target is not None:
                await self._uow.fleet.mark_done(
                    tenant_id, target, now=now, evidence_sequence=linked.sequence
                )

        for gap in message.gaps:
            if await self._uow.fleet.record_gap(
                tenant_id,
                agent_id=agent.id,
                first_sequence=gap.first_sequence,
                last_sequence=gap.last_sequence,
                dropped_at=_iso(gap.dropped_at)
                if gap.dropped_at.tzinfo
                else gap.dropped_at.isoformat(timespec="milliseconds"),
                reason=gap.reason,
                reported_at=now,
            ):
                _log.warning("agent %s reported a gap: %s", agent.id, gap.render())

        await self._uow.fleet.seen(tenant_id, agent, now=now, last_sequence=highest)
        return Receipt(
            accepted_through=highest,
            duplicates=duplicates,
            rejected=tuple(rejected),
            poll_after_seconds=self._settings.poll_seconds,
        ).to_dict()

    # -- internals ---------------------------------------------------------

    async def _require(self, tenant_id: str, agent_id: str) -> Any:
        agent = await self._uow.fleet.agent(tenant_id, agent_id)
        if agent is None:
            raise NotFoundError(
                f"no agent {agent_id!r} is enrolled in this estate",
                remedy="List the fleet (GET /fleet/agents) for the agents there are.",
                context={"agent_id": agent_id},
            )
        return agent

    async def _authenticate(
        self, agent_id: str, header: str | None, payload: str, signature: str | None
    ) -> tuple[Any, Refusal | None]:
        if header is not None and header != agent_id:
            return None, Refusal(
                reason="the X-Prama-Agent header names a different agent than the message",
                remedy="Send the agent's own id in both.",
            )
        agent = await self._uow.fleet.agent_for_message(agent_id)
        if agent is None:
            return None, Refusal(
                reason="this server does not know that agent",
                remedy="Enrol the agent again with a fresh token.",
            )
        if agent.state == "revoked":
            return None, Refusal(
                reason="this agent has been revoked",
                remedy=(
                    "Stop the agent. If it should be running, enrol it again; a revoked "
                    "identity is not reinstated."
                ),
                permanent=True,
            )
        if agent.state == "suspended":
            # Before the signature check, as in the coordinator: otherwise a
            # suspended agent's operator is told their key is wrong.
            return None, Refusal(
                reason="this agent is suspended",
                remedy=(
                    "Resume it when whatever caused the suspension is resolved. Keep it "
                    "running meanwhile: it will spool its findings and deliver them."
                ),
                permanent=False,
            )
        key = derive_key(self._settings.secret, agent.tenant_id, agent.id)
        if not signature or not verify_payload(key, payload, signature):
            return None, Refusal(
                reason="the message was not signed by that agent's key",
                remedy="Check the agent's key, or enrol the agent again.",
            )
        return agent, None


def _zone_counts() -> dict[str, int]:
    return {"queued": 0, "claimed": 0, "expired_claims": 0, "unassignable": 0}


def _no_agent_fits(plan: Any, engine: str, zone: str, agents: list[Any]) -> Unassignable | None:
    """Why nothing active in *zone* can run *plan*, or None when something can."""
    if not agents:
        return Unassignable(
            plan_id=plan.plan_id,
            dataset=plan.scope.dataset,
            zone=zone,
            reasons=(f"no active agent is enrolled in {zone}",),
            remedy="Enrol an agent in the zone, or resume a suspended one.",
        )
    reasons: list[str] = []
    remedies: list[str] = []
    for agent in agents:
        fitness = fits(
            plan, AgentCapabilities.from_dict(dict(agent.capabilities_json or {})), engine=engine
        )
        if fitness.assignable:
            return None
        reasons += [f"{agent.name}: {r}" for r in fitness.reasons]
        if fitness.remedy and fitness.remedy not in remedies:
            remedies.append(fitness.remedy)
    return Unassignable(
        plan_id=plan.plan_id,
        dataset=plan.scope.dataset,
        zone=zone,
        reasons=tuple(reasons),
        remedy="; ".join(remedies),
    )
