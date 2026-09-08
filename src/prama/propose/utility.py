"""How proposals are ranked, and how the ranking learns.

A queue of four hundred proposals in arbitrary order is a queue nobody
finishes, and the ones that matter are not the ones that happened to be
generated first. `FR-CHT-004` asks for utility ranking learned from acceptance
history; this is that, with the components kept separate so the answer to "why
is this at the top?" is a sentence rather than a number.

**The feedback trap, and why the prior is smoothed.** The obvious
implementation keeps an acceptance rate per rule and ranks by it. Reject the
first proposal a rule ever makes and its rate is 0/1; every later proposal from
that rule sorts to the bottom, where nobody reads it, so none is ever accepted,
so the rate stays zero. The rule is dead on one reviewer's Tuesday afternoon,
permanently, and nothing in the system says so.

Two things prevent it. The prior is Laplace-smoothed, so a single rejection
moves it from 0.5 to 0.33 rather than to 0. And it is *bounded* — the learned
term can reorder the queue but cannot dominate it, so a Tier 1 CDE with no
control on it still surfaces even from a rule with a poor record. Learning
which rules produce good proposals is worth having; learning it so hard that
the estate stops improving is not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.core.provenance import Origin
from prama.propose.proposal import Proposal, RejectionReason, Utility

#: How much each component can contribute. They sum to more than 1 before the
#: noise penalty, which is deliberate: a proposal can be excellent on every
#: axis, and the ranking only has to be an order.
WEIGHTS: dict[str, float] = {
    "criticality": 0.35,
    "coverage_gap": 0.25,
    "confidence": 0.20,
    "acceptance_prior": 0.20,
}

#: Rejections that must not be counted against a rule. "The data is wrong and
#: will be fixed" is a statement about the data, and "something else already
#: covers it" is a statement about the estate. Counting either against the rule
#: that produced the proposal would teach the ranker to bury the findings that
#: worked.
NOT_THE_RULES_FAULT: frozenset[RejectionReason] = frozenset(
    {RejectionReason.PENDING_REMEDIATION, RejectionReason.DUPLICATE}
)

#: The learned term's ceiling. Bounded so a rule with a poor record can still
#: surface a Tier 1 gap — see the feedback trap above.
PRIOR_CEILING = WEIGHTS["acceptance_prior"]


@dataclasses.dataclass(frozen=True, slots=True)
class Context:
    """What the scorer knows about the world the proposal lands in."""

    #: 1 (regulatory) to 4 (informational).
    criticality: int = 4
    #: Fraction of this dataset's columns already under a reviewed control.
    #: A proposal covering unprotected ground is worth more than the fifth
    #: control on the same column.
    covered_fraction: float = 0.0
    #: Whether the subject is a declared critical data element.
    is_cde: bool = False
    #: Whether any control already exists on this exact subject.
    subject_already_covered: bool = False


class AcceptanceHistory:
    """What this organisation has accepted before, by rule and by origin.

    Counts rather than a model. There is nothing here a linear model would add
    that a smoothed rate does not already give, and a great deal a linear model
    would take away: this one can be printed, argued with, and reset.
    """

    def __init__(self, *, smoothing: float = 1.0) -> None:
        #: Laplace pseudo-counts. One accept and one reject to start, so a
        #: rule's first rejection moves its prior to 0.33 rather than to zero.
        self._smoothing = smoothing
        self._accepted: dict[str, float] = {}
        self._rejected: dict[str, float] = {}
        #: Rejections that indict the rule rather than the circumstances,
        #: counted separately. Forty of these from one rule is a defect
        #: somebody should fix once, not forty reviewers dismissing it
        #: individually.
        self._indictments: dict[str, int] = {}

    def record(self, proposal: Proposal) -> None:
        """Learn from one decided proposal. Undecided ones teach nothing."""
        decision = proposal.decision
        if decision is None or not decision.status.is_decided:
            return
        if decision.reason in NOT_THE_RULES_FAULT:
            # "The data is wrong and will be fixed" is a statement about the
            # data. Counting it against the rule that correctly identified the
            # problem would teach the ranker to bury exactly the findings that
            # led to a remediation — the ones that worked.
            return
        for key in self._keys(proposal):
            if decision.status.value == "accepted":
                self._accepted[key] = self._accepted.get(key, 0.0) + 1.0
            else:
                self._rejected[key] = self._rejected.get(key, 0.0) + 1.0
        reason = decision.reason
        if reason is not None and reason.indicts_the_rule and proposal.rule:
            self._indictments[proposal.rule] = self._indictments.get(proposal.rule, 0) + 1

    def rate(self, key: str) -> float:
        """The smoothed acceptance rate for a rule or origin."""
        accepted = self._accepted.get(key, 0.0) + self._smoothing
        rejected = self._rejected.get(key, 0.0) + self._smoothing
        return accepted / (accepted + rejected)

    def prior(self, proposal: Proposal) -> float:
        """The learned term, in [0, 1], averaged over what is known."""
        keys = self._keys(proposal)
        return sum(self.rate(k) for k in keys) / len(keys)

    def observations(self, key: str) -> int:
        return int(self._accepted.get(key, 0.0) + self._rejected.get(key, 0.0))

    def indictments(self, rule: str) -> int:
        return self._indictments.get(rule, 0)

    def suspect_rules(self, *, threshold: int = 5) -> tuple[str, ...]:
        """Rules a person should look at rather than keep dismissing.

        The output this class exists for beyond ranking. A rule rejected as
        *incorrect* five times is producing wrong proposals systematically, and
        the fix is in the generator rather than in the queue.
        """
        return tuple(
            sorted(rule for rule, count in self._indictments.items() if count >= threshold)
        )

    @staticmethod
    def _keys(proposal: Proposal) -> tuple[str, ...]:
        keys = [f"origin:{proposal.origin.value}"]
        if proposal.rule:
            keys.append(f"rule:{proposal.rule}")
        return tuple(keys)

    def to_dict(self) -> dict[str, Any]:
        keys = sorted({*self._accepted, *self._rejected})
        return {
            "keys": {
                key: {
                    "accepted": self._accepted.get(key, 0.0),
                    "rejected": self._rejected.get(key, 0.0),
                    "rate": round(self.rate(key), 4),
                }
                for key in keys
            },
            "suspect_rules": list(self.suspect_rules()),
        }


class UtilityScorer:
    """Ranks a proposal, and can say why."""

    def __init__(self, history: AcceptanceHistory | None = None) -> None:
        self._history = AcceptanceHistory() if history is None else history

    def score(self, proposal: Proposal, context: Context | None = None) -> Utility:
        ctx = Context() if context is None else context
        criticality = self._criticality(ctx)
        coverage_gap = self._coverage_gap(ctx)
        confidence = self._confidence(proposal)
        prior = min(PRIOR_CEILING, self._history.prior(proposal) * PRIOR_CEILING * 2)
        penalty = self._noise_penalty(proposal)
        total = (
            WEIGHTS["criticality"] * criticality
            + WEIGHTS["coverage_gap"] * coverage_gap
            + WEIGHTS["confidence"] * confidence
            + prior
            + penalty
        )
        return Utility(
            score=max(0.0, total),
            criticality=criticality,
            coverage_gap=coverage_gap,
            confidence=confidence,
            acceptance_prior=prior,
            noise_penalty=penalty,
            explanation=self._explain(proposal, ctx, criticality, coverage_gap, penalty),
        )

    @staticmethod
    def _criticality(context: Context) -> float:
        """Tier 1 scores 1.0, Tier 4 scores 0.25, and a CDE counts as one up."""
        tier = max(1, min(4, context.criticality - (1 if context.is_cde else 0)))
        return (5 - tier) / 4

    @staticmethod
    def _coverage_gap(context: Context) -> float:
        """Unprotected ground is worth more than the fifth control on a column.

        Zero when the exact subject already has a control — not because the
        proposal is wrong, but because a second control on a covered column
        adds far less than a first control on an uncovered one, and the queue
        has to choose.
        """
        if context.subject_already_covered:
            return 0.0
        return max(0.0, 1.0 - context.covered_fraction)

    @staticmethod
    def _confidence(proposal: Proposal) -> float:
        """How strongly the evidence supports it.

        Origin does most of the work here, and it should: a declaration is a
        statement of intent, and no amount of statistical support makes a mined
        pattern equal to one.
        """
        # A declaration alone does not reach 1.0, and the ceiling is reserved
        # rather than wasted. Scoring it 1.0 would make corroboration invisible
        # precisely where it is worth the most — "you declared this and the
        # data independently confirms it" is the strongest evidence the system
        # can produce, and a saturated scale cannot say so.
        base = {
            Origin.DECLARATION: 0.9,
            Origin.DOCUMENT: 0.85,
            Origin.IMPORT: 0.7,
            Origin.MINING: 0.55,
            Origin.EXAMPLE: 0.45,
            Origin.INDUCTION: 0.35,
        }[proposal.origin]
        if proposal.provenance.is_corroborated:
            # Two independent origins reaching the same rule is real evidence,
            # and the size of the bonus is deliberately modest: agreement
            # between a declaration and a miner is confirmation, not proof.
            base = min(1.0, base + 0.15)
        return base

    @staticmethod
    def _noise_penalty(proposal: Proposal) -> float:
        """A control that fires constantly is worth less than one that does not.

        Scaled by how badly, rather than a flat penalty, because there is a
        real difference between a control that flags 5% of rows — plausibly a
        genuine backlog — and one that flags 60%, which is describing the data.
        """
        backtest = proposal.backtest
        if backtest is None or not backtest.ran:
            return 0.0
        if backtest.violation_rate <= 0.05:
            return 0.0
        return -min(0.5, backtest.violation_rate)

    def _explain(
        self,
        proposal: Proposal,
        context: Context,
        criticality: float,
        coverage_gap: float,
        penalty: float,
    ) -> str:
        """Why this is where it is, for the reviewer who asks.

        Assembled rather than stored, because a stored explanation drifts from
        the score it explains — and a wrong explanation of a ranking is worse
        than none, because it is the one somebody repeats.
        """
        parts: list[str] = []
        if criticality >= 0.75:
            parts.append(
                f"Tier {context.criticality} data"
                + (" and a declared CDE" if context.is_cde else "")
            )
        if coverage_gap > 0.5:
            parts.append(f"{1 - context.covered_fraction:.0%} of this dataset is unprotected")
        elif context.subject_already_covered:
            parts.append("this subject already has a control, so it adds less")
        history_key = f"rule:{proposal.rule}" if proposal.rule else ""
        seen = self._history.observations(history_key) if history_key else 0
        if seen >= 3:
            parts.append(
                f"{self._history.rate(history_key):.0%} of proposals from this rule "
                f"have been accepted ({seen} decided)"
            )
        if penalty < 0 and proposal.backtest is not None:
            parts.append(
                f"ranked down because it would flag {proposal.backtest.violation_rate:.0%} of rows"
            )
        return "; ".join(parts)


def rank(
    proposals: list[Proposal],
    *,
    scorer: UtilityScorer | None = None,
    context: dict[str, Context] | None = None,
) -> list[Proposal]:
    """Score and order proposals, best first.

    Ties break on identity rather than on input order, so two runs over the
    same queue produce the same list. A ranking that reshuffles equal items
    between refreshes looks broken even when it is not, and a reviewer working
    down a list cannot lose their place in it.
    """
    scoring = UtilityScorer() if scorer is None else scorer
    contexts = context or {}
    scored = [
        dataclasses.replace(
            proposal,
            utility=scoring.score(proposal, contexts.get(proposal.dataset)),
        )
        for proposal in proposals
    ]
    return sorted(scored, key=lambda p: (-p.score, p.identity))


def indicted_rules(
    history: AcceptanceHistory, *, threshold: int = 5
) -> tuple[tuple[str, int], ...]:
    """Rules whose proposals are repeatedly judged wrong, with the counts."""
    return tuple(
        (rule, history.indictments(rule)) for rule in history.suspect_rules(threshold=threshold)
    )
