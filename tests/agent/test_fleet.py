"""Enrolment, trust, capability and the outbound-only conversation.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from prama.agent import (
    Agent,
    AgentCapabilities,
    AgentRegistry,
    AgentState,
    Assignment,
    Coordinator,
    Receipt,
    Refusal,
    ResidencyPolicy,
    SampleDisposition,
    Spool,
    fits,
    fleet_health,
)
from prama.core.clock import Clock
from prama.core.errors import ValidationError
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control


class Movable(Clock):
    def __init__(self) -> None:
        self._now = datetime(2026, 4, 2, 6, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)

    def monotonic(self) -> float:
        return 0.0

    def epoch_millis(self) -> int:
        return int(self._now.timestamp() * 1000)


def enrol(registry: AgentRegistry, zone: str = "eu-frankfurt"):
    _, secret = registry.issue_token(zone, issued_by="a.roy")
    return registry.enrol(secret.reveal(), name=f"{zone}-01", version="1.0.0")


def an_agent(registry: AgentRegistry, **changes):
    identity, key = enrol(registry)
    options: dict = {
        "executor": lambda _sql: [{"scanned_rows": 8, "violating_rows": 1}],
        "residency": ResidencyPolicy(
            zone=identity.zone, samples=SampleDisposition.MASK, may_send=("account_id",)
        ),
        "capabilities": AgentCapabilities(engines=("sqlite",)),
    }
    options.update(changes)
    return identity, Agent(identity.agent_id, bytes.fromhex(key.reveal()), **options)


def an_assignment(plan_source: str = "CHECK t.a IS NOT NULL BECAUSE 'x'") -> tuple:
    plan = Lowerer().control(parse_control(plan_source))
    return plan, Assignment(
        plan_id=plan.plan_id,
        dataset=plan.scope.dataset,
        binding=plan.scope.dataset,
        engine="sqlite",
        metric_query="SELECT 1",
        metric_names=("scanned_rows", "violating_rows"),
        plan=plan.to_dict(),
    )


class TestEnrolment:
    def test_a_token_is_redeemed_once(self) -> None:
        # A replayable token is a credential that never expires, handed out
        # over whatever channel installed the agent.
        registry = AgentRegistry()
        _, secret = registry.issue_token("eu")
        registry.enrol(secret.reveal())
        with pytest.raises(ValidationError, match="already redeemed"):
            registry.enrol(secret.reveal())

    def test_an_expired_token_is_refused(self) -> None:
        clock = Movable()
        registry = AgentRegistry(clock=clock)
        _, secret = registry.issue_token("eu", minutes=10)
        clock.advance(minutes=11)
        with pytest.raises(ValidationError, match="expired"):
            registry.enrol(secret.reveal())

    def test_an_unknown_token_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not one this control plane issued"):
            AgentRegistry().enrol("made-up")

    def test_the_zone_is_fixed_at_issue_not_chosen_by_the_agent(self) -> None:
        # An agent that named its own zone could name the one with the
        # interesting data.
        registry = AgentRegistry()
        _, secret = registry.issue_token("reporting")
        identity, _ = registry.enrol(secret.reveal(), name="anything")
        assert identity.zone == "reporting"

    def test_a_token_needs_a_zone(self) -> None:
        with pytest.raises(ValidationError, match="needs a zone"):
            AgentRegistry().issue_token("")

    def test_the_registry_keeps_a_digest_not_the_key(self) -> None:
        # A registry that could reproduce the credential would be a registry
        # whose theft is an agent fleet.
        registry = AgentRegistry()
        identity, key = enrol(registry)
        assert key.reveal() not in str(identity.to_dict())
        assert identity.key_digest != key.reveal()


class TestTrust:
    def test_a_correct_signature_verifies(self) -> None:
        registry = AgentRegistry()
        identity, _ = enrol(registry)
        signature = registry.sign_as(identity.agent_id, "payload")
        assert registry.verify(identity.agent_id, "payload", signature)

    def test_a_revoked_agent_fails_even_with_a_correct_signature(self) -> None:
        # Verifying the signature and then accepting the finding anyway is how
        # a revocation list becomes decorative.
        registry = AgentRegistry()
        identity, _ = enrol(registry)
        signature = registry.sign_as(identity.agent_id, "payload")
        registry.revoke(identity.agent_id)
        assert not registry.verify(identity.agent_id, "payload", signature)

    def test_revocation_destroys_the_key(self) -> None:
        registry = AgentRegistry()
        identity, _ = enrol(registry)
        registry.revoke(identity.agent_id)
        with pytest.raises(ValidationError, match="no signing key"):
            registry.sign_as(identity.agent_id, "payload")

    def test_a_suspended_agent_may_not_report_but_may_be_resumed(self) -> None:
        registry = AgentRegistry()
        identity, _ = enrol(registry)
        registry.suspend(identity.agent_id)
        assert not registry.get(identity.agent_id).state.may_report  # type: ignore[union-attr]
        registry.resume(identity.agent_id)
        assert registry.get(identity.agent_id).state is AgentState.ACTIVE  # type: ignore[union-attr]


class TestSilence:
    def test_an_agent_that_stops_calling_is_reported(self) -> None:
        # Silence is reported rather than inferred from missing evidence: a
        # dead agent and a clean estate produce the same absence of findings,
        # and only one is a problem.
        clock = Movable()
        registry = AgentRegistry(clock=clock)
        identity, _ = enrol(registry)
        assert registry.stale() == []
        clock.advance(minutes=20)
        assert [a.agent_id for a in registry.stale()] == [identity.agent_id]

    def test_fleet_health_summarises_it(self) -> None:
        clock = Movable()
        registry = AgentRegistry(clock=clock)
        enrol(registry)
        clock.advance(hours=2)
        health = fleet_health(registry)
        assert health["agents"] == 1
        assert "silent" in health["summary"]


class TestCapabilityNegotiation:
    def test_a_plan_the_agent_cannot_run_is_unassignable(self) -> None:
        plan, _ = an_assignment(r"CHECK t.a MATCHES /^x/ BECAUSE 'x'")
        fitness = fits(
            plan,
            AgentCapabilities(engines=("sqlite",), pushdown=("pushdown.filter",)),
            engine="sqlite",
        )
        assert not fitness.assignable
        assert "pushdown.regex" in fitness.render()

    def test_every_reason_is_collected_not_the_first(self) -> None:
        # An agent short of three things needs upgrading once, not three times.
        plan, _ = an_assignment(r"CHECK t.a MATCHES /^x/ BECAUSE 'x'")
        fitness = fits(
            plan,
            AgentCapabilities(
                ir_versions=("0.9",), engines=("duckdb",), pushdown=("pushdown.filter",)
            ),
            engine="sqlite",
        )
        assert len(fitness.reasons) >= 3

    def test_an_agent_confined_to_datasets_is_not_given_others(self) -> None:
        plan, _ = an_assignment()
        fitness = fits(plan, AgentCapabilities(datasets=("other",)))
        assert not fitness.assignable
        assert "confined to" in fitness.render()

    def test_an_agent_with_no_declared_pushdown_is_not_second_guessed(self) -> None:
        # An older agent that declares nothing is assumed to manage, because
        # the alternative is that every agent stops working the day the
        # control plane learns a new capability name.
        plan, _ = an_assignment()
        assert fits(plan, AgentCapabilities()).assignable


class TestTheConversation:
    def test_an_agent_asks_and_receives_work(self) -> None:
        registry = AgentRegistry()
        identity, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        plan, assignment = an_assignment()
        coordinator.enqueue(identity.zone, plan, assignment)

        message, signature = agent.hello()
        response = coordinator.hello(message, signature)
        assert isinstance(response, Receipt)
        assert [a.plan_id for a in response.assignments] == [plan.plan_id]

    def test_work_is_assigned_by_zone_not_by_request(self) -> None:
        # A compromised agent in the reporting zone must not be able to obtain
        # the trading estate's controls.
        registry = AgentRegistry()
        identity, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        plan, assignment = an_assignment()
        coordinator.enqueue("trading", plan, assignment)

        message, signature = agent.hello()
        response = coordinator.hello(message, signature)
        assert isinstance(response, Receipt)
        assert response.assignments == ()

    def test_a_revoked_agent_is_refused_permanently(self) -> None:
        registry = AgentRegistry()
        identity, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        registry.revoke(identity.agent_id)

        message, signature = agent.hello()
        response = coordinator.hello(message, signature)
        assert isinstance(response, Refusal)
        assert response.permanent
        # The agent stops rather than retrying forever.
        assert agent.apply(response) is False

    def test_a_suspension_is_temporary_and_the_agent_keeps_working(self) -> None:
        registry = AgentRegistry()
        identity, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        registry.suspend(identity.agent_id)

        message, signature = agent.hello()
        response = coordinator.hello(message, signature)
        assert isinstance(response, Refusal)
        assert not response.permanent
        assert agent.apply(response) is True

    def test_a_forged_signature_is_refused(self) -> None:
        registry = AgentRegistry()
        _, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        message, _ = agent.hello()
        response = coordinator.hello(message, "0" * 64)
        assert isinstance(response, Refusal)
        assert "not signed by that agent's key" in response.reason

    def test_an_unknown_agent_is_refused(self) -> None:
        coordinator = Coordinator(AgentRegistry())
        registry = AgentRegistry()
        _, agent = an_agent(registry)
        message, signature = agent.hello()
        response = coordinator.hello(message, signature)
        assert isinstance(response, Refusal)
        assert "does not know that agent" in response.reason


class TestFindings:
    def test_findings_reach_the_ledger_and_the_chain_holds(self) -> None:
        registry = AgentRegistry()
        identity, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        _, assignment = an_assignment()
        for _ in range(3):
            agent.run(assignment)

        report, signature = agent.report()
        response = coordinator.report(report, signature)
        assert isinstance(response, Receipt)
        assert response.accepted_through == 2
        assert len(coordinator.ledger) == 3
        assert coordinator.ledger.verify().is_intact

    def test_an_acknowledged_batch_leaves_the_spool(self) -> None:
        registry = AgentRegistry()
        _, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        _, assignment = an_assignment()
        agent.run(assignment)
        report, signature = agent.report()
        agent.apply(coordinator.report(report, signature))
        assert len(agent.spool) == 0

    def test_redelivery_is_deduplicated_rather_than_duplicated(self) -> None:
        # At-least-once delivery means an agent that heard nothing must send
        # again. Claiming exactly-once would mean losing evidence to preserve
        # the claim.
        registry = AgentRegistry()
        _, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        _, assignment = an_assignment()
        agent.run(assignment)

        report, signature = agent.report()
        coordinator.report(report, signature)  # first delivery, receipt lost
        second = coordinator.report(report, signature)
        assert isinstance(second, Receipt)
        assert second.duplicates == 1
        assert len(coordinator.ledger) == 1

    def test_an_execution_failure_becomes_an_error_verdict_with_a_reason(self) -> None:
        # An agent that stopped on the first unreadable source would take the
        # rest of its zone's controls down with it.
        def broken(sql: str):
            raise RuntimeError("connection refused")

        registry = AgentRegistry()
        _, agent = an_agent(registry, executor=broken)
        _, assignment = an_assignment()
        outcome = agent.run(assignment)
        assert outcome.record is not None
        assert outcome.record.verdict == "error"
        assert "connection refused" in outcome.record.detail


class TestSurvivingAnOutage:
    def test_the_agent_keeps_working_while_the_control_plane_is_unreachable(self) -> None:
        # The estate goes unchecked precisely during the incident that took the
        # network out, and the gap is exactly where an auditor will look.
        registry = AgentRegistry()
        _, agent = an_agent(registry)
        _, assignment = an_assignment()
        for _ in range(200):
            agent.run(assignment)
        assert len(agent.spool) == 200

    def test_everything_is_delivered_when_it_comes_back(self) -> None:
        registry = AgentRegistry()
        _, agent = an_agent(registry)
        coordinator = Coordinator(registry)
        _, assignment = an_assignment()
        for _ in range(120):
            agent.run(assignment)

        while len(agent.spool):
            report, signature = agent.report(batch_size=50)
            agent.apply(coordinator.report(report, signature))
        assert len(coordinator.ledger) == 120
        assert coordinator.ledger.verify().is_intact

    def test_an_overflowing_spool_drops_the_oldest_and_records_the_gap(self) -> None:
        # Dropping the newest would be easier and would mean a long outage
        # hides the recent failures rather than the old ones.
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=10))
        _, assignment = an_assignment()
        for _ in range(15):
            agent.run(assignment)
        assert len(agent.spool) == 10
        assert agent.spool.gaps
        assert agent.spool.gaps[0].first_sequence == 0
        assert "capacity" in agent.spool.gaps[0].reason

    def test_the_spool_survives_a_restart(self, tmp_path) -> None:
        registry = AgentRegistry()
        path = tmp_path / "spool.json"
        _, agent = an_agent(registry, spool=Spool(path=path))
        _, assignment = an_assignment()
        for _ in range(5):
            agent.run(assignment)

        restarted = Spool(path=path)
        assert len(restarted) == 5
        assert restarted.head == agent.spool.head

    def test_a_corrupt_spool_is_a_gap_not_a_crash(self, tmp_path) -> None:
        # Refusing to start would leave the estate unchecked over exactly the
        # kind of incident that corrupted it.
        path = tmp_path / "spool.json"
        path.write_text("{ not json", encoding="utf-8")
        spool = Spool(path=path)
        assert len(spool) == 0
        assert spool.gaps
        assert "could not be read" in spool.gaps[0].reason


class TestDataStaysHome:
    def test_no_row_value_reaches_the_control_plane_under_a_withhold_policy(self) -> None:
        registry = AgentRegistry()
        identity, agent = an_agent(
            registry,
            executor=lambda sql: (
                [{"scanned_rows": 8, "violating_rows": 1}]
                if "COUNT" in sql or "scanned" in sql
                else [{"account_id": "A1", "lei": "5493001KJTIIGC8Y1R12"}]
            ),
            residency=ResidencyPolicy(
                zone="eu-frankfurt",
                samples=SampleDisposition.WITHHOLD,
                investigate_at="frankfurt-01",
            ),
        )
        coordinator = Coordinator(registry)
        _, assignment = an_assignment()
        agent.run(assignment)
        report, signature = agent.report()
        coordinator.report(report, signature)
        exported = coordinator.ledger.export()
        assert "5493001KJTIIGC8Y1R12" not in exported
        assert "A1" not in exported

    def test_the_report_carries_the_policy_so_the_server_knows_why(self) -> None:
        # A record with no samples because residency forbade them is a
        # different thing from one with none because the control passed.
        registry = AgentRegistry()
        _, agent = an_agent(
            registry,
            residency=ResidencyPolicy(
                zone="pci", samples=SampleDisposition.WITHHOLD, investigate_at="pci-1"
            ),
        )
        report, _ = agent.report()
        assert report.residency["samples"] == "withhold"
        assert "pci-1" in report.residency["describes"]

    def test_withheld_samples_are_still_available_where_the_data_is(self) -> None:
        # Withholding from the control plane is not discarding: an
        # investigator in the zone still needs the rows.
        registry = AgentRegistry()
        _, agent = an_agent(
            registry,
            executor=lambda sql: (
                [{"scanned_rows": 8, "violating_rows": 1}]
                if sql.strip()[-1] == "1"
                else [{"account_id": "A1"}]
            ),
            residency=ResidencyPolicy(zone="pci", samples=SampleDisposition.WITHHOLD),
        )
        plan, assignment = an_assignment()
        assignment = dataclasses.replace(assignment, sample_query="SELECT account_id FROM t")
        outcome = agent.run(assignment)
        assert outcome.record is not None
        assert outcome.record.sample_count == 1
        assert outcome.record.samples_digest == ""  # nothing crossed


class TestGapsAreOneHoleNotMany:
    """Eviction happens per record; a long overflow is still one hole."""

    def test_contiguous_drops_merge(self) -> None:
        # Forty separate gaps of one finding each is a report nobody can read.
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=10))
        _, assignment = an_assignment()
        for _ in range(50):
            agent.run(assignment)
        assert len(agent.spool.gaps) == 1
        assert agent.spool.gaps[0].count == 40

    def test_a_gap_reads_as_a_range(self) -> None:
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=5))
        _, assignment = an_assignment()
        for _ in range(20):
            agent.run(assignment)
        rendered = agent.spool.gaps[0].render()
        assert "15 finding(s)" in rendered
        assert "sequences 0 to 14" in rendered

    def test_a_delivered_gap_is_forgotten_and_a_later_one_is_new(self) -> None:
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=5))
        _, assignment = an_assignment()
        for _ in range(10):
            agent.run(assignment)
        delivered = agent.spool.gaps
        assert delivered
        assert agent.spool.forget_gaps(delivered) == len(delivered)
        assert agent.spool.gaps == ()
        for _ in range(10):
            agent.run(assignment)
        assert len(agent.spool.gaps) == 1

    def test_a_gap_recorded_after_the_report_is_not_forgotten_with_it(self) -> None:
        """Finding X3, the first of its two halves.

        `apply()` called `take_gaps()`, which cleared *every* gap the spool
        held. A gap recorded between building a report and receiving its
        receipt had therefore never been sent to anybody, and was deleted as
        though it had.

        A gap is the record of evidence this agent dropped. Losing it does not
        lose a log line — it makes the estate under-report while looking
        complete, which is the failure `Gap` exists to prevent.
        """
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=5))
        _, assignment = an_assignment()
        for _ in range(10):
            agent.run(assignment)

        agent.report()  # the gaps so far are now in flight
        reported = agent.spool.gaps
        assert reported
        reported_through = reported[-1].last_sequence

        # More overflow, after the report was built and before its receipt. The
        # spool coalesces a continuing overflow into the *same* gap rather than
        # accumulating one per dropped finding — "one hole, not many" — so what
        # grows is its range, and the hole the control plane was told about is
        # no longer the hole the spool holds.
        for _ in range(10):
            agent.run(assignment)
        assert agent.spool.gaps[-1].last_sequence > reported_through

        agent.apply(Receipt(accepted_through=0))
        assert agent.spool.gaps, "a gap that was never reported was deleted anyway"
        assert agent.spool.gaps[-1].last_sequence > reported_through

    def test_a_hello_receipt_does_not_delete_an_unreported_gap(self) -> None:
        """The second half, and the worse one.

        `apply()` is the single handler for both `Hello` and `Report`
        responses, and `Coordinator.hello` returns the previously accepted
        sequence — so once an agent had delivered anything, *every subsequent
        poll* cleared every gap it held, whether or not a report had carried
        them.
        """
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=5))
        _, assignment = an_assignment()
        for _ in range(10):
            agent.run(assignment)
        assert agent.spool.gaps

        # A receipt arriving without a report having been sent.
        agent.apply(Receipt(accepted_through=0))
        assert agent.spool.gaps, "a hello receipt deleted gaps nobody had been told about"

    def test_a_reported_gap_is_still_forgotten_once_acknowledged(self) -> None:
        """The counterfactual. A spool that never forgets a delivered gap
        reports the same hole for ever, and the control plane cannot tell a
        recurring problem from an old one."""
        registry = AgentRegistry()
        _, agent = an_agent(registry, spool=Spool(capacity=5))
        _, assignment = an_assignment()
        for _ in range(10):
            agent.run(assignment)
        assert agent.spool.gaps

        agent.report()
        agent.apply(Receipt(accepted_through=0))
        assert agent.spool.gaps == (), "a delivered gap was reported twice"
