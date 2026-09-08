"""Repositories, the unit of work, and the database-backed lease provider.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prama.core.clock import ManualClock
from prama.core.errors import ConflictError, NotFoundError
from prama.db import Database


class TestUnitOfWork:
    async def test_commits_on_clean_exit(self, started_database: Database) -> None:
        async with started_database.unit_of_work() as uow:
            uow.tenants.create(slug="acme", display_name="Acme")
        async with started_database.unit_of_work() as uow:
            assert await uow.tenants.by_slug("acme") is not None

    async def test_rolls_back_on_exception(self, started_database: Database) -> None:
        with pytest.raises(RuntimeError):
            async with started_database.unit_of_work() as uow:
                uow.tenants.create(slug="ghost", display_name="Ghost")
                await uow.flush()
                raise RuntimeError("boom")
        async with started_database.unit_of_work() as uow:
            assert await uow.tenants.by_slug("ghost") is None

    async def test_a_unique_violation_becomes_a_conflict_error(
        self, started_database: Database
    ) -> None:
        async with started_database.unit_of_work() as uow:
            uow.tenants.create(slug="dup", display_name="One")
        with pytest.raises(ConflictError) as caught:
            async with started_database.unit_of_work() as uow:
                uow.tenants.create(slug="dup", display_name="Two")
        assert "unique" in caught.value.remedy.lower()

    async def test_repositories_are_cached_per_unit_of_work(
        self, started_database: Database
    ) -> None:
        async with started_database.unit_of_work() as uow:
            assert uow.tenants is uow.tenants


class TestTenancy:
    async def test_tenant_scoped_lookup_will_not_cross_tenants(
        self, started_database: Database
    ) -> None:
        async with started_database.unit_of_work() as uow:
            a = uow.tenants.create(slug="a", display_name="A")
            b = uow.tenants.create(slug="b", display_name="B")
            await uow.flush()
            principal = uow.principals.create(
                tenant_id=str(a.id), username="jsmith", display_name="J Smith"
            )
            await uow.flush()
            # The right tenant finds it; the wrong tenant does not, and cannot.
            assert await uow.principals.get_for_tenant(str(a.id), str(principal.id)) is not None
            assert await uow.principals.get_for_tenant(str(b.id), str(principal.id)) is None

    async def test_requiring_a_missing_entity_names_it(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError) as caught:
                await uow.principals.require_for_tenant(tenant_id, "01AAAAAAAAAAAAAAAAAAAAAAAA")
        assert "Principal" in caught.value.message

    async def test_counts_are_scoped(self, started_database: Database) -> None:
        async with started_database.unit_of_work() as uow:
            a = uow.tenants.create(slug="a", display_name="A")
            b = uow.tenants.create(slug="b", display_name="B")
            await uow.flush()
            for i in range(3):
                uow.principals.create(tenant_id=str(a.id), username=f"u{i}", display_name=f"U{i}")
            await uow.flush()
            assert await uow.principals.count_for_tenant(str(a.id)) == 3
            assert await uow.principals.count_for_tenant(str(b.id)) == 0


class TestRolesAndKeys:
    async def test_grant_is_idempotent_and_revocable(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            role = uow.roles.create(
                tenant_id=tenant_id, name="steward", permissions=["control:approve"]
            )
            principal = uow.principals.create(
                tenant_id=tenant_id, username="aroy", display_name="A Roy"
            )
            await uow.flush()
            await uow.roles.grant(str(principal.id), str(role.id))
            await uow.roles.grant(str(principal.id), str(role.id))  # again: no error
            await uow.flush()
            assert [r.name for r in await uow.principals.roles_of(str(principal.id))] == ["steward"]
            await uow.roles.revoke(str(principal.id), str(role.id))
            await uow.flush()
            assert await uow.principals.roles_of(str(principal.id)) == []

    async def test_permissions_round_trip_through_json_text(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            role = uow.roles.create(
                tenant_id=tenant_id,
                name="auditor",
                permissions=["evidence:read", "attestation:read"],
                builtin=True,
            )
            await uow.flush()
            role_id = str(role.id)
        async with started_database.unit_of_work() as uow:
            loaded = await uow.roles.require(role_id)
            assert loaded.permissions_json == ["evidence:read", "attestation:read"]
            assert loaded.is_builtin is True  # INTEGER 0/1 comes back as a bool

    async def test_api_key_stores_only_a_hash(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            principal = uow.principals.create(
                tenant_id=tenant_id, username="svc", display_name="Service", kind="service"
            )
            await uow.flush()
            key = uow.api_keys.create(
                tenant_id=tenant_id,
                principal_id=str(principal.id),
                name="ci",
                key_prefix="pk_live_abcd",
                key_hash="sha256:deadbeef",
                scopes=["control:read"],
                expires_at=datetime(2027, 1, 1, tzinfo=UTC),
            )
            await uow.flush()
            found = await uow.api_keys.by_prefix("pk_live_abcd")
            assert found is not None and found.key_hash == "sha256:deadbeef"
            assert not hasattr(key, "plaintext")


class TestAuditAndSettings:
    async def test_audit_is_append_only_and_queryable_by_object(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            for outcome in ("success", "denied"):
                uow.audit.record(
                    tenant_id=tenant_id,
                    action="control.approve",
                    object_kind="control",
                    object_id="ctl-1",
                    outcome=outcome,
                    detail={"severity": "critical"},
                )
        async with started_database.unit_of_work() as uow:
            events = await uow.audit.for_object(tenant_id, "control", "ctl-1")
            assert len(events) == 2
            assert events[0].detail_json["severity"] == "critical"
        # The repository deliberately exposes no way to change history.
        from prama.db.repositories import AuditRepository

        assert not hasattr(AuditRepository, "update")
        assert not hasattr(AuditRepository, "delete_for_object")

    async def test_timestamps_round_trip_as_aware_utc(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            uow.audit.record(tenant_id=tenant_id, action="x", object_kind="y")
        async with started_database.unit_of_work() as uow:
            event = (await uow.audit.recent(tenant_id))[0]
            assert event.occurred_at.tzinfo is not None
            assert event.occurred_at.utcoffset().total_seconds() == 0

    async def test_settings_upsert(self, started_database: Database, tenant_id: str) -> None:
        async with started_database.unit_of_work() as uow:
            await uow.settings.put(tenant_id, "alerting.digest", {"hour": 7})
            await uow.settings.put(tenant_id, "alerting.digest", {"hour": 9})
        async with started_database.unit_of_work() as uow:
            assert await uow.settings.get_value(tenant_id, "alerting.digest") == {"hour": 9}
            assert await uow.settings.get_value(tenant_id, "missing", default="d") == "d"


class TestDatabaseLeaseProvider:
    async def test_only_one_holder_wins_a_contested_resource(
        self, started_database: Database
    ) -> None:
        provider = started_database.lease_provider()
        first = await provider.acquire("scheduler.dispatch", "node-a", 30)
        second = await provider.acquire("scheduler.dispatch", "node-b", 30)
        assert first is not None
        assert second is None

    async def test_fencing_token_increases_across_handovers(
        self, started_database: Database
    ) -> None:
        provider = started_database.lease_provider()
        first = await provider.acquire("dispatch", "a", 30)
        assert first is not None
        await provider.release(first)
        second = await provider.acquire("dispatch", "b", 30)
        assert second is not None
        assert second.fencing_token > first.fencing_token

    async def test_an_expired_lease_can_be_taken_over(self, started_database: Database) -> None:
        clock = ManualClock()
        from prama.db.lease_provider import DatabaseLeaseProvider

        provider = DatabaseLeaseProvider(started_database._engines.async_engine(), clock=clock)
        assert await provider.acquire("dispatch", "a", 10) is not None
        assert await provider.acquire("dispatch", "b", 10) is None
        clock.advance(11)
        assert await provider.acquire("dispatch", "b", 10) is not None

    async def test_renewal_by_a_superseded_holder_is_rejected(
        self, started_database: Database
    ) -> None:
        provider = started_database.lease_provider()
        stale = await provider.acquire("dispatch", "a", 30)
        assert stale is not None
        await provider.release(stale)
        await provider.acquire("dispatch", "b", 30)
        # 'a' resumes after a stall and tries to renew a lease it no longer owns.
        assert await provider.renew(stale, 30) is None

    async def test_inspect_reports_the_current_holder(self, started_database: Database) -> None:
        provider = started_database.lease_provider()
        await provider.acquire("dispatch", "node-a", 30)
        current = await provider.inspect("dispatch")
        assert current is not None and current.holder == "node-a"
        assert await provider.inspect("nothing-held") is None
