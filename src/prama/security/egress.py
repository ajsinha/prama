"""Every place data leaves, and the one gate they all pass through.

:mod:`prama.security.residency` decides whether a movement is allowed. This
decides *where the question gets asked*, which is the part that goes wrong: a
policy engine nothing calls is a policy engine that permits everything, and it
fails silently, which is the worst way for a control to fail.

Two ideas.

**Egress points are enumerated, not discovered at the call site.** Each one is
registered here with what it sends and where the destination comes from. The
registry is the thing a security reviewer reads when asked "what leaves this
system?", and it is short enough to read.

**A registered point that does not consult the gate is a build failure.**
``tests/architecture/test_egress.py`` parses the source of every registered
module and requires it to reach the gate. That is the only form of this control
that survives a year of changes: an assertion in a review document does not, and
a hand-audit is a hand-audit.

The gate refuses by raising. A caller that gets a :class:`Decision` back can
ignore it, and the one call site where somebody forgets is the one that
matters — so :func:`Gate.require` is the normal way in, and returning a decision
is reserved for reporting.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Final

from prama.core.errors import PramaError
from prama.security.residency import Decision, Policy

__all__ = [
    "EGRESS_POINTS",
    "EgressPoint",
    "Gate",
    "ResidencyRefused",
    "point",
]


class ResidencyRefused(PramaError):
    """A movement the tenant's residency rule does not allow.

    Its own type, not a generic ValidationError: an operator triaging a failed
    export needs to tell "the data may not go there" from "the request was
    malformed", and a log line is not the place to be guessing.
    """

    code = "RESIDENCY.REFUSED"


@dataclasses.dataclass(frozen=True, slots=True)
class EgressPoint:
    """One place data leaves Prama."""

    name: str
    #: The module that performs the movement. Checked against the source.
    module: str
    #: What leaves, in the words somebody reviewing this would use.
    what: str
    #: Where the destination comes from — configuration, a target's own
    #: address, a caller's argument. Reviewers ask this second.
    destination_from: str
    #: What the data's jurisdiction is taken from. The common defect is an
    #: egress that knows its destination and not its subject's home.
    jurisdiction_from: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "module": self.module,
            "what": self.what,
            "destination_from": self.destination_from,
            "jurisdiction_from": self.jurisdiction_from,
        }


EGRESS_POINTS: Final[tuple[EgressPoint, ...]] = (
    EgressPoint(
        name="model-inference",
        module="prama.llm.providers",
        what="prompts, which carry column names, samples and business language",
        destination_from="the provider's configured region",
        jurisdiction_from="the tenant's declared residency and the dataset's jurisdiction",
    ),
    EgressPoint(
        name="catalog-write-back",
        module="prama.integrate.catalog",
        what="quality badges: standing, coverage, and an evidence reference",
        destination_from="the target's declared region",
        jurisdiction_from="the badge's dataset jurisdiction",
    ),
    EgressPoint(
        name="siem-export",
        module="prama.security.siem",
        what="audit events: who did what to which tenant's estate",
        destination_from="the collector's configured region",
        jurisdiction_from="the tenant's declared residency",
    ),
    EgressPoint(
        name="telemetry-export",
        module="prama.telemetry.otlp",
        what=(
            "Prama's own trace spans to an OpenTelemetry collector: span names, durations, "
            "control ids, dataset names and verdicts; no row of data"
        ),
        destination_from="the collector's configured region",
        jurisdiction_from="the operator's declared residency",
    ),
    EgressPoint(
        name="lineage-export",
        module="prama.telemetry.openlineage_http",
        what="OpenLineage run events: dataset names and whether each assertion held",
        destination_from="the collector's configured region",
        jurisdiction_from="the operator's declared residency",
    ),
    EgressPoint(
        name="evidence-anchor",
        module="prama.evidence.anchor",
        what=(
            "a SHA-256 digest of the evidence chain head, to a time-stamp authority: "
            "32 bytes naming no record, no dataset and no tenant"
        ),
        destination_from="the time-stamp authority's configured region",
        jurisdiction_from="the tenant's declared residency",
    ),
    EgressPoint(
        name="evidence-export",
        module="prama.evidence.retention",
        what="the evidence ledger for a period, including sample digests",
        destination_from="the archive's configured region",
        jurisdiction_from="the tenant's declared residency",
    ),
    EgressPoint(
        name="secret-fetch",
        module="prama.secrets.vault",
        what=(
            "an authenticated read against the secret store. The credential "
            "comes back, so the store's region is where a credential is held"
        ),
        destination_from="the configured Vault address's region",
        jurisdiction_from=(
            "the same region: a credential belongs wherever its store is, and "
            "there is no separate subject to ask"
        ),
    ),
    EgressPoint(
        name="source-read",
        module="prama.connect.sources.rest",
        what=(
            "a credential, and any query parameters the read carries. Reading is "
            "mostly an ingress, but the token genuinely leaves and the source's "
            "region is where the tenant's data is sitting"
        ),
        destination_from="the configured base URL's region",
        jurisdiction_from="the dataset's declared jurisdiction",
    ),
    EgressPoint(
        name="alert-delivery",
        module="prama.alert.route",
        what="alert bodies, which quote failing values",
        destination_from="the channel's configured region",
        jurisdiction_from="the alerting dataset's jurisdiction",
    ),
)


def point(name: str) -> EgressPoint:
    for entry in EGRESS_POINTS:
        if entry.name == name:
            return entry
    from prama.core.errors import ValidationError

    raise ValidationError(
        f"no such egress point: {name!r}",
        remedy=(
            "Register it in prama.security.egress.EGRESS_POINTS. An egress "
            "the registry does not name is an egress nobody reviews. "
            f"Known: {', '.join(p.name for p in EGRESS_POINTS)}."
        ),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class Gate:
    """The residency check, at the point of departure."""

    policy: Policy
    tenant_id: str = ""

    @classmethod
    def for_tenant(cls, residency: str | None, tenant_id: str = "") -> Gate:
        return cls(policy=Policy.of(residency), tenant_id=tenant_id)

    def decide(
        self,
        egress: str,
        *,
        destination: str,
        jurisdiction: str = "",
        subject: str = "",
    ) -> Decision:
        """The decision, for a report. Does not enforce — see :meth:`require`."""
        # Resolving the name here rather than accepting a free string: a typo
        # would otherwise be an egress point that quietly checks nothing.
        known = point(egress)
        return self.policy.decide(
            destination=destination,
            jurisdiction=jurisdiction,
            subject=subject or known.name,
        )

    def require(
        self,
        egress: str,
        *,
        destination: str,
        jurisdiction: str = "",
        subject: str = "",
    ) -> Decision:
        """Check, and raise if the movement may not happen.

        Raising rather than returning, because a returned decision can be
        ignored and the call site where somebody forgets is the one that
        matters.
        """
        decision = self.decide(
            egress, destination=destination, jurisdiction=jurisdiction, subject=subject
        )
        if not decision.may_proceed:
            raise ResidencyRefused(
                decision.describe(),
                remedy=_remedy_for(decision),
                context={
                    "egress": egress,
                    "tenant": self.tenant_id,
                    "destination": decision.destination,
                    "jurisdiction": decision.jurisdiction or "(undeclared)",
                },
            )
        return decision


def _remedy_for(decision: Decision) -> str:
    """What to actually do, which differs by why it was refused."""
    if decision.is_undeclared:
        return (
            "Declare the jurisdiction this data belongs to. Undeclared is not "
            "unrestricted: treating it as unrestricted is how the one table "
            "nobody got round to declaring is the one that leaves the region."
        )
    if decision.destination_unstated:
        return (
            "State the destination. A movement with no destination cannot be "
            "checked, and a check that cannot be made is a refusal."
        )
    return (
        "Send this to a destination inside the tenant's residency, or change "
        "the tenant's residency rule if the obligation has changed."
    )
