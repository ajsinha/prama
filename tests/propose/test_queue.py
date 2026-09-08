"""The review queue, and its memory of what has already been answered.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.provenance import Origin, Provenance
from prama.propose.proposal import Backtest, Proposal, ProposalStatus, RejectionReason
from prama.propose.queue import ProposalQueue, Suppression, suppression_from

NOW = "2026-09-08T10:00:00Z"


def proposal(
    identity: str = "P1",
    *,
    origin: Origin = Origin.MINING,
    content: str = "CHECK t.x IS NOT NULL",
    rule: str = "mine.not_null",
    backtest: Backtest | None = None,
    dataset: str = "t",
) -> Proposal:
    return Proposal(
        identity=identity,
        content=content,
        content_hash=f"h:{content}",
        provenance=Provenance(origin=origin, rule=rule, statement="x is never null"),
        description="every x has a value",
        dataset=dataset,
        subject="x",
        rule=rule,
        backtest=backtest,
    )


# -- the memory, which is the point -----------------------------------------


def test_a_rejected_proposal_is_not_offered_again() -> None:
    """A miner re-proposing every Tuesday what was refused last Tuesday does
    not merely waste a minute; it teaches the reviewer that the queue is noise,
    and then the one proposal that mattered goes unread with the rest."""
    queue = ProposalQueue()
    queue.offer(proposal())
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)

    again = queue.offer(proposal())
    assert again.outcome == "suppressed"
    assert not again.admitted
    assert "a.sinha" in again.detail


def test_a_suppressed_proposal_returns_when_the_evidence_materially_changes() -> None:
    """ "You rejected this when 3% of rows failed; 40% fail now" is a different
    question from the one that was answered."""
    queue = ProposalQueue()
    queue.offer(proposal(backtest=Backtest(scanned=1000, violations=30)))
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)

    worse = queue.offer(proposal(backtest=Backtest(scanned=1000, violations=400)))
    assert worse.outcome == "reopened"
    assert "3.0%" in worse.detail
    assert "40.0%" in worse.detail


def test_a_small_drift_does_not_reopen_anything() -> None:
    """Re-asking about the same situation is exactly what trains people to stop
    reading."""
    queue = ProposalQueue()
    queue.offer(proposal(backtest=Backtest(scanned=1000, violations=30)))
    queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)
    assert (
        queue.offer(proposal(backtest=Backtest(scanned=1000, violations=35))).outcome
        == "suppressed"
    )


def test_a_rule_rejected_as_incorrect_never_comes_back() -> None:
    """It is wrong however the data changes, and re-offering it when the data
    shifts would answer a question about the rule with evidence about the
    data."""
    queue = ProposalQueue()
    queue.offer(proposal(backtest=Backtest(scanned=1000, violations=10)))
    queue.reject("P1", "a.sinha", NOW, RejectionReason.INCORRECT)
    assert (
        queue.offer(proposal(backtest=Backtest(scanned=1000, violations=900))).outcome
        == "suppressed"
    )


def test_a_control_rejected_as_too_noisy_returns_when_it_becomes_quiet() -> None:
    """The reopening runs in both directions: the objection was the volume, and
    the volume is what changed."""
    queue = ProposalQueue()
    queue.offer(proposal(backtest=Backtest(scanned=1000, violations=400)))
    queue.reject("P1", "a.sinha", NOW, RejectionReason.TOO_NOISY)
    quiet = queue.offer(proposal(backtest=Backtest(scanned=1000, violations=20)))
    assert quiet.outcome == "reopened"
    assert "too noisy" in quiet.detail


def test_a_rejection_must_say_why() -> None:
    """The reason decides what happens next, and "wrong" and "right but not
    worth it" lead somewhere completely different."""
    with pytest.raises(TypeError):
        ProposalQueue().reject("P1", "a", NOW)  # type: ignore[call-arg]


# -- corroboration ----------------------------------------------------------


def test_two_origins_reaching_the_same_rule_merge_rather_than_duplicate() -> None:
    """Dropping one discards the most interesting thing that can happen here."""
    queue = ProposalQueue()
    queue.offer(proposal(origin=Origin.DECLARATION, rule="grain.completeness"))
    second = queue.offer(proposal(origin=Origin.MINING, rule="mine.not_null"))
    assert second.outcome == "corroborated"
    assert second.proposal is not None
    assert second.proposal.origin is Origin.DECLARATION
    assert second.proposal.provenance.is_corroborated


def test_the_stronger_origin_keeps_the_proposal() -> None:
    """Order of arrival must not decide which source gets the credit."""
    queue = ProposalQueue()
    queue.offer(proposal(origin=Origin.MINING))
    merged = queue.offer(proposal(origin=Origin.DECLARATION))
    assert merged.proposal is not None
    assert merged.proposal.origin is Origin.DECLARATION


def test_the_same_proposal_from_the_same_source_is_just_a_duplicate() -> None:
    queue = ProposalQueue()
    queue.offer(proposal())
    assert queue.offer(proposal()).outcome == "duplicate"


# -- revision rather than accumulation ---------------------------------------


def test_re_proposing_a_live_control_unchanged_is_recognised_as_such() -> None:
    queue = ProposalQueue()
    queue.register_existing("P1", "h:CHECK t.x IS NOT NULL")
    assert queue.offer(proposal()).outcome == "already_live"


def test_a_changed_proposal_for_a_live_control_is_a_revision_not_an_addition() -> None:
    """Presenting it as new would grow the estate by one control that does the
    same job as another; dropping it would hide a real change."""
    queue = ProposalQueue()
    queue.register_existing("P1", "h:old")
    admission = queue.offer(proposal())
    assert admission.outcome == "superseded"
    assert "replaces rather than adds" in admission.detail


def test_a_newer_proposal_supersedes_an_undecided_older_one() -> None:
    queue = ProposalQueue()
    queue.offer(proposal(content="CHECK t.x IS NOT NULL"))
    newer = queue.offer(proposal(content="CHECK t.x IS NOT NULL AND t.x <> ''"))
    assert newer.outcome == "superseded"
    assert len(queue.pending()) == 1


# -- what may run without a person ------------------------------------------


def test_only_a_declaration_may_run_without_review() -> None:
    queue = ProposalQueue()
    queue.offer(proposal(identity="D", origin=Origin.DECLARATION))
    queue.offer(proposal(identity="M", origin=Origin.MINING, content="CHECK t.y IS NOT NULL"))
    assert [p.identity for p in queue.auto_activatable()] == ["D"]


def test_not_even_a_declaration_may_run_if_it_would_drown_the_queue() -> None:
    """A control that would fire on half the rows is not the control the
    declarer meant, however clearly they declared it. It means the data does
    not match the declaration, which is a conversation rather than an alert."""
    queue = ProposalQueue()
    queue.offer(
        proposal(
            origin=Origin.DECLARATION,
            backtest=Backtest(scanned=1000, violations=500),
        )
    )
    assert queue.auto_activatable() == []


# -- decisions ---------------------------------------------------------------


def test_accepting_removes_it_from_the_queue_and_teaches_the_ranker() -> None:
    queue = ProposalQueue()
    queue.offer(proposal())
    queue.accept("P1", "a.sinha", NOW)
    assert queue.pending() == []
    assert queue.history.observations("rule:mine.not_null") == 1


def test_deferring_keeps_it_but_out_of_the_working_list() -> None:
    """A deferred proposal comes back; a rejected one does not, and collapsing
    the two loses the distinction that matters."""
    queue = ProposalQueue()
    queue.offer(proposal())
    queue.defer("P1", "waiting on the grain declaration")
    assert queue.pending() == []
    assert queue.deferred()[0].status is ProposalStatus.DEFERRED


def test_deciding_a_proposal_that_is_not_open_says_which_way_it_went() -> None:
    queue = ProposalQueue()
    queue.offer(proposal())
    queue.accept("P1", "a.sinha", NOW)
    with pytest.raises(KeyError, match="already decided"):
        queue.accept("P1", "a.sinha", NOW)
    with pytest.raises(KeyError, match="never offered"):
        queue.accept("nope", "a.sinha", NOW)


def test_a_suppression_can_be_rebuilt_from_a_decided_proposal() -> None:
    """So a queue reloaded from storage remembers what it was told."""
    queue = ProposalQueue()
    queue.offer(proposal(backtest=Backtest(scanned=100, violations=5)))
    rejected = queue.reject("P1", "a.sinha", NOW, RejectionReason.NOT_MATERIAL)

    reloaded = ProposalQueue()
    reloaded.remember_rejection(suppression_from(rejected))
    assert reloaded.offer(proposal()).outcome == "suppressed"


def test_only_a_rejection_produces_a_suppression() -> None:
    queue = ProposalQueue()
    queue.offer(proposal())
    accepted = queue.accept("P1", "a.sinha", NOW)
    with pytest.raises(ValueError, match="only a rejected proposal"):
        suppression_from(accepted)


# -- reporting ---------------------------------------------------------------


def test_the_summary_names_what_a_person_should_act_on() -> None:
    queue = ProposalQueue()
    queue.offer(proposal(identity="A"))
    queue.offer(
        proposal(
            identity="B",
            content="CHECK t.y IS NOT NULL",
            backtest=Backtest(scanned=100, violations=60),
        )
    )
    summary = queue.summary()
    assert summary["pending"] == 2
    assert summary["would_be_too_noisy"] == 1
    assert summary["by_origin"]["mining"] == 2


def test_a_suppression_records_what_would_change_its_mind() -> None:
    suppression = Suppression(
        identity="P1",
        reason=RejectionReason.NOT_MATERIAL,
        decided_by="a.sinha",
        decided_at=NOW,
        violation_rate=0.02,
    )
    assert not suppression.is_permanent
    assert suppression.reopened_by(0.30)
    assert not suppression.reopened_by(0.025)
