"""From a failing run to one message, once, and a resolution when it passes.

`Router` existed with routing, deduplication, a digest and resolution, and the
server never built one: nothing turned a failing run into an alert and
nothing delivered a dispatch. These tests drive the whole path — a real run
writing real evidence, the pipeline reading it back from the ledger, the
dataset's declared steward as the recipient, a notifier receiving the message
— and the property that makes alerting tolerable: an incident still open is
not announced again, even by a router built afresh from the database.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest

from prama.alert import notify
from prama.alert.notify import DeliveryError, Message, Notifier, new_registry
from prama.alert.pipeline import AlertPipeline, alert_after_run, digest_if_due
from prama.alert.route import Change, Role, Router
from prama.core.clock import FixedClock
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.registry import Registry
from prama.db import Database
from prama.execute import ControlRun

pytestmark = pytest.mark.anyio

REPO_ROOT = Path(__file__).resolve().parents[2]

CRITICAL = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY critical DIMENSION completeness BECAUSE 'CDE for FRTB'"
)
MINOR = (
    "CHECK positions_eod.desk IS NOT NULL "
    "SEVERITY minor DIMENSION completeness BECAUSE 'nice to have'"
)


class Capture(Notifier):
    """Keeps every message, so a test asserts what was delivered."""

    plugin_key: ClassVar[str] = "capture"
    sent: ClassVar[list[Message]] = []

    def deliver(self, message: Message) -> None:
        Capture.sent.append(message)


class Broken(Notifier):
    plugin_key: ClassVar[str] = "broken"

    def deliver(self, message: Message) -> None:
        raise DeliveryError("the relay is down", remedy="Bring the relay back.")


@pytest.fixture
def registry() -> Registry[Notifier]:
    Capture.sent = []
    built = new_registry()
    built.register(Capture)
    built.register(Broken)
    return built


def alerts_config(channel: str = "capture", **alerts: Any) -> Configuration:
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "alerts": {
                    "enabled": True,
                    "channels": {"owner": channel, "steward": channel, "custodian": channel},
                    **alerts,
                }
            },
            name="test",
        )
        .build()
    )


async def declare_estate(
    database: Database, tenant_id: str, pql: str = CRITICAL, *, jurisdiction: str | None = None
) -> str:
    """A dataset with an owner, a steward and a custodian, and one live control."""
    async with database.unit_of_work() as uow:
        people = {
            role: uow.principals.create(
                tenant_id=tenant_id,
                username=role,
                display_name=role.title(),
                email=f"{role}@example.com",
            )
            for role in ("olive", "sam", "carl")
        }
        await uow.flush()
        await uow.datasets.create(
            tenant_id=tenant_id,
            name="Positions EOD",
            slug="positions_eod",
            owner_id=str(people["olive"].id),
            steward_id=str(people["sam"].id),
            custodian_id=str(people["carl"].id),
            jurisdiction=jurisdiction,
        )
        control, _ = await uow.controls.declare(
            tenant_id=tenant_id, identity="notional", pql=pql, criticality=1
        )
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
        return str(control.id)


async def run(database: Database, tenant_id: str, *, violating: int) -> str:
    def execute(_query: str) -> list[dict[str, float]]:
        return [{"scanned_rows": 1000, "violating_rows": violating}]

    async with database.unit_of_work() as uow:
        report = await ControlRun(uow, tenant_id, execute=execute).execute_all()
    return report.run_id


async def run_and_alert(
    database: Database,
    tenant_id: str,
    registry: Registry[Notifier],
    *,
    violating: int,
    config: Configuration | None = None,
) -> Any:
    run_id = await run(database, tenant_id, violating=violating)
    return await alert_after_run(
        database, tenant_id, config or alerts_config(), run_id=run_id, registry=registry
    )


class TestTheLoop:
    async def test_one_alert_then_silence_then_a_resolution(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        await declare_estate(started_database, tenant_id)

        first = await run_and_alert(started_database, tenant_id, registry, violating=12)
        assert first.delivered == 1
        [opened] = Capture.sent
        assert opened.subject == "[Prama] opened: positions_eod (value)"
        # A value fault is the steward's, and reaches them by email address.
        assert opened.recipients == ("sam@example.com",)
        assert "12 violating row(s) of 1,000 scanned" in opened.body
        assert opened.alert["alert"]["dataset"] == "positions_eod"

        # The same failure again, within the quiet period: nothing.
        second = await run_and_alert(started_database, tenant_id, registry, violating=12)
        assert second.delivered == 0
        assert [d.change for d in second.dispatches] == [Change.UNCHANGED]
        assert len(Capture.sent) == 1

        # It passes: one resolution, to the same person.
        third = await run_and_alert(started_database, tenant_id, registry, violating=0)
        assert third.resolved == 1 and third.delivered == 1
        assert len(Capture.sent) == 2
        resolved = Capture.sent[1]
        assert resolved.subject.startswith("[Prama] resolved:")
        assert resolved.recipients == ("sam@example.com",)

        # And it is over: a pass after that sends nothing more.
        fourth = await run_and_alert(started_database, tenant_id, registry, violating=0)
        assert fourth.resolved == 0 and len(Capture.sent) == 2
        async with started_database.unit_of_work() as uow:
            assert await uow.alerts.open_alerts(tenant_id) == []

    async def test_off_by_default(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        await declare_estate(started_database, tenant_id)
        run_id = await run(started_database, tenant_id, violating=12)
        defaults = ConfigurationBuilder().with_defaults(DEFAULTS).build()
        assert await alert_after_run(started_database, tenant_id, defaults, run_id=run_id) is None
        assert Capture.sent == []

    async def test_nobody_declared_means_nobody_is_sent_anything(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id, identity="n", pql=CRITICAL, criticality=1
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="a")
        report = await run_and_alert(started_database, tenant_id, registry, violating=3)
        assert report.delivered == 0 and Capture.sent == []
        assert "nobody is recorded as steward" in report.dispatches[0].reason


class TestTheStateSurvives:
    async def test_a_new_router_built_from_the_database_does_not_repeat_it(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        await declare_estate(started_database, tenant_id)
        report = await run_and_alert(started_database, tenant_id, registry, violating=12)
        [dispatch] = report.dispatches
        alert = dispatch.alert
        contacts = {("positions_eod", Role.STEWARD): "sam@example.com"}

        async with started_database.unit_of_work() as uow:
            history = await uow.alerts.history(tenant_id)
        assert alert.fingerprint in history

        # As a restarted server, or a second one, would build it.
        rebuilt = Router(contacts, history=history)
        assert rebuilt.dispatch(alert).change is Change.UNCHANGED
        assert rebuilt.history == history

        # The counterfactual: a router that starts empty announces it again.
        assert Router(contacts).dispatch(alert).change is Change.OPENED

    async def test_without_saving_the_state_every_run_alerts_again(
        self,
        started_database: Database,
        tenant_id: str,
        registry: Registry[Notifier],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The counterfactual for the persistence: the state before this fix."""

        async def forget(*_args: Any) -> None:
            return None

        monkeypatch.setattr(AlertPipeline, "_save", forget)
        await declare_estate(started_database, tenant_id)
        await run_and_alert(started_database, tenant_id, registry, violating=12)
        await run_and_alert(started_database, tenant_id, registry, violating=12)
        assert len(Capture.sent) == 2


class TestFailure:
    async def test_a_notifier_failure_is_recorded_and_the_run_stands(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        await declare_estate(started_database, tenant_id)
        report = await run_and_alert(
            started_database, tenant_id, registry, violating=12, config=alerts_config("broken")
        )
        assert report.delivered == 0
        [error] = report.failures.values()
        assert "the relay is down" in error
        async with started_database.unit_of_work() as uow:
            [state] = await uow.alerts.open_alerts(tenant_id)
            assert "the relay is down" in state.last_error
            chain = await uow.evidence.chain(tenant_id)
        assert [r.verdict for r in chain] == ["fail"]

    async def test_an_unknown_channel_is_recorded_not_raised(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        await declare_estate(started_database, tenant_id)
        report = await run_and_alert(
            started_database, tenant_id, registry, violating=12, config=alerts_config("pager")
        )
        assert "pager" in next(iter(report.failures.values()))

    async def test_residency_withholds_the_alert_and_nothing_is_delivered(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        async with started_database.unit_of_work() as uow:
            tenant = await uow.tenants.get(tenant_id)
            tenant.residency = "EU"
        await declare_estate(started_database, tenant_id, jurisdiction="EU")
        report = await run_and_alert(
            started_database,
            tenant_id,
            registry,
            violating=12,
            config=alerts_config(channel_regions={"capture": "US"}),
        )
        assert Capture.sent == []
        assert "withheld on residency" in report.dispatches[0].reason


class TestTheDigest:
    async def test_a_minor_failure_waits_for_one_digest_a_day(
        self, started_database: Database, tenant_id: str, registry: Registry[Notifier]
    ) -> None:
        await declare_estate(started_database, tenant_id, MINOR)
        report = await run_and_alert(started_database, tenant_id, registry, violating=4)
        assert report.queued == 1 and Capture.sent == []
        config = alerts_config(digest_hour=9)

        before = FixedClock(datetime(2030, 3, 4, 8, 59, tzinfo=UTC))
        assert (
            await digest_if_due(
                started_database, tenant_id, config, registry=registry, clock=before
            )
            == 0
        )

        after = FixedClock(datetime(2030, 3, 4, 9, 30, tzinfo=UTC))
        assert (
            await digest_if_due(started_database, tenant_id, config, registry=registry, clock=after)
            == 1
        )
        [digest] = Capture.sent
        assert digest.subject == "[Prama] daily digest: 1 finding(s)"
        assert digest.recipients == ("sam@example.com",)
        assert "positions_eod" in digest.body

        # Once a day: a second minor finding the same day waits for tomorrow.
        await run_and_alert(started_database, tenant_id, registry, violating=4)
        later = FixedClock(datetime(2030, 3, 4, 17, 0, tzinfo=UTC))
        assert (
            await digest_if_due(started_database, tenant_id, config, registry=registry, clock=later)
            == 0
        )


class TestTheSchedulerDelivers:
    async def test_a_tick_on_a_failing_table_sends_the_alert(
        self,
        started_database: Database,
        tenant_id: str,
        registry: Registry[Notifier],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Through the real scheduler, on a real DuckDB table, with the
        process-wide registry the server uses."""
        import duckdb

        from prama.execute.scheduler import Scheduler

        source = tmp_path / "w.duckdb"
        connection = duckdb.connect(str(source))
        connection.execute("CREATE TABLE positions_eod (notional DOUBLE)")
        connection.execute("INSERT INTO positions_eod VALUES (1.0), (NULL)")
        connection.close()
        monkeypatch.setattr(notify, "_default", registry)
        await declare_estate(started_database, tenant_id)

        scheduler = Scheduler(
            started_database,
            [tenant_id],
            against=str(source),
            dialect="duckdb",
            config=alerts_config(),
        )
        tick = await scheduler.tick()
        assert tick.outcome == "ran", tick.detail
        assert tick.verdicts == {"fail": 1}
        [message] = Capture.sent
        assert message.subject == "[Prama] opened: positions_eod (value)"


def test_every_place_a_run_completes_alerts() -> None:
    """The completion points, pinned: a run path that stops alerting is a
    build failure, not a quiet regression."""
    src = REPO_ROOT / "src" / "prama"
    callers = sorted(
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "alert_after_run"
    )
    assert callers == [
        "api/routes/fleet.py",
        "api/routes/runs.py",
        "cli/control.py",
        "execute/scheduler.py",
    ]
