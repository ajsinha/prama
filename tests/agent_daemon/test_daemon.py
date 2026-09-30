"""The daemon's loop against a fake server: run, report, spool, back off, stop.

Every assignment here was compiled by the server's compiler and runs against a
real SQLite file, and every verdict asserted is the executed one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import signal
from pathlib import Path

import pytest
from prama_agent.config import AgentConfig, Source
from prama_agent.daemon import EXIT_OK, EXIT_REFUSED, Daemon
from prama_agent.executors import Executors, SqliteExecutor
from prama_agent.state import SPOOL, load_contact
from prama_kernel.agent.protocol import Refusal
from prama_kernel.errors import ConfigError
from prama_kernel.record import GENESIS
from tests.agent_daemon.conftest import (
    IDENTITY,
    SECRET,
    FakeServer,
    account_known,
    amount_present,
    ccy_present,
    replace_residency,
)


def daemon(config: AgentConfig, server: FakeServer, **options: object) -> Daemon:
    return Daemon(config, IDENTITY, server, rng=random.Random(7), **options)  # type: ignore[arg-type]


class TestACycle:
    def test_assignments_run_and_their_findings_reach_the_server(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        server.queue = [amount_present(), ccy_present()]
        result = daemon(config, server).cycle()

        assert result.ran == 2 and result.delivered == 2 and result.contacted
        verdicts = {r.dataset + ":" + r.verdict for r in server.records}
        assert verdicts == {"trades:fail", "trades:pass"}
        failing = next(r for r in server.records if r.verdict == "fail")
        assert failing.metrics["violating_rows"] == 2  # the executed count, on real rows
        assert failing.triggered_by == "agent:agt-01"
        assert [r.sequence for r in server.records] == [0, 1]

    def test_the_hello_carries_capabilities_derived_from_the_configuration(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        daemon(config, server).cycle()
        (hello,) = server.hellos
        assert hello["agent_id"] == "agt-01"
        assert hello["capabilities"]["engines"] == ["sqlite"]
        assert hello["capabilities"]["max_concurrency"] == 1 == hello["free_slots"]

    def test_the_wait_is_the_servers_poll_within_the_configured_bounds(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        server.poll_after = 7
        assert daemon(config, server).cycle().wait_seconds == 7
        server.poll_after = 0
        assert daemon(config, server).cycle().wait_seconds == 1  # poll.min_seconds
        server.poll_after = 86_400
        assert daemon(config, server).cycle().wait_seconds == 60  # poll.max_seconds

    def test_a_source_that_fails_is_a_finding_not_a_crash(
        self, config: AgentConfig, server: FakeServer, source: Path
    ) -> None:
        source.unlink()
        server.queue = [amount_present()]
        result = daemon(config, server).cycle()
        assert result.ran == 1
        (record,) = server.records
        assert record.verdict == "error" and "w.db" in record.detail

    def test_an_assignment_for_a_source_this_agent_lacks_is_reported_as_an_error(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        # An empty router is falsy (it has a length): it must still be the router
        # used, not silently replaced by a missing single executor.
        server.queue = [amount_present()]
        daemon(config, server, executors=Executors.of({})).cycle()
        (record,) = server.records
        assert record.verdict == "error" and "no source bound to 'trades'" in record.detail


class TestWhenTheServerIsUnreachable:
    def test_findings_are_spooled_and_delivered_later_with_no_loss(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        server.queue = [amount_present(), ccy_present()]
        server.down = False
        first = daemon(config, server)
        # hello gets through; the report does not.
        original = server.report

        def unreachable(report: dict, *, key: bytes) -> dict:
            server.down = True
            try:
                return original(report, key=key)
            finally:
                server.down = False

        server.report = unreachable  # type: ignore[method-assign]
        result = first.cycle()
        assert result.ran == 2 and not result.contacted and result.wait_seconds > 0
        assert server.records == []
        # Durable: on disk, in the state directory, before anything was sent.
        spooled = json.loads((config.state_dir / SPOOL).read_text())
        assert [r["sequence"] for r in spooled["pending"]] == [0, 1]

        # The daemon restarts (a new process, the same state directory) and the
        # server is back. The old findings go with the new one, in order.
        server.report = original  # type: ignore[method-assign]
        server.queue = [amount_present()]
        second = daemon(config, server)
        assert len(second.spool) == 2
        second.cycle()
        assert [r.sequence for r in server.records] == [0, 1, 2]
        assert server.records[0].previous_hash == GENESIS  # one unbroken chain
        assert len(second.spool) == 0

    def test_the_fake_server_would_notice_a_lost_finding(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        """The counterfactual for the test above: a gap in what arrives fails it."""
        server.queue = [amount_present(), ccy_present()]
        agent = daemon(config, server)
        agent.agent.run(amount_present())
        agent.agent.run(ccy_present())
        message, _ = agent.agent.report()
        payload = message.to_dict()
        del payload["records"][0]  # lose the first finding in transit
        with pytest.raises(AssertionError, match="went missing"):
            server.report(payload, key=b"")

    def test_an_unreachable_hello_backs_off_and_recovers(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        agent = daemon(config, server)
        server.hello_down = True
        waits = [agent.cycle().wait_seconds for _ in range(4)]
        contact = load_contact(config.state_dir)
        assert contact.consecutive_failures == 4 and "refused" in contact.last_error
        assert contact.last_contact_at == ""
        # Exponential, capped at backoff_max_seconds, jittered into the upper half.
        for failures, wait in enumerate(waits, start=1):
            ceiling = min(config.poll.backoff_max_seconds, 2 * 2 ** (failures - 1))
            assert ceiling / 2 <= wait <= ceiling
        server.hello_down = False
        recovered = agent.cycle()
        assert recovered.contacted and recovered.wait_seconds == 7
        assert load_contact(config.state_dir).consecutive_failures == 0

    def test_jitter_spreads_a_fleet(self, config: AgentConfig, server: FakeServer) -> None:
        waits = {
            round(Daemon(config, IDENTITY, server, rng=random.Random(seed)).backoff(5), 3)
            for seed in range(20)
        }
        assert len(waits) > 10


class TestRefusal:
    def test_a_permanent_refusal_stops_the_daemon_for_good(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        server.refusal = Refusal("this agent was revoked", remedy="re-enrol", permanent=True)
        assert daemon(config, server).run(handle_signals=False) == EXIT_REFUSED
        assert len(server.hellos) == 1  # it did not keep calling
        assert load_contact(config.state_dir).refused["reason"] == "this agent was revoked"
        # And a restart by the service manager does not undo it.
        assert daemon(config, server).run(handle_signals=False) == EXIT_REFUSED
        assert len(server.hellos) == 1

    def test_a_temporary_refusal_waits_and_tries_again(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        server.refusal = Refusal("busy", permanent=False)
        result = daemon(config, server).cycle()
        assert result.refusal is not None and not result.refused_for_good
        assert result.wait_seconds > 0
        assert not load_contact(config.state_dir).refused


class TestStopping:
    def test_sigterm_finishes_the_assignment_in_hand_then_stops(
        self, config: AgentConfig, server: FakeServer, source: Path
    ) -> None:
        signals: list[int] = []

        class Terminated(SqliteExecutor):
            def batches(self, sql: str, size: int):  # type: ignore[no-untyped-def]
                if not signals:
                    signals.append(signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGTERM)  # arrives mid-assignment
                yield from super().batches(sql, size)

        terminated = Terminated(Source("trades", "sqlite", path=str(source)))
        executors = Executors.of({"trades": terminated})
        server.queue = [amount_present(), ccy_present(), amount_present()]
        before = signal.getsignal(signal.SIGTERM)

        status = daemon(config, server, executors=executors).run()

        assert status == EXIT_OK
        # The first finished and was delivered on the way out; the rest were not started.
        (record,) = server.records
        assert record.verdict == "fail" and record.metrics["violating_rows"] == 2
        assert signal.getsignal(signal.SIGTERM) == before  # the handler is put back

    def test_once_runs_one_cycle(self, config: AgentConfig, server: FakeServer) -> None:
        server.queue = [ccy_present()]
        assert daemon(config, server).run(once=True, handle_signals=False) == EXIT_OK
        assert len(server.hellos) == 1 and len(server.records) == 1


class TestResidency:
    @pytest.mark.parametrize(
        "policy",
        [
            {"samples": "withhold", "investigate_at": "the zone's workbench"},
            {"samples": "mask", "may_send": ["trade_id"]},
            {"samples": "fingerprint"},
        ],
    )
    def test_no_row_value_leaves_in_a_report(
        self, config: AgentConfig, server: FakeServer, source: Path, policy: dict
    ) -> None:
        # The counterfactual first: the failing rows really do hold the secret,
        # so a report carrying them would be caught below.
        rows = SqliteExecutor(Source("t", "sqlite", path=str(source)))(account_known().sample_query)
        assert any(SECRET in json.dumps(row) for row in rows)

        server.queue = [account_known()]
        daemon(replace_residency(config, **policy), server).cycle()

        (report,) = server.raw_reports
        assert SECRET not in json.dumps(report)
        assert report["residency"]["zone"] == "eu-frankfurt"  # the enrolled zone
        assert report["residency"]["samples"] == policy["samples"]
        (record,) = server.records
        assert record.sample_count == 1  # that samples exist is said, not what they are

    def test_a_withheld_sample_is_not_an_absent_one(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        server.queue = [account_known()]
        agent = daemon(replace_residency(config, samples="withhold"), server)
        agent.cycle()
        (record,) = server.records
        assert record.samples_digest == "" and record.sample_count == 1

        server.queue = [account_known()]  # same state, same server: one chain
        masked = daemon(replace_residency(config, samples="mask", may_send=["trade_id"]), server)
        masked.cycle()
        carried = server.records[1]
        assert carried.samples_digest.startswith("sha256:")
        # Held here whatever the policy: the rows stay for an investigator in the zone.
        assert len(masked.agent.local_samples(carried.samples_digest)) == 1

    def test_a_policy_written_for_another_zone_is_refused(
        self, config: AgentConfig, server: FakeServer
    ) -> None:
        wrong = replace_residency(config, samples="withhold", zone="us-east")
        wrong = dataclasses.replace(wrong, zone_declared=True)
        with pytest.raises(ConfigError, match="enrolled in eu-frankfurt"):
            daemon(wrong, server)
