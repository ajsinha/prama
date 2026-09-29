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

    def held(self, criticality: Criticality | int, approved_by: str | None) -> bool:
        """Whether a change at this tier, with this approver, waits for approval.

        A change that needs an approver and has none is **held**: recorded, and
        not in effect until somebody approves it (`check_approver`). It used to
        be refused outright, with a remedy promising exactly this hold, which
        nothing implemented — so a Tier-1 declaration could only be made by
        naming an approver, and over the API any caller could name anybody.
        """
        return self.for_criticality(criticality).needs_approver and not approved_by

    def check(
        self,
        *,
        criticality: Criticality | int,
        authored_by: str | None,
        approved_by: str | None,
        what: str = "declaration",
    ) -> None:
        """Refuse an approval the tier does not allow.

        A missing approver is not refused here: the change is held (`held`).
        What is refused is the author approving their own Tier-1 change.
        """
        if approved_by:
            self.check_approver(
                criticality=criticality, authored_by=authored_by, approver=approved_by, what=what
            )

    def check_approver(
        self,
        *,
        criticality: Criticality | int,
        authored_by: str | None,
        approver: str,
        what: str = "declaration",
    ) -> None:
        """Refuse *approver* for a change *authored_by* made, if the tier forbids it."""
        requirement = self.for_criticality(criticality)
        if requirement.needs_second_person and authored_by and approver == authored_by:
            raise ValidationError(
                f"a Tier-{int(criticality)} {what} cannot be approved by its own author",
                remedy=(
                    "Ask a second person to approve it. Segregation of duties on Tier-1 "
                    "declarations is a control, not a formality."
                ),
                context={"author": authored_by, "approver": approver},
            )
