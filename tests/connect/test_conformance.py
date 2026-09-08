"""The connector conformance suite.

Every connector passes this, or it is not supported. That is the whole meaning
of the word here: not "we wrote one", but "it behaves the way the contract says,
including when it fails".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from prama.connect import (
    Connector,
    ConnectorError,
    HealthState,
    ReadPolicy,
    SamplePlan,
    SamplingStrategy,
    UnauthorisedError,
)
from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry

ROWS = [
    (1, "GB0002634946", "GBP", 1000.50),
    (2, "US0378331005", "USD", 25000.00),
    (3, "DE0007164600", "EUR", 3300.75),
    (4, "GB0002634946", "GBP", 990.25),
    (5, None, "JPY", 120000.0),
]


@pytest.fixture
def registry() -> ConnectorRegistry:
    return register_builtin(ConnectorRegistry())


@pytest.fixture
def csv_root(tmp_path: Path) -> Path:
    root = tmp_path / "landing"
    root.mkdir()
    lines = ["position_id,isin,currency,notional"]
    lines += [f"{r[0]},{r[1] or ''},{r[2]},{r[3]}" for r in ROWS]
    (root / "positions_20260331.csv").write_text("\n".join(lines) + "\n")
    (root / "notes.md").write_text("not a data file\n")
    return root


@pytest.fixture
def sqlite_source(tmp_path: Path) -> Path:
    path = tmp_path / "extract.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE positions ("
        "position_id INTEGER NOT NULL, isin TEXT, currency TEXT NOT NULL, notional REAL)"
    )
    connection.executemany("INSERT INTO positions VALUES (?, ?, ?, ?)", ROWS)
    connection.execute("CREATE VIEW gbp_positions AS SELECT * FROM positions WHERE currency='GBP'")
    connection.commit()
    connection.close()
    return path


async def _make(registry: ConnectorRegistry, key: str, config: dict[str, Any], **kw: Any):
    return registry.create(key, config, **kw)


#: Every connector, and how this suite gets hold of a readable one.
#:
#: ``None`` means the connector needs a live service — a database, a bucket —
#: and is exercised by its own integration tests instead. It still has to
#: appear here: the point of the table is that a connector cannot be added
#: without somebody deciding how it will be proved, and
#: ``test_every_registered_connector_is_accounted_for`` fails the build if one
#: is.
COVERAGE: dict[str, str | None] = {
    "filesystem": "csv_root",
    "sqlite": "sqlite_source",
    # tests/connect/sql/test_postgres_live.py — needs PRAMA_TEST_POSTGRES_DSN
    "postgresql": None,
    # tests/connect/objectstore/ — needs PRAMA_TEST_S3_ENDPOINT
    "objectstore": None,
}

LOCAL = [key for key, fixture in COVERAGE.items() if fixture is not None]


@pytest.fixture(params=LOCAL)
async def connector(
    request: pytest.FixtureRequest,
    registry: ConnectorRegistry,
    csv_root: Path,
    sqlite_source: Path,
) -> AsyncIterator[tuple[Connector, tuple[str, ...]]]:
    """Each locally runnable connector, plus the path of an object it reads."""
    if request.param == "filesystem":
        connector = await _make(registry, "filesystem", {"root_path": str(csv_root)})
        path = ("positions_20260331.csv",)
    else:
        connector = await _make(registry, "sqlite", {"database_path": str(sqlite_source)})
        path = ("positions",)
    async with connector:
        yield connector, path


class TestCoverage:
    def test_every_registered_connector_is_accounted_for(self, registry: ConnectorRegistry) -> None:
        """A connector cannot ship without somebody deciding how it is proved.

        Connector breadth is a treadmill, and the way a treadmill goes wrong is
        quietly: a source is added, it works on the author's machine, and
        nothing ever checks it again. This test is the thing that notices.
        """
        missing = sorted(set(registry.keys()) - set(COVERAGE))
        assert not missing, (
            f"connector(s) {missing} are registered but not in COVERAGE. Add them to "
            f"this suite, or record the integration test that proves them."
        )

    def test_every_connector_declares_what_it_can_push_down(
        self, registry: ConnectorRegistry
    ) -> None:
        # The capability matrix is the published contract. A connector that
        # declares nothing would have every control fall back to local
        # evaluation, silently and expensively.
        for key in registry:
            assert registry.capabilities(key).to_capabilities(), key

    def test_every_connector_states_the_credential_field_it_fills(
        self, registry: ConnectorRegistry
    ) -> None:
        for key in registry:
            assert registry.get(key).credential_field


class TestContract:
    """Behaviour every connector must exhibit."""

    async def test_health_reports_a_usable_source(self, connector) -> None:
        subject, _ = connector
        report = await subject.health()
        assert report.state is HealthState.HEALTHY
        assert report.is_usable
        assert report.detail  # in business language, never a stack trace

    async def test_discovery_finds_the_object_and_ranks_it(self, connector) -> None:
        subject, path = connector
        found = await subject.discover()
        assert path in [o.path for o in found]
        # Ranked for a person: largest first, never alphabetical.
        sizes = [(o.estimated_bytes or o.estimated_rows or 0) for o in found]
        assert sizes == sorted(sizes, reverse=True)

    async def test_describe_returns_the_columns(self, connector) -> None:
        subject, path = connector
        schema = await subject.describe(path)
        assert set(schema.column_names) == {"position_id", "isin", "currency", "notional"}
        assert schema.column("isin") is not None
        assert schema.estimated_rows == len(ROWS)

    async def test_snapshot_is_exact_and_stable(self, connector) -> None:
        subject, path = connector
        first = await subject.snapshot(path)
        second = await subject.snapshot(path)
        assert first.exact is True
        # Same unchanged data, same identifier: that is what makes replay work.
        assert first.identifier == second.identifier
        assert first.to_dict()["exact"] is True

    async def test_read_returns_every_row_as_arrow(self, connector) -> None:
        subject, path = connector
        rows = 0
        async for batch in subject.read(path):
            rows += batch.num_rows
            assert set(batch.schema.names) >= {"position_id", "currency"}
        assert rows == len(ROWS)

    async def test_a_head_sample_is_bounded_and_marked_unrepresentative(self, connector) -> None:
        subject, path = connector
        plan = SamplePlan(strategy=SamplingStrategy.HEAD, rows=2)
        rows = 0
        async for batch in subject.read(path, plan=plan):
            rows += batch.num_rows
        assert rows <= 2
        # A rate measured here says nothing about the whole, and the type says so.
        assert plan.strategy.is_representative is False

    async def test_a_missing_object_names_itself_with_a_remedy(self, connector) -> None:
        subject, _ = connector
        with pytest.raises(ConnectorError) as caught:
            await subject.describe(("no_such_object",))
        assert caught.value.remedy
        assert "no_such_object" in str(caught.value)

    async def test_capabilities_are_declared_not_probed(self, connector) -> None:
        subject, _ = connector
        capabilities = subject.pushdown_capabilities()
        assert capabilities  # each built-in claims something
        assert subject.supports("pushdown.sql")

    async def test_the_read_policy_is_enforced(
        self, registry: ConnectorRegistry, csv_root: Path, sqlite_source: Path
    ) -> None:
        # A path outside the policy is refused, and the refusal says how to fix it.
        policy = ReadPolicy(allowed_paths=("nothing_matches",))
        subject = registry.create("sqlite", {"database_path": str(sqlite_source)}, policy=policy)
        async with subject:
            assert await subject.discover() == []
            with pytest.raises(UnauthorisedError) as caught:
                await subject.describe(("positions",))
        assert "allowed paths" in caught.value.remedy


class TestHealthDiagnosis:
    """The distinction that decides what a user does next."""

    async def test_a_missing_source_is_unreachable_not_unauthorised(
        self, registry: ConnectorRegistry, tmp_path: Path
    ) -> None:
        subject = registry.create("sqlite", {"database_path": str(tmp_path / "absent.db")})
        async with subject:
            report = await subject.health()
        assert report.state is HealthState.UNREACHABLE
        assert report.needs_access_request is False  # a path problem, not an access one

    async def test_a_directory_that_is_a_file_is_diagnosed_precisely(
        self, registry: ConnectorRegistry, tmp_path: Path
    ) -> None:
        file = tmp_path / "notadir.csv"
        file.write_text("a,b\n1,2\n")
        subject = registry.create("filesystem", {"root_path": str(file)})
        async with subject:
            report = await subject.health()
        assert report.state is HealthState.UNREACHABLE
        assert "folder above it" in report.detail


class TestFilesystemSpecifics:
    async def test_non_data_files_are_ignored(
        self, registry: ConnectorRegistry, csv_root: Path
    ) -> None:
        subject = registry.create("filesystem", {"root_path": str(csv_root)})
        async with subject:
            found = await subject.discover()
        assert [o.leaf for o in found] == ["positions_20260331.csv"]

    async def test_an_unsupported_extension_is_refused_with_the_list(
        self, registry: ConnectorRegistry, tmp_path: Path
    ) -> None:
        (tmp_path / "data.xyz").write_text("x")
        subject = registry.create("filesystem", {"root_path": str(tmp_path), "file_pattern": "*"})
        async with subject:
            with pytest.raises(ConnectorError) as caught:
                await subject.describe(("data.xyz",))
        assert ".csv" in caught.value.remedy

    async def test_a_seeded_fractional_sample_is_reproducible(
        self, registry: ConnectorRegistry, csv_root: Path
    ) -> None:
        subject = registry.create("filesystem", {"root_path": str(csv_root)})
        plan = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.6, seed=42)
        async with subject:
            first = [b.num_rows async for b in subject.read(("positions_20260331.csv",), plan=plan)]
            second = [
                b.num_rows async for b in subject.read(("positions_20260331.csv",), plan=plan)
            ]
        # Reproducibility is what lets a sampled verdict carry an honest confidence.
        assert first == second


class TestSqliteSpecifics:
    async def test_views_are_discovered_when_asked_for(
        self, registry: ConnectorRegistry, sqlite_source: Path
    ) -> None:
        subject = registry.create("sqlite", {"database_path": str(sqlite_source)})
        async with subject:
            kinds = {o.leaf: o.kind for o in await subject.discover()}
        assert kinds["gbp_positions"] == "view"

    async def test_views_can_be_excluded(
        self, registry: ConnectorRegistry, sqlite_source: Path
    ) -> None:
        subject = registry.create(
            "sqlite", {"database_path": str(sqlite_source), "include_views": False}
        )
        async with subject:
            assert "gbp_positions" not in [o.leaf for o in await subject.discover()]

    async def test_the_source_is_opened_read_only(
        self, registry: ConnectorRegistry, sqlite_source: Path
    ) -> None:
        # Pointing Prama at a production extract must not be able to alter it,
        # and the guarantee comes from the driver rather than our discipline.
        subject = registry.create("sqlite", {"database_path": str(sqlite_source)})
        async with subject:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                subject._connect().execute("DELETE FROM positions")

    async def test_nullability_is_reported(
        self, registry: ConnectorRegistry, sqlite_source: Path
    ) -> None:
        subject = registry.create("sqlite", {"database_path": str(sqlite_source)})
        async with subject:
            schema = await subject.describe(("positions",))
        assert schema.column("position_id").nullable is False
        assert schema.column("isin").nullable is True

    async def test_sqlite_does_not_claim_regex_it_does_not_have(
        self, registry: ConnectorRegistry
    ) -> None:
        # Claiming it would produce a control that compiles and then fails at
        # the source — the exact outcome the capability matrix prevents.
        assert registry.capabilities("sqlite").regex_flavour == "none"
        assert "pushdown.regex" not in registry.capabilities("sqlite").describe()
