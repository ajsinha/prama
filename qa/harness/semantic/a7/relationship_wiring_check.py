"""Direct-execution verification: does confirming a relationship ever invoke
RelationshipGenerator, so that relationship-kind proposals reach the queue?
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.derive.relationships import RelationshipGenerator
from prama.semantic.relationships import MatchKey, RelationshipDeclaration, RelationshipKind, Tolerance
from prama.semantic.services import DatasetService, RelationshipService

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

CALLS = []
_original_generate = RelationshipGenerator.generate


def _tracking_generate(self, declaration):
    CALLS.append(declaration.kind.value)
    return _original_generate(self, declaration)


RelationshipGenerator.generate = _tracking_generate


def make_config(tmp_dir: Path):
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(tmp_dir / "prama-test.db")},
                    "schema_dir": str(REPO_ROOT / "schema"),
                    "verify_on_start": True,
                },
                "security": {
                    "session_secret": "test-only-not-a-secret",
                    "cookies_https_only": False,
                },
            },
            name="test",
        )
        .build()
    )


async def main():
    tmp_dir = Path(tempfile.mkdtemp())
    config = make_config(tmp_dir)
    database = Database.from_config(config)
    database.initialise(applied_by="qa")
    await database.start()
    try:
        async with database.unit_of_work() as uow:
            tenant = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
            await uow.flush()
            tenant_id = str(tenant.id)

        async with database.unit_of_work() as uow:
            ds = DatasetService(uow)
            sub, _ = await ds.declare(tenant_id=tenant_id, name="Sub-ledger")
            gl, _ = await ds.declare(tenant_id=tenant_id, name="General Ledger")
            sub_id, gl_id = str(sub.id), str(gl.id)

        async with database.unit_of_work() as uow:
            rel_service = RelationshipService(uow)
            entity, version = await rel_service.declare(
                tenant_id=tenant_id,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=sub_id,
                    to_dataset_id=gl_id,
                    match_keys=(MatchKey("account_code"),),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="EUR"),
                ),
                authored_by="architect",
                approved_by="reviewer",
            )
            relationship_id = str(entity.id)
            print(f"declared relationship {relationship_id}, status={version.status}")
            print(f"declaration.generates (static, from RelationshipKind) = {version.kind}")

        async with database.unit_of_work() as uow:
            events = await uow.audit.for_object(tenant_id, "relationship", relationship_id)
            print(f"audit event detail: {events[0].detail_json}")

        print(f"\nRelationshipGenerator.generate() call count after declare(): {len(CALLS)}")
        print(f"calls recorded: {CALLS}")

        # Also test the discover-then-confirm path, which is what a real
        # steward clicking 'confirm' on the estate map exercises.
        CALLS.clear()
        async with database.unit_of_work() as uow:
            rel_service = RelationshipService(uow)
            entity2, version2 = await rel_service.propose_discovered(
                tenant_id=tenant_id,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.MIRRORS,
                    from_dataset_id=sub_id,
                    to_dataset_id=gl_id,
                    match_keys=(MatchKey("account_code"),),
                    compare=("amount",),
                ),
                discovered_by="overlap_statistics",
                confidence=0.95,
                evidence={"key_overlap": 0.99},
            )
            rel2_id = str(entity2.id)

        async with database.unit_of_work() as uow:
            confirmed = await RelationshipService(uow).confirm(
                tenant_id=tenant_id, relationship_id=rel2_id, confirmed_by="steward"
            )
            print(f"\nconfirmed discovered MIRRORS relationship, status={confirmed.status}")

        print(f"RelationshipGenerator.generate() call count after propose_discovered()+confirm(): {len(CALLS)}")
        print(f"calls recorded: {CALLS}")

        # Check whether the uow exposes any DAO for proposals/queue at all.
        dao_names = [
            name for name in dir(uow.__class__)
            if isinstance(getattr(uow.__class__, name, None), property)
        ]
        print(f"\nUnitOfWork DAOs available: {sorted(dao_names)}")
        print(f"'proposals' DAO present: {'proposals' in dao_names}")
    finally:
        await database.stop()
        database.sync_engine().dispose()


asyncio.run(main())
