"""A proposed change to the estate, and the decision somebody made about it.

`FR-IND-007`: **the single mutation channel.** Nothing becomes a running
control except by passing through here. Mining, induction, document extraction,
example generalisation and Γ itself all produce proposals, and a person decides.
That is not ceremony — it is the difference between an estate somebody owns and
one that appeared overnight, and an estate nobody agreed to is one whose alerts
get muted rather than fixed.

Three things this carries that a naive proposal object does not, each of which
is the difference between a queue people work and a queue people abandon:

**What it would have done.** A control is approved or rejected on its expected
behaviour, not its wording. A proposal that would alert on 40% of rows is a bad
proposal however sound its logic, and the reviewer should not have to discover
that by approving it and waiting. So a proposal carries its backtest, and one
that would fire constantly is marked before anybody looks at it.

**Why it is worth the reviewer's next minute.** A queue of four hundred
proposals in arbitrary order is a queue nobody finishes. Utility is computed,
and it is computed from things that actually predict value — how critical the
data is, how much of the estate is unprotected, how confident the evidence is —
rather than from how recently the proposal arrived.

**That it was rejected before.** Rejecting "this column should be non-null" and
then being offered it again next Tuesday, and every Tuesday after, is how a
review queue becomes noise and then becomes ignored. A rejection is remembered
and suppresses the same proposal until the evidence behind it changes
materially — at which point it returns, saying what changed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from prama.core.provenance import Origin, Provenance


class ProposalStatus(enum.Enum):
    """Where a proposal is."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    #: Held for a reason that will resolve — waiting on a declaration, a
    #: profile, or a decision elsewhere. Distinct from rejected, because a
    #: deferred proposal comes back and a rejected one does not.
    DEFERRED = "deferred"
    #: A newer proposal for the same thing replaced it.
    SUPERSEDED = "superseded"

    @property
    def is_open(self) -> bool:
        return self in (ProposalStatus.PROPOSED, ProposalStatus.DEFERRED)

    @property
    def is_decided(self) -> bool:
        return self in (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED)


class RejectionReason(enum.Enum):
    """Why a proposal was turned down.

    A free-text reason would be easier and would be worth much less. The reason
    determines what happens next, and "wrong" and "right but not worth it" lead
    somewhere completely different: the first is a defect in the rule that
    produced it, the second is a threshold on the queue.
    """

    #: The rule is wrong about the data. The generator or miner has a defect.
    INCORRECT = "incorrect"
    #: True, and not worth alerting on. Nothing is broken.
    NOT_MATERIAL = "not_material"
    #: True today, not a rule. The classic mined-constraint failure: unique in
    #: this extract, not a key.
    COINCIDENTAL = "coincidental"
    #: Something else already covers it.
    DUPLICATE = "duplicate"
    #: Correct and unaffordable — it would alert too often to be actionable.
    TOO_NOISY = "too_noisy"
    #: The data is wrong and will be fixed; the rule is right but premature.
    PENDING_REMEDIATION = "pending_remediation"

    @property
    def indicts_the_rule(self) -> bool:
        """Whether this rejection says the *generator* is at fault.

        The signal worth acting on in aggregate: one INCORRECT rejection is a
        bad proposal, and forty from the same rule is a bug somebody should fix
        once rather than forty reviewers dismissing it one at a time.
        """
        return self in (RejectionReason.INCORRECT, RejectionReason.COINCIDENTAL)

    @property
    def may_be_reconsidered(self) -> bool:
        """Whether new evidence should bring this proposal back.

        A rule rejected as *incorrect* is wrong however the data changes. One
        rejected as *not material* or *pending remediation* is a judgement
        about circumstances, and circumstances move.
        """
        return self in (
            RejectionReason.NOT_MATERIAL,
            RejectionReason.TOO_NOISY,
            RejectionReason.PENDING_REMEDIATION,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Backtest:
    """What the proposed control would have done on data already held.

    The single most useful thing to put in front of a reviewer, and the reason
    is arithmetic rather than psychology: "this would have failed 41% of rows
    every day last month" answers the approve-or-not question outright, and no
    amount of reading the rule does.
    """

    #: Rows examined.
    scanned: int
    #: Rows that would have violated it.
    violations: int
    #: Days examined, so a daily alert volume can be stated.
    days: int = 1
    #: Distinct segments — entities, feeds — in which violations occurred. A
    #: failure concentrated in one entity is a different finding from the same
    #: count spread evenly, and usually a more actionable one.
    affected_segments: tuple[str, ...] = ()
    #: Set when the control could not be run against history — no data yet, or
    #: the column does not exist in the retained snapshots.
    unavailable: str = ""

    @property
    def ran(self) -> bool:
        return not self.unavailable and self.scanned > 0

    @property
    def violation_rate(self) -> float:
        return self.violations / self.scanned if self.scanned else 0.0

    @property
    def alerts_per_day(self) -> float:
        return self.violations / self.days if self.days else float(self.violations)

    @property
    def would_pass_today(self) -> bool:
        return self.ran and self.violations == 0

    @property
    def is_unactionable(self) -> bool:
        """Whether approving this would produce more work than value.

        The threshold is not a guess. A control failing more than a fifth of
        rows is not identifying exceptions; it is describing the data, and
        whatever it describes is either normal or a project rather than an
        alert. Either way the daily queue is the wrong place for it.
        """
        return self.ran and self.violation_rate > 0.2

    def describe(self) -> str:
        if self.unavailable:
            return f"not backtested: {self.unavailable}"
        if not self.scanned:
            return "no rows were available to test it against"
        if not self.violations:
            return (
                f"would have passed cleanly on all {self.scanned:,} rows "
                f"over {self.days} day{'s' if self.days != 1 else ''}"
            )
        where = (
            f", concentrated in {', '.join(self.affected_segments[:3])}"
            if self.affected_segments
            else ""
        )
        return (
            f"would have flagged {self.violations:,} of {self.scanned:,} rows "
            f"({self.violation_rate:.2%}), about {self.alerts_per_day:,.0f} a day{where}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "violations": self.violations,
            "days": self.days,
            "violation_rate": round(self.violation_rate, 6),
            "alerts_per_day": round(self.alerts_per_day, 2),
            "affected_segments": list(self.affected_segments),
            "unavailable": self.unavailable,
            "is_unactionable": self.is_unactionable,
            "summary": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    """A reviewer's answer, and enough of it to learn from."""

    status: ProposalStatus
    decided_by: str
    #: ISO-8601 UTC.
    decided_at: str
    reason: RejectionReason | None = None
    note: str = ""
    #: What the reviewer changed before accepting, if anything. An accepted-
    #: with-edits proposal is the most informative outcome there is: the rule
    #: was nearly right, and the edit says exactly how it was wrong.
    amended: bool = False

    def __post_init__(self) -> None:
        if self.status is ProposalStatus.REJECTED and self.reason is None:
            raise ValueError(
                "a rejection must say why: the reason decides whether the rule "
                "comes back with new evidence, and whether the generator that "
                "produced it has a defect"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason.value if self.reason else None,
            "note": self.note,
            "amended": self.amended,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Utility:
    """How much this proposal is worth, and what that estimate rests on.

    The components are kept rather than folded into a single number, because a
    reviewer asking "why is this at the top?" deserves "because it is a Tier 1
    CDE with no control on it and the evidence is a check digit" and not "0.87".
    """

    score: float
    criticality: float = 0.0
    coverage_gap: float = 0.0
    confidence: float = 0.0
    #: Learned from what this reviewer's organisation has accepted before
    #: (`FR-CHT-004`). Zero until there is history, which is the honest
    #: starting point rather than a prior somebody invented.
    acceptance_prior: float = 0.0
    #: Negative. A proposal that would fire constantly is worth less than one
    #: that would not, however important the column.
    noise_penalty: float = 0.0
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "criticality": round(self.criticality, 4),
            "coverage_gap": round(self.coverage_gap, 4),
            "confidence": round(self.confidence, 4),
            "acceptance_prior": round(self.acceptance_prior, 4),
            "noise_penalty": round(self.noise_penalty, 4),
            "explanation": self.explanation,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Proposal:
    """One proposed addition to the estate, with everything needed to judge it."""

    #: Stable across regeneration — the same identity as the derived control or
    #: comparison it carries. Two proposals for the same thing are one
    #: proposal, whatever produced them.
    identity: str
    #: What is being proposed, rendered. PQL for a control, the COMPARE line
    #: for a comparison.
    content: str
    #: Changes when the content does. What supersession is decided on.
    content_hash: str
    provenance: Provenance
    #: The plain sentence a reviewer reads first.
    description: str
    dataset: str = ""
    subject: str = ""
    rule: str = ""
    severity: str = "major"
    status: ProposalStatus = ProposalStatus.PROPOSED
    backtest: Backtest | None = None
    utility: Utility | None = None
    decision: Decision | None = None
    #: Set when this proposal replaced an earlier one for the same identity.
    supersedes: str = ""
    #: Why it is being held, when deferred.
    deferred_because: str = ""

    @property
    def origin(self) -> Origin:
        return self.provenance.origin

    @property
    def is_open(self) -> bool:
        return self.status.is_open

    @property
    def needs_review(self) -> bool:
        """Whether a person must look at this before it can run.

        Only a declaration may skip review, and even then only if it would not
        immediately drown the queue. A generated control that would fire on
        half the rows is not a control the declarer meant, whatever they
        declared — it means the data does not match the declaration, and that
        is a conversation rather than an alert.
        """
        if self.backtest is not None and self.backtest.is_unactionable:
            return True
        return not self.origin.may_auto_activate

    @property
    def score(self) -> float:
        return self.utility.score if self.utility else 0.0

    def accepted_by(self, who: str, at: str, *, amended: bool = False) -> Proposal:
        return dataclasses.replace(
            self,
            status=ProposalStatus.ACCEPTED,
            decision=Decision(
                status=ProposalStatus.ACCEPTED,
                decided_by=who,
                decided_at=at,
                amended=amended,
            ),
        )

    def rejected_by(self, who: str, at: str, reason: RejectionReason, note: str = "") -> Proposal:
        return dataclasses.replace(
            self,
            status=ProposalStatus.REJECTED,
            decision=Decision(
                status=ProposalStatus.REJECTED,
                decided_by=who,
                decided_at=at,
                reason=reason,
                note=note,
            ),
        )

    def deferred(self, because: str) -> Proposal:
        return dataclasses.replace(self, status=ProposalStatus.DEFERRED, deferred_because=because)

    def corroborated_by(self, other: Proposal) -> Proposal:
        """Fold a second, independent proposal for the same thing into this one.

        The interesting case rather than a housekeeping one, and the reason
        proposals are merged rather than deduplicated: a declaration the data
        independently confirms is approved in a second, where the same
        declaration with the corroborating evidence discarded takes a minute
        and a query.
        """
        return dataclasses.replace(
            self,
            provenance=self.provenance.corroborated_by(
                other.provenance, other.provenance.statement or other.rule
            ),
        )

    def why(self) -> str:
        """Everything a reviewer needs, in the order they need it."""
        parts = [self.description, self.provenance.sentence()]
        if self.backtest is not None:
            parts.append(self.backtest.describe().capitalize())
        if self.utility is not None and self.utility.explanation:
            parts.append(self.utility.explanation)
        return " ".join(p.rstrip(".") + "." for p in parts if p)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "content": self.content,
            "content_hash": self.content_hash,
            "description": self.description,
            "dataset": self.dataset,
            "subject": self.subject,
            "rule": self.rule,
            "severity": self.severity,
            "status": self.status.value,
            "origin": self.origin.value,
            "needs_review": self.needs_review,
            "provenance": self.provenance.to_dict(),
            "backtest": self.backtest.to_dict() if self.backtest else None,
            "utility": self.utility.to_dict() if self.utility else None,
            "decision": self.decision.to_dict() if self.decision else None,
            "supersedes": self.supersedes,
            "deferred_because": self.deferred_because,
            "why": self.why(),
        }
