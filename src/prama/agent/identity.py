"""Who an agent is, and what it may be trusted with.

An agent runs on somebody else's machine, inside a network the control plane
cannot see into, holding credentials to a production database. The control
plane has to answer three questions about it and cannot answer any of them by
assumption.

**Which agent is this?** Every agent has an identity issued at enrolment, and
every finding it sends is signed. Without that, a control plane accepts
evidence from anything that can reach it, and the audit trail becomes an
assertion that somebody sent something.

**Is it still trusted?** Identities are revocable, and a revoked agent's later
findings are rejected rather than quietly kept. Revocation without rejection is
a list nobody enforces.

**What is it for?** An agent is enrolled into a zone and is assigned work for
that zone only. A compromised agent in the reporting zone must not be able to
ask for the trading estate's controls, and it cannot, because assignment is by
zone rather than by request.

Enrolment is one-time-use: a token issued by somebody with authority, redeemed
once for a credential. A token that could be replayed is a credential that
never expires, handed out over whatever channel somebody used to install the
agent.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.core.errors import ValidationError
from prama.secrets import SecretValue

#: How long an enrolment token is good for. Short, because it is carried by
#: hand or by a deployment tool and its whole purpose is to be used once
#: shortly after being issued.
ENROLMENT_MINUTES = 60


class AgentState(enum.Enum):
    ENROLLING = "enrolling"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"

    @property
    def may_report(self) -> bool:
        """Whether findings from an agent in this state are accepted.

        A suspended agent may still be running and buffering; its findings are
        held rather than discarded, because the reason for suspension is
        usually operational and losing a day of evidence to it would be a
        second problem. A revoked agent's are rejected outright.
        """
        return self is AgentState.ACTIVE

    @property
    def may_be_assigned(self) -> bool:
        return self is AgentState.ACTIVE


@dataclasses.dataclass(frozen=True, slots=True)
class EnrolmentToken:
    """A one-time invitation to become an agent."""

    token_id: str
    #: The zone the agent will belong to. Fixed at issue, not chosen by the
    #: agent: an agent that named its own zone could name the one with the
    #: interesting data.
    zone: str
    issued_at: datetime
    expires_at: datetime
    issued_by: str = ""
    #: Set when redeemed, so a second attempt is refused rather than issuing a
    #: second credential.
    redeemed_at: datetime | None = None

    def is_valid_at(self, moment: datetime) -> bool:
        return self.redeemed_at is None and moment < self.expires_at

    def why_invalid(self, moment: datetime) -> str:
        if self.redeemed_at is not None:
            return (
                f"this token was already redeemed at "
                f"{self.redeemed_at.isoformat(timespec='seconds')}"
            )
        if moment >= self.expires_at:
            return f"this token expired at {self.expires_at.isoformat(timespec='seconds')}"
        return ""


@dataclasses.dataclass(frozen=True, slots=True)
class AgentIdentity:
    """An enrolled agent, as the control plane knows it."""

    agent_id: str
    zone: str
    #: A digest of the agent's key, never the key. The control plane can verify
    #: a signature without being able to produce one, so a stolen copy of the
    #: registry cannot be used to forge findings.
    key_digest: str
    name: str = ""
    state: AgentState = AgentState.ACTIVE
    enrolled_at: datetime | None = None
    last_seen_at: datetime | None = None
    #: The agent's own version, so the control plane can reason about skew
    #: rather than discovering it through a failure.
    version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "zone": self.zone,
            "state": self.state.value,
            "version": self.version,
            "enrolled_at": self.enrolled_at.isoformat() if self.enrolled_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }

    def is_stale(self, moment: datetime, *, after_minutes: int = 15) -> bool:
        """Whether this agent has stopped calling home.

        Reported rather than inferred from missing evidence: an agent that has
        died and an agent whose datasets are all clean produce the same silence,
        and only one of them is a problem.
        """
        if self.last_seen_at is None:
            return True
        return moment - self.last_seen_at > timedelta(minutes=after_minutes)


class AgentRegistry:
    """The control plane's record of its agents."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._tokens: dict[str, EnrolmentToken] = {}
        self._agents: dict[str, AgentIdentity] = {}
        self._keys: dict[str, bytes] = {}

    # -- enrolment ---------------------------------------------------------

    def issue_token(
        self, zone: str, *, issued_by: str = "", minutes: int = ENROLMENT_MINUTES
    ) -> tuple[EnrolmentToken, SecretValue]:
        """Invite one agent into one zone.

        Returns the record and the secret separately: the secret is shown once,
        to the person installing the agent, and the control plane keeps only
        its digest. A registry that could reproduce the token would be a
        registry whose theft is an agent fleet.
        """
        if not zone:
            raise ValidationError(
                "an enrolment token needs a zone",
                remedy=(
                    "Name the zone the agent will belong to. Assignment is by zone, so "
                    "an agent without one could be given any dataset's work."
                ),
            )
        secret = secrets.token_urlsafe(32)
        now = self._clock.now()
        token = EnrolmentToken(
            token_id=_digest(secret),
            zone=zone,
            issued_at=now,
            expires_at=now + timedelta(minutes=minutes),
            issued_by=issued_by,
        )
        self._tokens[token.token_id] = token
        return token, SecretValue(secret, origin=f"enrolment:{zone}")

    def enrol(
        self, token_secret: str, *, name: str = "", version: str = ""
    ) -> tuple[AgentIdentity, SecretValue]:
        """Redeem a token for an agent identity and a signing key."""
        token = self._tokens.get(_digest(token_secret))
        now = self._clock.now()
        if token is None:
            raise ValidationError(
                "that enrolment token is not one this control plane issued",
                remedy="Ask whoever administers Prama for a new token.",
            )
        if not token.is_valid_at(now):
            raise ValidationError(
                f"that enrolment token cannot be used: {token.why_invalid(now)}",
                remedy=(
                    "Ask for a new token. Tokens are one-time and short-lived because a "
                    "replayable one is a credential that never expires, handed out over "
                    "whatever channel installed the agent."
                ),
                context={"zone": token.zone},
            )
        self._tokens[token.token_id] = dataclasses.replace(token, redeemed_at=now)

        key = secrets.token_bytes(32)
        agent = AgentIdentity(
            agent_id=f"agent:{secrets.token_hex(8)}",
            zone=token.zone,
            key_digest=_digest(key.hex()),
            name=name or f"{token.zone} agent",
            state=AgentState.ACTIVE,
            enrolled_at=now,
            last_seen_at=now,
            version=version,
        )
        self._agents[agent.agent_id] = agent
        self._keys[agent.agent_id] = key
        return agent, SecretValue(key.hex(), origin=f"agent:{agent.agent_id}")

    # -- the fleet ---------------------------------------------------------

    def get(self, agent_id: str) -> AgentIdentity | None:
        return self._agents.get(agent_id)

    def in_zone(self, zone: str) -> list[AgentIdentity]:
        return [a for a in self._agents.values() if a.zone == zone and a.state.may_be_assigned]

    def all(self) -> list[AgentIdentity]:
        return list(self._agents.values())

    def seen(self, agent_id: str) -> AgentIdentity | None:
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        updated = dataclasses.replace(agent, last_seen_at=self._clock.now())
        self._agents[agent_id] = updated
        return updated

    def suspend(self, agent_id: str) -> AgentIdentity | None:
        return self._set_state(agent_id, AgentState.SUSPENDED)

    def resume(self, agent_id: str) -> AgentIdentity | None:
        return self._set_state(agent_id, AgentState.ACTIVE)

    def revoke(self, agent_id: str) -> AgentIdentity | None:
        """Stop trusting an agent. Its key is destroyed here as well.

        Keeping the key of a revoked agent would leave the registry able to
        verify findings it has decided not to accept, which is a state nobody
        can reason about.
        """
        self._keys.pop(agent_id, None)
        return self._set_state(agent_id, AgentState.REVOKED)

    def stale(self, *, after_minutes: int = 15) -> list[AgentIdentity]:
        now = self._clock.now()
        return [
            a
            for a in self._agents.values()
            if a.state is AgentState.ACTIVE and a.is_stale(now, after_minutes=after_minutes)
        ]

    # -- authenticity ------------------------------------------------------

    def sign_as(self, agent_id: str, payload: str) -> str:
        """Sign on an agent's behalf. For tests and for the agent's own use."""
        key = self._keys.get(agent_id)
        if key is None:
            raise ValidationError(
                f"no signing key is held for {agent_id}",
                remedy="The agent is not enrolled, or has been revoked.",
                context={"agent_id": agent_id},
            )
        return sign_payload(key, payload)

    def verify(self, agent_id: str, payload: str, signature: str) -> bool:
        """Whether this payload came from this agent, and whether it counts.

        A revoked agent fails here even with a correct signature. Verifying the
        signature and then accepting the finding anyway is the commonest way a
        revocation list becomes decorative.
        """
        agent = self._agents.get(agent_id)
        if agent is None or not agent.state.may_report:
            return False
        key = self._keys.get(agent_id)
        if key is None:
            return False
        return hmac.compare_digest(sign_payload(key, payload), signature)

    def _set_state(self, agent_id: str, state: AgentState) -> AgentIdentity | None:
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        updated = dataclasses.replace(agent, state=state)
        self._agents[agent_id] = updated
        return updated


def sign_payload(key: bytes, payload: str) -> str:
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
