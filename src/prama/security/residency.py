"""Residency: where data is allowed to be, and what may cross a border.

A tenant declares where its data must stay. A dataset declares the jurisdiction
it belongs to. A connector, a model, a report distribution and an evidence
export each want to move something somewhere. This decides whether they may.

**Refusal is the default and the reason is always stated.** A residency check
that returns a bare False produces an outage nobody can diagnose — the operator
sees a failure, not a policy — so every refusal names the tenant's rule, the
data's jurisdiction, and the destination that broke it.

**Unknown is not permitted.** A dataset with no declared jurisdiction inside a
tenant that has a residency rule is *not* cleared to move: it is undeclared, and
treating undeclared as unrestricted is how the one table nobody got round to
declaring is the one that leaves the region. That is a deliberate cost — it will
block work until somebody declares the thing — and it is the only safe
direction, because the alternative fails silently and permanently.

**A tenant with no rule is not "deny everything".** Most deployments are in one
region and have no residency obligation at all, and a product that refused every
movement until a rule was written would be a product nobody finishes installing.
No rule means no restriction, and the decision says so rather than looking like
an approval.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable
from typing import Any


class Verdict(enum.Enum):
    """Whether a movement may happen, and on what basis."""

    #: The tenant declares no residency rule.
    UNRESTRICTED = "unrestricted"
    #: Permitted by the rule.
    PERMITTED = "permitted"
    #: Refused by the rule.
    REFUSED = "refused"
    #: The data does not say where it belongs, and the tenant has a rule.
    UNDECLARED = "undeclared"

    @property
    def may_proceed(self) -> bool:
        return self in (Verdict.UNRESTRICTED, Verdict.PERMITTED)


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    """One residency decision, with everything needed to argue with it."""

    verdict: Verdict
    destination: str
    #: Where the tenant says its data must stay. Empty when it has no rule.
    rule: tuple[str, ...] = ()
    #: Where the data says it belongs.
    jurisdiction: str = ""
    subject: str = ""

    @property
    def may_proceed(self) -> bool:
        return self.verdict.may_proceed

    @property
    def is_undeclared(self) -> bool:
        """Refused because the data did not say where it belongs.

        A property rather than a comparison a caller makes against the enum:
        the remedy for this refusal is different from every other one — declare
        the jurisdiction, rather than change the destination — and a caller
        that has to reach into the enum to tell them apart usually does not.
        """
        return self.verdict is Verdict.UNDECLARED

    @property
    def destination_unstated(self) -> bool:
        """Refused because no destination was given at all."""
        return not self.may_proceed and self.destination == "(unstated)"

    def describe(self) -> str:
        """The sentence an operator reads when something is blocked.

        A bare refusal produces an outage nobody can diagnose: the operator sees
        a failure and not a policy, and spends the first hour looking at the
        network.
        """
        subject = self.subject or "this data"
        if self.verdict is Verdict.UNRESTRICTED:
            return (
                f"{subject} may go to {self.destination}: this tenant declares no "
                "residency rule, so nothing is restricted. That is an absence of a "
                "rule, not an approval."
            )
        allowed = ", ".join(self.rule) or "(none)"
        if self.verdict is Verdict.PERMITTED:
            return (
                f"{subject} may go to {self.destination}: the tenant's data must stay "
                f"in {allowed}, and {self.destination} is among them."
            )
        if self.verdict is Verdict.UNDECLARED:
            return (
                f"{subject} may not go to {self.destination}: it does not declare a "
                f"jurisdiction, and this tenant's data must stay in {allowed}. "
                "Undeclared is refused rather than assumed unrestricted — otherwise "
                "the one dataset nobody got round to declaring is the one that leaves "
                "the region."
            )
        return (
            f"{subject} may not go to {self.destination}: it belongs to "
            f"{self.jurisdiction or 'an unstated jurisdiction'} and this tenant's data "
            f"must stay in {allowed}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "may_proceed": self.may_proceed,
            "destination": self.destination,
            "rule": list(self.rule),
            "jurisdiction": self.jurisdiction,
            "subject": self.subject,
            "message": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Policy:
    """One tenant's residency rule."""

    #: Jurisdictions this tenant's data may occupy. Empty means unrestricted.
    allowed: tuple[str, ...] = ()

    @classmethod
    def of(cls, residency: str | Iterable[str] | None) -> Policy:
        """From a tenant's stored residency, however it was written.

        A comma-separated string is what a form produces and a list is what an
        API produces; accepting only one of them means the rule silently does
        not apply for half of the ways it can be set.
        """
        if residency is None:
            return cls()
        if isinstance(residency, str):
            parts = [part.strip() for part in residency.split(",")]
        else:
            parts = [str(part).strip() for part in residency]
        return cls(allowed=tuple(sorted({part.upper() for part in parts if part})))

    @property
    def is_unrestricted(self) -> bool:
        return not self.allowed

    def decide(self, *, destination: str, jurisdiction: str = "", subject: str = "") -> Decision:
        """Whether ``subject`` may move to ``destination``."""
        where = (destination or "").strip().upper()
        belongs = (jurisdiction or "").strip().upper()

        if self.is_unrestricted:
            return Decision(
                verdict=Verdict.UNRESTRICTED,
                destination=where or "(unstated)",
                jurisdiction=belongs,
                subject=subject,
            )
        if not where:
            # A movement with no stated destination cannot be checked, and a
            # check that cannot be made is a refusal rather than a pass.
            return Decision(
                verdict=Verdict.REFUSED,
                destination="(unstated)",
                rule=self.allowed,
                jurisdiction=belongs,
                subject=subject,
            )
        if not belongs:
            return Decision(
                verdict=Verdict.UNDECLARED,
                destination=where,
                rule=self.allowed,
                subject=subject,
            )
        permitted = where in self.allowed and belongs in self.allowed
        return Decision(
            verdict=Verdict.PERMITTED if permitted else Verdict.REFUSED,
            destination=where,
            rule=self.allowed,
            jurisdiction=belongs,
            subject=subject,
        )

    def describe(self) -> str:
        if self.is_unrestricted:
            return "no residency rule: data may go anywhere"
        return f"data must stay in {', '.join(self.allowed)}"


def refusals(decisions: Iterable[Decision]) -> tuple[Decision, ...]:
    """Only what was blocked. What a residency report is actually about."""
    return tuple(decision for decision in decisions if not decision.may_proceed)


__all__ = ["Decision", "Policy", "Verdict", "refusals"]
