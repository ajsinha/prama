"""Approval policy for declarations.

Who may declare what, and what must be reviewed before it takes effect. The
policy lives here rather than scattered through the services so that "what needs
a second pair of eyes?" has one answer, visible in one file, that an auditor can
read.

The rule that matters: **a Tier-1 declaration cannot be authored and approved by
the same person.** Segregation of duties expressed in code, not in a procedure
document that nobody reads.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum

from prama.core.errors import ValidationError
from prama.semantic.values import Criticality


class ApprovalRequirement(enum.Enum):
    """How much review a change needs before it is effective."""

    NONE = "none"  # author's word is enough
    REVIEW = "review"  # someone must look, but not necessarily another person
    MAKER_CHECKER = "maker_checker"  # a *different* person must approve

    @property
    def needs_approver(self) -> bool:
        return self is not ApprovalRequirement.NONE

    @property
    def needs_second_person(self) -> bool:
        return self is ApprovalRequirement.MAKER_CHECKER


@dataclasses.dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """Maps criticality to the review a change requires.

    The defaults are deliberately strict at Tier 1 and permissive below it. A
    governance regime that demands two signatures for a comment on a Tier-4
    dataset trains people to click through approvals, which is worse than having
    none.
    """

    tier_one: ApprovalRequirement = ApprovalRequirement.MAKER_CHECKER
    tier_two: ApprovalRequirement = ApprovalRequirement.REVIEW
    tier_three: ApprovalRequirement = ApprovalRequirement.NONE
    tier_four: ApprovalRequirement = ApprovalRequirement.NONE

    def for_criticality(self, criticality: Criticality | int) -> ApprovalRequirement:
        tier = int(criticality)
        return {
            1: self.tier_one,
            2: self.tier_two,
            3: self.tier_three,
            4: self.tier_four,
        }.get(tier, ApprovalRequirement.NONE)

    def check(
        self,
        *,
        criticality: Criticality | int,
        authored_by: str | None,
        approved_by: str | None,
        what: str = "declaration",
    ) -> None:
        """Refuse a change that does not meet its approval requirement."""
        requirement = self.for_criticality(criticality)
        if not requirement.needs_approver:
            return
        if not approved_by:
            raise ValidationError(
                f"a Tier-{int(criticality)} {what} requires approval before it takes effect",
                remedy=(
                    "Submit it for review. It will be held as proposed until an approver "
                    "signs it off."
                ),
                context={"criticality": int(criticality), "requirement": requirement.value},
            )
        if requirement.needs_second_person and approved_by == authored_by:
            raise ValidationError(
                f"a Tier-{int(criticality)} {what} cannot be approved by its own author",
                remedy=(
                    "Ask a second person to approve it. Segregation of duties on Tier-1 "
                    "declarations is a control, not a formality."
                ),
                context={"author": authored_by, "approver": approved_by},
            )
