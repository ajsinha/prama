"""The review queue: one channel in, and a memory of what was said before.

Everything Wave 6 generates arrives here — Γ's declaration-derived controls,
mined constraints, induced rules, extracted document rules — and a person
decides. The queue's job is to make that decision cheap: fold duplicates,
surface corroboration, order by what is worth the next minute, and above all
**stop asking questions that have already been answered.**

That last one is the difference between a queue people work and a queue people
abandon. A miner that re-proposes "this column should be non-null" every
Tuesday, having been told no last Tuesday and the Tuesday before, does not just
waste a reviewer's time — it teaches them that the queue is noise, and then the
one proposal that mattered goes unread with the rest.

So a rejection is remembered. It suppresses the same proposal, and it stays
suppressed until the evidence behind it changes materially — at which point the
proposal returns *saying what changed*, because "you rejected this when 3% of
rows failed; it is now 40%" is a different question from the one that was
answered.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.propose.proposal import (
    Decision,
    Proposal,
    ProposalStatus,
    RejectionReason,
)
from prama.propose.utility import AcceptanceHistory, Context, UtilityScorer, rank

#: How much a backtest's violation rate must move before a rejected proposal is
#: worth asking about again. Set where it is because a rate that has doubled is
#: describing a different situation, while one that has drifted by a point is
#: describing the same one — and re-asking about the same one is precisely what
#: trains people to stop reading.
MATERIAL_CHANGE = 2.0


@dataclasses.dataclass(frozen=True, slots=True)
class Suppression:
    """A remembered rejection, and what would make it worth asking again."""

    identity: str
    reason: RejectionReason
    decided_by: str
    decided_at: str
    #: The violation rate at the time of rejection, when there was a backtest.
    #: The number the change is measured against.
    violation_rate: float | None = None
    note: str = ""

    @property
    def is_permanent(self) -> bool:
        """Whether new evidence could ever bring this back.

        A rule rejected as *incorrect* is wrong however the data changes, and
        re-offering it when the data shifts would be re-asking a question about
        the rule using evidence about the data.
        """
        return not self.reason.may_be_reconsidered

    def reopened_by(self, rate: float | None) -> str:
        """Why this proposal is being asked about again, or "" for not yet."""
        if self.is_permanent:
            return ""
        if rate is None or self.violation_rate is None:
            return ""
        before, after = self.violation_rate, rate
        if before <= 0:
            return (
                f"it was rejected when nothing failed it, and {after:.1%} of rows fail it now"
                if after > 0
                else ""
            )
        ratio = after / before
        if ratio >= MATERIAL_CHANGE:
            return f"you rejected this when {before:.1%} of rows failed it; {after:.1%} fail it now"
        if ratio <= 1 / MATERIAL_CHANGE and self.reason is RejectionReason.TOO_NOISY:
            return f"you rejected this as too noisy at {before:.1%}; it would now flag {after:.1%}"
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "reason": self.reason.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "violation_rate": self.violation_rate,
            "is_permanent": self.is_permanent,
            "note": self.note,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Admission:
    """What the queue did with one offered proposal, and why.

    Returned rather than swallowed, so a generator can report "I produced forty
    and thirty-two were already known" instead of appearing to have produced
    eight.
    """

    proposal: Proposal | None
    outcome: str
    detail: str = ""

    @property
    def admitted(self) -> bool:
        return self.outcome in ("admitted", "reopened", "superseded")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "detail": self.detail,
            "identity": self.proposal.identity if self.proposal else "",
        }


class ProposalQueue:
    """The single mutation channel, with a memory."""

    def __init__(
        self,
        *,
        history: AcceptanceHistory | None = None,
        scorer: UtilityScorer | None = None,
    ) -> None:
        self._history = AcceptanceHistory() if history is None else history
        self._scorer = UtilityScorer(self._history) if scorer is None else scorer
        self._open: dict[str, Proposal] = {}
        self._decided: dict[str, Proposal] = {}
        self._suppressed: dict[str, Suppression] = {}
        #: Identities already running in the estate. Offering one again is not
        #: a duplicate to be dropped silently — it is usually a *revision*, and
        #: telling the reviewer that is more useful than either dropping it or
        #: presenting it as new.
        self._live: dict[str, str] = {}

    # -- what is already true ---------------------------------------------

    def register_existing(self, identity: str, content_hash: str) -> None:
        """Record a control already running, so a re-proposal is seen as one."""
        self._live[identity] = content_hash

    def remember_rejection(self, suppression: Suppression) -> None:
        self._suppressed[suppression.identity] = suppression

    # -- offering ----------------------------------------------------------

    def offer(self, proposal: Proposal) -> Admission:
        """Put one proposal to the queue. It may not end up in it."""
        identity = proposal.identity
        rate = proposal.backtest.violation_rate if proposal.backtest else None

        live_hash = self._live.get(identity)
        if live_hash is not None:
            if live_hash == proposal.content_hash:
                return Admission(
                    proposal=None,
                    outcome="already_live",
                    detail="an identical control is already running",
                )
            return self._admit(
                dataclasses.replace(proposal, supersedes=live_hash),
                outcome="superseded",
                detail=(
                    "a control for this already runs; this is a revision of it, and "
                    "approving it replaces rather than adds"
                ),
            )

        suppression = self._suppressed.get(identity)
        if suppression is not None:
            why = suppression.reopened_by(rate)
            if not why:
                return Admission(
                    proposal=None,
                    outcome="suppressed",
                    detail=(
                        f"rejected as {suppression.reason.value} by "
                        f"{suppression.decided_by} on {suppression.decided_at[:10]}"
                    ),
                )
            del self._suppressed[identity]
            return self._admit(proposal, outcome="reopened", detail=why)

        existing = self._open.get(identity)
        if existing is not None:
            if existing.content_hash == proposal.content_hash:
                if existing.origin is proposal.origin:
                    return Admission(
                        proposal=existing,
                        outcome="duplicate",
                        detail="the same proposal from the same source",
                    )
                # Two independent origins reaching the same rule. The naive
                # move is to drop one; that discards the most interesting thing
                # that can happen here.
                merged = self._keep_stronger(existing, proposal)
                self._open[identity] = merged
                return Admission(
                    proposal=merged,
                    outcome="corroborated",
                    detail=(
                        f"{proposal.origin.label} as well, which is independent "
                        f"evidence rather than a duplicate"
                    ),
                )
            return self._admit(
                dataclasses.replace(proposal, supersedes=existing.content_hash),
                outcome="superseded",
                detail="replaces an earlier proposal for the same thing",
            )

        return self._admit(proposal, outcome="admitted")

    def _admit(self, proposal: Proposal, *, outcome: str, detail: str = "") -> Admission:
        self._open[proposal.identity] = proposal
        return Admission(proposal=proposal, outcome=outcome, detail=detail)

    @staticmethod
    def _keep_stronger(first: Proposal, second: Proposal) -> Proposal:
        """Keep the higher authority, and record the other as corroboration.

        A declaration confirmed by mining is stronger than either alone, and a
        reviewer reading "you declared this and the data independently confirms
        it" approves in a second.
        """
        stronger, weaker = (
            (first, second)
            if first.origin.authority >= second.origin.authority
            else (second, first)
        )
        return stronger.corroborated_by(weaker)

    # -- deciding ----------------------------------------------------------

    def accept(self, identity: str, who: str, at: str, *, amended: bool = False) -> Proposal:
        proposal = self._require_open(identity).accepted_by(who, at, amended=amended)
        self._settle(proposal)
        return proposal

    def reject(
        self,
        identity: str,
        who: str,
        at: str,
        reason: RejectionReason,
        note: str = "",
    ) -> Proposal:
        proposal = self._require_open(identity).rejected_by(who, at, reason, note)
        self._settle(proposal)
        self._suppressed[identity] = Suppression(
            identity=identity,
            reason=reason,
            decided_by=who,
            decided_at=at,
            violation_rate=(proposal.backtest.violation_rate if proposal.backtest else None),
            note=note,
        )
        return proposal

    def defer(self, identity: str, because: str) -> Proposal:
        proposal = self._require_open(identity).deferred(because)
        self._open[identity] = proposal
        return proposal

    def _settle(self, proposal: Proposal) -> None:
        self._open.pop(proposal.identity, None)
        self._decided[proposal.identity] = proposal
        self._history.record(proposal)

    def _require_open(self, identity: str) -> Proposal:
        try:
            return self._open[identity]
        except KeyError:
            raise KeyError(
                f"no open proposal {identity!r}. "
                + (
                    "It was already decided."
                    if identity in self._decided
                    else "It was never offered, or was suppressed."
                )
            ) from None

    # -- reading -----------------------------------------------------------

    def pending(self, context: dict[str, Context] | None = None) -> list[Proposal]:
        """Everything awaiting a decision, best first."""
        return rank(
            [p for p in self._open.values() if p.status is ProposalStatus.PROPOSED],
            scorer=self._scorer,
            context=context,
        )

    def deferred(self) -> list[Proposal]:
        return [p for p in self._open.values() if p.status is ProposalStatus.DEFERRED]

    def decided(self) -> list[Proposal]:
        return list(self._decided.values())

    def suppressions(self) -> list[Suppression]:
        return list(self._suppressed.values())

    def auto_activatable(self) -> list[Proposal]:
        """Proposals that may run without a person, which is few of them.

        Only a declaration, and only one whose backtest does not show it
        drowning the queue. A generated control that would fire on half the
        rows is not the control the declarer meant however clearly they
        declared it — it means the data does not match the declaration, which
        is a conversation rather than an alert.
        """
        return [p for p in self._open.values() if p.is_open and not p.needs_review]

    def summary(self) -> dict[str, Any]:
        """A report worth putting in front of somebody."""
        pending = self.pending()
        noisy = [p for p in pending if p.backtest and p.backtest.is_unactionable]
        return {
            "pending": len(pending),
            "deferred": len(self.deferred()),
            "decided": len(self._decided),
            "suppressed": len(self._suppressed),
            "auto_activatable": len(self.auto_activatable()),
            "would_be_too_noisy": len(noisy),
            "by_origin": self._counts(pending),
            "suspect_rules": list(self._history.suspect_rules()),
            "top": [p.identity for p in pending[:10]],
        }

    @staticmethod
    def _counts(proposals: list[Proposal]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for proposal in proposals:
            counts[proposal.origin.value] = counts.get(proposal.origin.value, 0) + 1
        return counts

    @property
    def history(self) -> AcceptanceHistory:
        return self._history


def suppression_from(proposal: Proposal) -> Suppression:
    """Build a suppression from a decided proposal, for reloading a queue."""
    decision = proposal.decision
    if decision is None or decision.reason is None:
        raise ValueError("only a rejected proposal produces a suppression")
    return Suppression(
        identity=proposal.identity,
        reason=decision.reason,
        decided_by=decision.decided_by,
        decided_at=decision.decided_at,
        violation_rate=proposal.backtest.violation_rate if proposal.backtest else None,
        note=decision.note,
    )


__all__ = [
    "MATERIAL_CHANGE",
    "Admission",
    "Decision",
    "ProposalQueue",
    "Suppression",
    "suppression_from",
]
