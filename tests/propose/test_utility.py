"""Ranking, and the feedback trap it has to avoid.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.core.provenance import Origin, Provenance
from prama.propose.proposal import Backtest, Proposal, RejectionReason
from prama.propose.utility import (
    AcceptanceHistory,
    Context,
    UtilityScorer,
    indicted_rules,
    rank,
)

NOW = "2026-09-08T10:00:00Z"


def proposal(
    identity: str = "P1",
    *,
    origin: Origin = Origin.MINING,
    rule: str = "mine.not_null",
    dataset: str = "t",
    backtest: Backtest | None = None,
) -> Proposal:
    return Proposal(
        identity=identity,
        content=f"CHECK {dataset}.x IS NOT NULL",
        content_hash=identity,
        provenance=Provenance(origin=origin, rule=rule),
        description="every x has a value",
        dataset=dataset,
        subject="x",
        rule=rule,
        backtest=backtest,
    )


# -- what the ranking is for -------------------------------------------------


def test_a_tier_one_cde_outranks_an_informational_column() -> None:
    scorer = UtilityScorer()
    critical = scorer.score(proposal(), Context(criticality=1, is_cde=True))
    routine = scorer.score(proposal(), Context(criticality=4))
    assert critical.score > routine.score


def test_unprotected_ground_outranks_a_fifth_control_on_a_covered_column() -> None:
    scorer = UtilityScorer()
    fresh = scorer.score(proposal(), Context(criticality=2, covered_fraction=0.05))
    crowded = scorer.score(
        proposal(), Context(criticality=2, subject_already_covered=True, covered_fraction=0.9)
    )
    assert fresh.score > crowded.score


def test_a_declaration_outranks_a_mined_pattern_of_the_same_shape() -> None:
    """No amount of statistical support makes an observation equal to a
    statement of intent."""
    scorer = UtilityScorer()
    declared = scorer.score(proposal(origin=Origin.DECLARATION), Context(criticality=2))
    mined = scorer.score(proposal(origin=Origin.MINING), Context(criticality=2))
    assert declared.score > mined.score


def test_corroboration_raises_confidence_modestly() -> None:
    """Agreement between a declaration and a miner is confirmation, not proof."""
    scorer = UtilityScorer()
    alone = proposal(origin=Origin.MINING)
    confirmed = alone.corroborated_by(proposal(origin=Origin.DECLARATION))
    plain = scorer.score(alone).confidence
    boosted = scorer.score(confirmed).confidence
    assert plain < boosted <= plain + 0.2


def test_a_control_that_would_fire_constantly_is_ranked_down() -> None:
    scorer = UtilityScorer()
    quiet = scorer.score(proposal(backtest=Backtest(scanned=1000, violations=5)))
    loud = scorer.score(proposal(backtest=Backtest(scanned=1000, violations=600)))
    assert loud.score < quiet.score
    assert loud.noise_penalty < 0
    assert quiet.noise_penalty == 0


def test_a_plausible_backlog_is_not_penalised_like_a_description_of_the_data() -> None:
    """There is a real difference between a control flagging 5% of rows and one
    flagging 60%."""
    scorer = UtilityScorer()
    assert scorer.score(proposal(backtest=Backtest(scanned=1000, violations=40))).noise_penalty == 0


# -- the feedback trap -------------------------------------------------------


def test_one_rejection_does_not_send_a_rule_to_the_bottom_forever() -> None:
    """The trap: an unsmoothed rate goes to 0/1, every later proposal sorts
    below everything, nobody reads them, none is accepted, and the rule is dead
    on one reviewer's Tuesday afternoon with nothing saying so."""
    history = AcceptanceHistory()
    before = history.rate("rule:mine.not_null")
    history.record(proposal().rejected_by("a.sinha", NOW, RejectionReason.NOT_MATERIAL))
    after = history.rate("rule:mine.not_null")
    assert before == 0.5
    assert 0.3 < after < 0.4


def test_the_learned_term_cannot_dominate_the_ranking() -> None:
    """A Tier 1 CDE with no control on it must still surface from a rule with a
    poor record. Learning which rules produce good proposals is worth having;
    learning it so hard the estate stops improving is not."""
    history = AcceptanceHistory()
    for index in range(20):
        history.record(
            proposal(identity=f"R{index}").rejected_by("a.sinha", NOW, RejectionReason.NOT_MATERIAL)
        )
    scorer = UtilityScorer(history)
    important = scorer.score(proposal(), Context(criticality=1, is_cde=True))
    trivial = scorer.score(
        proposal(rule="unblemished.rule"), Context(criticality=4, covered_fraction=1.0)
    )
    assert important.score > trivial.score


def test_a_remediation_rejection_is_not_counted_against_the_rule() -> None:
    """ "The data is wrong and will be fixed" is a statement about the data.
    Counting it against the rule that found the problem would teach the ranker
    to bury exactly the findings that worked."""
    history = AcceptanceHistory()
    history.record(proposal().rejected_by("a.sinha", NOW, RejectionReason.PENDING_REMEDIATION))
    assert history.rate("rule:mine.not_null") == 0.5
    assert history.observations("rule:mine.not_null") == 0


def test_an_undecided_proposal_teaches_nothing() -> None:
    history = AcceptanceHistory()
    history.record(proposal())
    assert history.observations("rule:mine.not_null") == 0


# -- the signal worth acting on ---------------------------------------------


def test_a_rule_repeatedly_judged_wrong_is_named_for_a_human_to_fix() -> None:
    """Forty INCORRECT rejections from one rule is a defect somebody should fix
    once, not forty reviewers dismissing it individually."""
    history = AcceptanceHistory()
    for index in range(6):
        history.record(
            proposal(identity=f"R{index}").rejected_by("a.sinha", NOW, RejectionReason.INCORRECT)
        )
    assert "mine.not_null" in history.suspect_rules()
    assert indicted_rules(history) == (("mine.not_null", 6),)


def test_being_told_it_is_immaterial_does_not_indict_the_rule() -> None:
    """ "Right but not worth it" is a threshold on the queue; "wrong" is a bug
    in the generator, and they lead somewhere completely different."""
    history = AcceptanceHistory()
    for index in range(10):
        history.record(
            proposal(identity=f"R{index}").rejected_by("a.sinha", NOW, RejectionReason.NOT_MATERIAL)
        )
    assert history.suspect_rules() == ()


# -- ordering ----------------------------------------------------------------


def test_ranking_is_stable_between_runs() -> None:
    """A list that reshuffles equal items between refreshes looks broken even
    when it is not, and a reviewer working down it cannot lose their place."""
    proposals = [proposal(identity=f"P{i}") for i in range(10)]
    first = [p.identity for p in rank(list(proposals))]
    second = [p.identity for p in rank(list(reversed(proposals)))]
    assert first == second


def test_the_explanation_says_why_it_is_at_the_top() -> None:
    """A reviewer asking deserves a sentence, not 0.87."""
    history = AcceptanceHistory()
    for index in range(4):
        history.record(proposal(identity=f"A{index}").accepted_by("a.sinha", NOW))
    scored = UtilityScorer(history).score(
        proposal(), Context(criticality=1, is_cde=True, covered_fraction=0.1)
    )
    assert "Tier 1" in scored.explanation
    assert "unprotected" in scored.explanation
    assert "accepted" in scored.explanation


def test_the_explanation_says_when_something_was_ranked_down() -> None:
    scored = UtilityScorer().score(proposal(backtest=Backtest(scanned=100, violations=70)))
    assert "70% of rows" in scored.explanation
