"""The standalone agent's fixtures: a real SQLite source, real assignments, a fake server.

The assignments are compiled by the server's own compiler (`assignment_for`),
so the daemon is tested on the SQL a server would actually send, not on SQL
written to suit it. The server is a fake `FleetLink` that keeps what it was
sent and checks the agent's hash chain, which is how "delivered with no loss"
is asserted rather than assumed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from prama_agent.config import AgentConfig, parse_config
from prama_agent.link import LinkUnavailable
from prama_agent.state import Identity
from prama_kernel.agent.protocol import Assignment, Hello, Receipt, Refusal, Report
from prama_kernel.agent.signing import sign_payload
from prama_kernel.record import GENESIS, EvidenceRecord

from prama.agent.assign import assignment_for
from prama.ir.resolve import resolved
from prama.pql import parse_control

KEY = bytes.fromhex("11" * 32)
#: A value that must never leave the machine, planted in the failing rows.
SECRET = "ACC-SECRET-7731"


def make_source(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(
        f"""
        CREATE TABLE trades (trade_id INTEGER, account_id TEXT, amount REAL, ccy TEXT);
        INSERT INTO trades VALUES (1, 'ACC-1', 10.0, 'EUR');
        INSERT INTO trades VALUES (2, '{SECRET}', NULL, 'EUR');
        INSERT INTO trades VALUES (3, 'ACC-3', NULL, 'USD');
        INSERT INTO trades VALUES (4, 'ACC-4', 4.0, 'GBP');
        """
    )
    connection.commit()
    connection.close()
    return path


def an_assignment(source: str, *, dataset: str = "trades") -> Assignment:
    plan = resolved(parse_control(source))
    assignment = assignment_for(plan, "sqlite", control_id=f"ctl-{plan.plan_id[:8]}")
    assert assignment.dataset == dataset
    return assignment


def amount_present() -> Assignment:
    """Fails on this data: two trades have no amount."""
    return an_assignment("CHECK trades.amount IS NOT NULL BECAUSE 'every trade has an amount'")


def ccy_present() -> Assignment:
    """Passes on this data."""
    return an_assignment("CHECK trades.ccy IS NOT NULL BECAUSE 'every trade has a currency'")


def account_known() -> Assignment:
    """Fails on one row, and that row's sample carries `SECRET`."""
    return an_assignment(
        "CHECK trades.account_id IN ('ACC-1', 'ACC-3', 'ACC-4') BECAUSE 'known accounts only'"
    )


def config_for(tmp_path: Path, **residency: Any) -> AgentConfig:
    policy = residency or {"samples": "mask", "may_send": ["trade_id"]}
    return parse_config(
        {
            "server": {"url": "https://prama.example.com"},
            "state_dir": str(tmp_path / "state"),
            "sources": {"trades": {"engine": "sqlite", "path": str(tmp_path / "w.db")}},
            "residency": policy,
            "poll": {"min_seconds": 1, "max_seconds": 60, "backoff_initial_seconds": 2},
        }
    )


IDENTITY = Identity(
    agent_id="agt-01",
    key_hex=KEY.hex(),
    zone="eu-frankfurt",
    server="https://prama.example.com",
    name="eu-01",
)


class FakeServer:
    """A `FleetLink` that behaves as the contract says the server does.

    Hands out queued assignments on hello, dedupes reports by sequence, rejects
    a jump, and checks each record links to the one before — so a finding lost
    anywhere between the agent and here fails the test.
    """

    def __init__(self, assignments: list[Assignment] | None = None) -> None:
        self.queue = list(assignments or [])
        self.records: list[EvidenceRecord] = []
        self.gaps: list[dict[str, Any]] = []
        self.raw_reports: list[dict[str, Any]] = []
        self.hellos: list[dict[str, Any]] = []
        self.accepted = -1
        self.head = GENESIS
        self.down = False
        self.hello_down = False
        self.refusal: Refusal | None = None
        self.poll_after = 7
        self.closed = False

    # -- FleetLink ------------------------------------------------------------

    def enrol(
        self, token: str, *, name: str, version: str, capabilities: dict[str, Any]
    ) -> dict[str, Any]:
        if token != "tok-1":
            raise LinkUnavailable("unknown token", remedy="ask for another")
        self.enrolled = {"name": name, "version": version, "capabilities": capabilities}
        return {"agent_id": "agt-01", "key": KEY.hex(), "zone": "eu-frankfurt",
                "poll_after_seconds": 15}  # fmt: skip

    def hello(self, hello: dict[str, Any], *, key: bytes) -> dict[str, Any]:
        if self.down or self.hello_down:
            raise LinkUnavailable("connection refused", remedy="wait")
        message = Hello.from_dict(hello)
        # What the SDK would put in X-Prama-Signature verifies over the rebuilt message.
        assert sign_payload(key, message.signable()) == sign_payload(KEY, message.signable())
        self.hellos.append(hello)
        if self.refusal is not None:
            return self.refusal.to_dict()
        handed, self.queue = self.queue, []
        return Receipt(
            accepted_through=self.accepted,
            assignments=tuple(handed),
            poll_after_seconds=self.poll_after,
        ).to_dict()

    def report(self, report: dict[str, Any], *, key: bytes) -> dict[str, Any]:
        if self.down:
            raise LinkUnavailable("connection reset", remedy="wait")
        if self.refusal is not None:
            return self.refusal.to_dict()
        self.raw_reports.append(report)
        message = Report.from_dict(report)
        duplicates = 0
        for record in message.records:
            if record.sequence <= self.accepted:
                duplicates += 1
                continue
            assert record.sequence == self.accepted + 1, "a finding went missing"
            assert record.previous_hash == self.head, "the agent's chain is broken"
            self.records.append(record)
            self.accepted, self.head = record.sequence, record.record_hash
        self.gaps.extend(g.to_dict() for g in message.gaps)
        return Receipt(accepted_through=self.accepted, duplicates=duplicates).to_dict()

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return make_source(tmp_path / "w.db")


@pytest.fixture
def config(tmp_path: Path, source: Path) -> AgentConfig:
    return config_for(tmp_path)


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


def replace_residency(config: AgentConfig, **policy: Any) -> AgentConfig:
    fresh = parse_config({"server": "https://x.example", "state_dir": "/", "sources": {
        "s": {"engine": "sqlite", "path": "/x"}}, "residency": policy})  # fmt: skip
    return dataclasses.replace(config, residency=fresh.residency)
