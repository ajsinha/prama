"""SOC 2 readiness: which Trust Services Criteria the product itself evidences.

Not the bank's SOC 2 — Prama's own. An auditor examining a control plane asks
what *it* does about access, change and monitoring, and the answer has to be a
list of mechanisms that exist rather than a policy document describing intent.

**Readiness is not compliance, and the difference is stated everywhere here.** A
criterion with a mechanism is *evidenceable*: there is something to show an
auditor. Whether the organisation operates it consistently over an observation
window is a Type II question that no code can answer, and a module claiming
otherwise would be helping somebody mislead an auditor.

So each criterion carries three separate things:

* the **mechanism** in the product, named so it can be pointed at;
* whether it is **evidenceable today**, or a gap;
* what an auditor would actually **ask for**, so a gap is actionable rather than
  a red cell in a spreadsheet.

A criterion Prama does not address is listed as unaddressed. A readiness matrix
showing only what is covered is a matrix whose gaps are invisible, and the gaps
are the reason anybody reads it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any


class Readiness(enum.Enum):
    """How far the product itself gets toward evidencing a criterion."""

    #: A mechanism exists and produces evidence an auditor can examine.
    EVIDENCEABLE = "evidenceable"
    #: A mechanism exists and its evidence is incomplete or manual.
    PARTIAL = "partial"
    #: Nothing in the product addresses this; it is organisational.
    ORGANISATIONAL = "organisational"
    #: Prama should address this and does not. A gap in the product.
    GAP = "gap"

    @property
    def needs_work_in_the_product(self) -> bool:
        return self in (Readiness.PARTIAL, Readiness.GAP)

    @property
    def label(self) -> str:
        return {
            Readiness.EVIDENCEABLE: "a mechanism exists and produces evidence",
            Readiness.PARTIAL: "a mechanism exists; its evidence is incomplete",
            Readiness.ORGANISATIONAL: "not a product control — policy and operation",
            Readiness.GAP: "Prama should address this and does not",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Criterion:
    """One Trust Services Criterion, and what the product does about it."""

    identity: str
    category: str
    statement: str
    readiness: Readiness
    #: The thing in the product. Named so an auditor can be shown it, not
    #: described so a reader can imagine it.
    mechanism: str = ""
    #: What an auditor asks for. Present even for a gap, because a gap without
    #: this is a red cell rather than a piece of work.
    evidence_request: str = ""
    note: str = ""

    def describe(self) -> str:
        head = f"{self.identity} ({self.category}): {self.readiness.label}"
        if self.mechanism:
            head += f" — {self.mechanism}"
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "category": self.category,
            "statement": self.statement,
            "readiness": self.readiness.value,
            "readiness_label": self.readiness.label,
            "mechanism": self.mechanism,
            "evidence_request": self.evidence_request,
            "note": self.note,
            "message": self.describe(),
        }


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        identity="CC6.1",
        category="Logical access",
        statement="Access to data and systems is restricted to authorised users.",
        readiness=Readiness.EVIDENCEABLE,
        mechanism=(
            "Local authentication with PBKDF2, per-password salt and rehash on "
            "sign-in; roles carrying permissions with one-level wildcards; every "
            "tenant-scoped read proved isolated by a signature-scanning test suite"
        ),
        evidence_request=(
            "A user list with roles, the permission each role carries, and the "
            "cross-tenant isolation test output"
        ),
    ),
    Criterion(
        identity="CC6.2",
        category="Logical access",
        statement="New credentials are issued only on authorisation, and removed on exit.",
        readiness=Readiness.PARTIAL,
        mechanism="`prama principal create` and a `disabled` status that refuses sign-in",
        evidence_request="A joiner/leaver record reconciled against the principal list",
        note=(
            "Partial deliberately: the product records the account, and nothing in "
            "it evidences the *authorisation* to create one. SCIM (W10.3) is what "
            "would close this, and claiming it closed today would be the kind of "
            "overstatement an auditor is looking for."
        ),
    ),
    Criterion(
        identity="CC6.6",
        category="Logical access",
        statement="Transmission and storage of sensitive data is protected.",
        readiness=Readiness.PARTIAL,
        mechanism=(
            "Session secrets are refused when empty and never in a tracked file; "
            "residency policy refuses movement out of a declared jurisdiction; "
            "evidence samples expire on their own clock, separately from records"
        ),
        evidence_request="The residency policy, and the sample retention configuration",
        note=(
            "Customer-managed keys (W10.3) are not built, so encryption at rest is "
            "whatever the deployment's storage provides — which is a real answer "
            "and not the one a bank wants."
        ),
    ),
    Criterion(
        identity="CC7.2",
        category="System operations",
        statement="The system is monitored, and anomalies are identified.",
        readiness=Readiness.EVIDENCEABLE,
        mechanism=(
            "The evidence ledger records every control execution; unfinished runs "
            "are surfaced rather than absorbed; SIEM export in ECS and CEF with "
            "severity derived from the event"
        ),
        evidence_request="A SIEM feed sample, and the ledger's verification output",
    ),
    Criterion(
        identity="CC7.3",
        category="System operations",
        statement="Security events are evaluated and responded to.",
        readiness=Readiness.PARTIAL,
        mechanism="Audit events with outcome and actor; incident triage over the ledger",
        evidence_request="An incident record from detection to disposition",
        note=(
            "The product records the event and the disposition. Whether somebody "
            "responded within a stated time is an operational fact it cannot know."
        ),
    ),
    Criterion(
        identity="CC8.1",
        category="Change management",
        statement="Changes are authorised, designed, tested and approved.",
        readiness=Readiness.EVIDENCEABLE,
        mechanism=(
            "Controls are bitemporal and versioned; activation records who approved; "
            "suppression requires an expiry and a reason; rejections are kept so "
            "nothing is re-proposed silently"
        ),
        evidence_request=(
            "A control's version history with its approver, and the suppression log with reasons"
        ),
    ),
    Criterion(
        identity="A1.2",
        category="Availability",
        statement="Recovery and backup support the availability commitment.",
        readiness=Readiness.ORGANISATIONAL,
        mechanism="",
        evidence_request="A restore test against the deployment's own backups",
        note=(
            "Prama has no backup mechanism of its own and should not: its state is "
            "one PostgreSQL database, and a product that backed itself up beside "
            "the operator's backups would produce two recovery points and no "
            "statement about which is authoritative."
        ),
    ),
    Criterion(
        identity="PI1.1",
        category="Processing integrity",
        statement="Processing is complete, valid, accurate, timely and authorised.",
        readiness=Readiness.EVIDENCEABLE,
        mechanism=(
            "Deterministic compilation with a content-addressed plan id; a screen "
            "that cannot establish a pass reports indeterminate rather than passing; "
            "hash-chained evidence with a Merkle root; deterministic replay"
        ),
        evidence_request=(
            "A control replayed from its plan id, giving the recorded verdict, and "
            "the ledger's chain verification"
        ),
    ),
    Criterion(
        identity="C1.1",
        category="Confidentiality",
        statement="Confidential information is identified and protected.",
        readiness=Readiness.PARTIAL,
        mechanism=(
            "Sensitivity on attributes; masked columns named on any sample shown; "
            "SIEM export carries an allow-list so a free-form detail cannot leak"
        ),
        evidence_request="The attribute sensitivity register, and a masked sample",
        note="Automated PII discovery and classification is not built.",
    ),
    Criterion(
        identity="CC6.8",
        category="Logical access",
        statement="Unauthorised or malicious software is prevented or detected.",
        readiness=Readiness.GAP,
        mechanism="",
        evidence_request="An SBOM, a signed image, and a dependency scan on each release",
        note=(
            "A real gap in the product rather than an organisational one. The image "
            "is not signed and no SBOM is produced, and W10.8's signed offline "
            "bundle is where both would land."
        ),
    ),
)


@dataclasses.dataclass(frozen=True, slots=True)
class Readout:
    """The matrix, with the gaps first."""

    criteria: tuple[Criterion, ...] = CRITERIA

    def of(self, readiness: Readiness) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.readiness is readiness)

    @property
    def gaps(self) -> tuple[Criterion, ...]:
        """Criteria needing work *in the product*.

        Organisational ones are excluded deliberately: they are not gaps, they
        are somebody else's control, and mixing them in makes the product look
        worse and the list less actionable.
        """
        return tuple(c for c in self.criteria if c.readiness.needs_work_in_the_product)

    def describe(self) -> str:
        evidenceable = len(self.of(Readiness.EVIDENCEABLE))
        total = len(self.criteria)
        gaps = self.gaps
        if not gaps:
            return f"{evidenceable} of {total} criteria are evidenceable; no product gaps."
        # Gaps first. A readiness matrix leading with what is covered is one
        # whose gaps are read last or not at all.
        return (
            f"{len(gaps)} of {total} criteria need work in the product "
            f"({', '.join(c.identity for c in gaps)}); {evidenceable} are evidenceable."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "criteria": [c.to_dict() for c in self.criteria],
            "evidenceable": len(self.of(Readiness.EVIDENCEABLE)),
            "gaps": [c.identity for c in self.gaps],
            "organisational": [c.identity for c in self.of(Readiness.ORGANISATIONAL)],
            "message": self.describe(),
            "caveat": (
                "Readiness is not compliance. A criterion with a mechanism is one "
                "there is something to show an auditor; whether the organisation "
                "operates it consistently over an observation window is a Type II "
                "question no code can answer."
            ),
        }


def readout() -> Readout:
    return Readout()


__all__ = ["CRITERIA", "Criterion", "Readiness", "Readout", "readout"]
