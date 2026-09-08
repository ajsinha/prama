"""The bridge from a declared connection to a live connector.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from prama.connect import SamplingStrategy, UnauthorisedError
from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry
from prama.core.errors import NotFoundError, ValidationError
from prama.db import Database
from prama.secrets import MemorySecretProvider, SecretResolutionError, SecretResolver
from prama.semantic.services import (
    ConnectionService,
    ConnectivityService,
    DatasetService,
    read_policy_from,
)


@pytest.fixture
def registry() -> ConnectorRegistry:
    return register_builtin(ConnectorRegistry())


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "trades.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE trades (trade_id INTEGER NOT NULL, ccy TEXT NOT NULL, notional REAL)"
    )
    connection.executemany(
        "INSERT INTO trades VALUES (?,?,?)",
        [(i, ["GBP", "USD"][i % 2], i * 10.0) for i in range(1, 1001)],
    )
    connection.commit()
    connection.close()
    return path


async def _connection(uow, tenant_id: str, source: Path, **config):
    entity, _ = await ConnectionService(uow).configure(
        tenant_id=tenant_id,
        name="Trade extract",
        source_type="sqlite",
        config={"database_path": str(source), **config},
        authored_by="alice",
    )
    return str(entity.id)


class TestReadPolicy:
    def test_the_declaration_becomes_the_enforced_policy(self) -> None:
        policy = read_policy_from(
            {
                "allowed_paths": ["risk.*"],
                "max_bytes_scanned": 1_000_000,
                "permitted_hours": [2, 3, 4],
                "default_sampling": "systematic",
                "load_ceiling": 0.02,
            }
        )
        assert policy.permits_path(("risk", "positions"))
        assert not policy.permits_path(("finance", "gl"))
        assert policy.permits_now(3) and not policy.permits_now(11)
        assert policy.default_sampling is SamplingStrategy.SYSTEMATIC
        assert policy.load_ceiling == 0.02

    def test_an_empty_declaration_permits_everything_within_the_source(self) -> None:
        # A connection with no stated restriction is unrestricted, which is
        # honest; pretending otherwise would make the policy meaningless.
        policy = read_policy_from({})
        assert policy.permits_path(("anything",))
        assert policy.permits_now(4)


class TestConnectivity:
    async def test_test_reports_health_and_records_it(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            result = await ConnectivityService(uow, registry=registry).test(connection_id)
            assert result["state"] == "healthy"
            assert result["usable"] is True
            assert result["needs_access_request"] is False
            # And the outcome is recorded against the declaration.
            stored = await uow.connections.current(connection_id)
            assert stored.health_state == "healthy"
            assert stored.is_usable

    async def test_an_unreachable_source_is_not_an_access_problem(
        self, started_database: Database, tenant_id: str, tmp_path: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, tmp_path / "absent.db")
            result = await ConnectivityService(uow, registry=registry).test(connection_id)
        assert result["state"] == "unreachable"
        # The distinction that decides what the reader does next.
        assert result["needs_access_request"] is False

    async def test_discovery_ranks_and_limits(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            found = await ConnectivityService(uow, registry=registry).discover(connection_id)
        assert [o.qualified_name for o in found] == ["trades"]

    async def test_profiling_chooses_a_plan_and_records_it(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            run = await ConnectivityService(uow, registry=registry).profile(
                connection_id, ("trades",)
            )
        # A thousand rows is under the full-scan ceiling, so it reads everything
        # and may state an exact rate.
        assert run.profile.rows == 1000
        assert run.profile.provenance.is_complete
        assert "trade_id" in run.profile.key_candidates

    async def test_an_unattended_sweep_profiles_the_whole_source(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        # The Wave 3 gate: point Prama at a source and come back to an
        # inventory, with nobody having declared anything.
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            runs = await ConnectivityService(uow, registry=registry).profile_source(connection_id)
        assert [r.profile.qualified_name for r in runs] == ["trades"]
        assert runs[0].profile.rows == 1000

    async def test_the_read_policy_reaches_the_live_connector(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, _ = await ConnectionService(uow).configure(
                tenant_id=tenant_id,
                name="Restricted extract",
                source_type="sqlite",
                config={"database_path": str(source)},
                read_policy={"allowed_paths": ["nothing_matches"]},
            )
            service = ConnectivityService(uow, registry=registry)
            assert await service.discover(str(entity.id)) == []
            with pytest.raises(UnauthorisedError):
                await service.profile(str(entity.id), ("trades",))

    async def test_a_missing_connection_names_itself(
        self, started_database: Database, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError):
                await ConnectivityService(uow, registry=registry).test("01AAAAAAAAAAAAAAAAAAAAAAAA")

    async def test_an_uninstalled_source_type_lists_what_is_available(
        self, started_database: Database, tenant_id: str, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, _ = await ConnectionService(uow).configure(
                tenant_id=tenant_id, name="Teradata", source_type="teradata"
            )
            with pytest.raises(ValidationError) as caught:
                await ConnectivityService(uow, registry=registry).test(str(entity.id))
        assert "sqlite" in caught.value.remedy


class TestBindingSuggestions:
    async def test_an_unbound_dataset_is_matched_to_an_object_by_name(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            await DatasetService(uow).declare(tenant_id=tenant_id, name="Trades")
            suggestions = await ConnectivityService(uow, registry=registry).suggest_bindings(
                tenant_id, connection_id
            )
        assert len(suggestions) == 1
        assert suggestions[0]["path"] == ["trades"]
        # The evidence is shown, so a steward can check it in a second rather
        # than having to trust it.
        assert suggestions[0]["evidence"]["method"] == "name_similarity"
        assert suggestions[0]["confidence"] == 1.0

    async def test_an_unrelated_name_is_not_suggested(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            await DatasetService(uow).declare(
                tenant_id=tenant_id, name="Counterparty Reference Data"
            )
            suggestions = await ConnectivityService(uow, registry=registry).suggest_bindings(
                tenant_id, connection_id
            )
        assert suggestions == []

    async def test_nothing_is_suggested_when_everything_is_bound(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            suggestions = await ConnectivityService(uow, registry=registry).suggest_bindings(
                tenant_id, connection_id
            )
        assert suggestions == []


class TestCredentialResolution:
    """A connection stores a reference; the credential arrives at the last moment."""

    async def test_the_stored_declaration_never_holds_the_credential(
        self, started_database: Database, tenant_id: str, source: Path
    ) -> None:
        # The property the whole design rests on: this record can be exported to
        # Git, diffed in a pull request and shown in the UI.
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            declared = await uow.connections.current(connection_id)
            assert declared is not None
            assert "password" not in json.dumps(declared.config_json or {})

    async def test_a_referenced_secret_reaches_the_connector(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        resolver = SecretResolver([MemorySecretProvider({"pg": "from-the-vault"})])
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            declared = await uow.connections.current(connection_id)
            assert declared is not None
            declared.credential_ref = "memory://pg"
            connector = await ConnectivityService(
                uow, registry=registry, secrets=resolver
            ).connector_for(connection_id)
            assert connector.config["password"] == "from-the-vault"

    async def test_where_the_credential_lands_is_the_connectors_decision(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        # Not the reference's. A fragment already means "which field of the JSON
        # document at this location", so routing by fragment would leave
        # memory://creds#password ambiguous between the two meanings.
        registry.get("sqlite").credential_field = "busy_timeout_seconds"
        try:
            resolver = SecretResolver([MemorySecretProvider({"creds": '{"password": "9"}'})])
            async with started_database.unit_of_work() as uow:
                connection_id = await _connection(uow, tenant_id, source)
                declared = await uow.connections.current(connection_id)
                assert declared is not None
                declared.credential_ref = "memory://creds#password"
                connector = await ConnectivityService(
                    uow, registry=registry, secrets=resolver
                ).connector_for(connection_id)
                # The fragment chose the field *inside the document*; the
                # connector chose where it went.
                assert connector.config["busy_timeout_seconds"] == "9"
        finally:
            registry.get("sqlite").credential_field = "password"

    async def test_a_connection_with_no_credential_still_works(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        # A file on a mounted share; a database using OS authentication.
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            result = await ConnectivityService(uow, registry=registry).test(connection_id)
            assert result["state"] == "healthy"

    async def test_an_unresolvable_reference_fails_before_the_source_is_touched(
        self, started_database: Database, tenant_id: str, source: Path, registry
    ) -> None:
        # Rather than sending an empty password to the source and getting back
        # "authentication failed", which sends someone to check a credential
        # that was never read.
        resolver = SecretResolver([MemorySecretProvider({})])
        async with started_database.unit_of_work() as uow:
            connection_id = await _connection(uow, tenant_id, source)
            declared = await uow.connections.current(connection_id)
            assert declared is not None
            declared.credential_ref = "memory://absent"
            with pytest.raises(SecretResolutionError):
                await ConnectivityService(uow, registry=registry, secrets=resolver).connector_for(
                    connection_id
                )
