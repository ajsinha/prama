import asyncio
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db import Database
from prama.db.temporal import Provenance
from prama.semantic.services import DatasetService, EstateService, RelationshipService
from prama.semantic.services.graph import BindingService, ConceptService, ConnectionService, JourneyService
from prama.semantic.relationships import MatchKey, RelationshipDeclaration, RelationshipKind
from prama.semantic.values import Grain, Rhythm, Frequency

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")


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


RESULTS = {}


def record(case_id, outcome):
    RESULTS[case_id] = outcome
    print(f"--- {case_id}: {outcome}")


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
            tenant_b = uow.tenants.create(slug="beta-bank", display_name="Beta Bank")
            await uow.flush()
            tenant_b_id = str(tenant_b.id)

        # ================= SEM-151: every mutation writes an audit event =================
        try:
            audit_actions = []
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds_entity, ds_version = await svc.declare(
                    tenant_id=tenant_id, name="Audit Ds1", authored_by="alice"
                )
                ds_id = str(ds_entity.id)
                await svc.amend(
                    tenant_id=tenant_id, dataset_id=ds_id, reason="grain clarified", authored_by="alice",
                    purpose="clarify"
                )
                await svc.correct(
                    tenant_id=tenant_id, dataset_id=ds_id, reason="fixed typo", authored_by="alice",
                    description="fixed"
                )
                attr_entity, _ = await svc.declare_attribute(
                    tenant_id=tenant_id, dataset_id=ds_id, name="amount", authored_by="alice"
                )
                ds2_entity, _ = await svc.declare(tenant_id=tenant_id, name="Audit Ds2", authored_by="alice")
                ds2_id = str(ds2_entity.id)

                rel_svc = RelationshipService(uow)
                rel_entity, rel_version = await rel_svc.declare(
                    tenant_id=tenant_id,
                    declaration=RelationshipDeclaration(
                        kind=RelationshipKind.REFERENCES,
                        from_dataset_id=ds_id,
                        to_dataset_id=ds2_id,
                        match_keys=(MatchKey("k"),),
                    ),
                    authored_by="alice",
                )
                # a second relationship to confirm/reject cycle
                rel2_entity, rel2_version = await rel_svc.propose_discovered(
                    tenant_id=tenant_id,
                    declaration=RelationshipDeclaration(
                        kind=RelationshipKind.REFERENCES,
                        from_dataset_id=ds_id,
                        to_dataset_id=ds2_id,
                        match_keys=(MatchKey("k2"),),
                    ),
                    discovered_by="scanner",
                    confidence=0.5,
                    evidence={},
                )
                await rel_svc.confirm(tenant_id=tenant_id, relationship_id=str(rel2_entity.id), confirmed_by="bob")
                rel3_entity, _ = await rel_svc.propose_discovered(
                    tenant_id=tenant_id,
                    declaration=RelationshipDeclaration(
                        kind=RelationshipKind.REFERENCES,
                        from_dataset_id=ds_id,
                        to_dataset_id=ds2_id,
                        match_keys=(MatchKey("k3"),),
                    ),
                    discovered_by="scanner",
                    confidence=0.5,
                    evidence={},
                )
                await rel_svc.reject(
                    tenant_id=tenant_id, relationship_id=str(rel3_entity.id), rejected_by="bob", reason="wrong"
                )

                concept_svc = ConceptService(uow)
                concept_entity, _ = await concept_svc.declare_concept(
                    tenant_id=tenant_id, name="Exposure Concept", authored_by="alice"
                )
                prop_entity, _ = await concept_svc.declare_property(
                    tenant_id=tenant_id, concept_id=str(concept_entity.id), name="Notional",
                    authored_by="alice"
                )
                await concept_svc.map_attribute(
                    tenant_id=tenant_id, attribute_id=str(attr_entity.id), property_id=str(prop_entity.id),
                    mapped_by="alice"
                )

                journey_svc = JourneyService(uow)
                journey_entity, _ = await journey_svc.declare(
                    tenant_id=tenant_id, name="EOD Journey", authored_by="alice",
                    steps=[{"kind": "dataset", "dataset_id": ds_id}],
                )
                await journey_svc.set_steps(
                    tenant_id=tenant_id, journey_id=str(journey_entity.id), reason="add step",
                    authored_by="alice",
                    steps=[{"kind": "dataset", "dataset_id": ds_id}, {"kind": "dataset", "dataset_id": ds2_id}],
                )

                conn_svc = ConnectionService(uow)
                conn_entity, _ = await conn_svc.configure(
                    tenant_id=tenant_id, name="Main Conn", source_type="postgres", authored_by="alice"
                )

                bind_svc = BindingService(uow)
                bind_entity, _ = await bind_svc.bind_dataset(
                    tenant_id=tenant_id, dataset_id=ds_id, connection_id=str(conn_entity.id),
                    physical_ref={"table": "positions"}, authored_by="alice"
                )
                await bind_svc.record_drift(
                    tenant_id=tenant_id, binding_id=str(bind_entity.id), drift_state="retyped",
                    detail="new col"
                )

                checks = {
                    "dataset.declared": ("dataset", ds_id),
                    "dataset.amended": ("dataset", ds_id),
                    "dataset.corrected": ("dataset", ds_id),
                    "attribute.declared": ("attribute", str(attr_entity.id)),
                    "relationship.declared": ("relationship", str(rel_entity.id)),
                    "relationship.confirmed": ("relationship", str(rel2_entity.id)),
                    "relationship.rejected": ("relationship", str(rel3_entity.id)),
                    "concept.declared": ("concept", str(concept_entity.id)),
                    "concept_property.declared": ("concept_property", str(prop_entity.id)),
                    "attribute.mapped": ("attribute", str(attr_entity.id)),
                    "journey.declared": ("journey", str(journey_entity.id)),
                    "journey.steps_changed": ("journey", str(journey_entity.id)),
                    "connection.configured": ("connection", str(conn_entity.id)),
                    "dataset.bound": ("dataset", ds_id),
                    "binding.drifted": ("dataset", ds_id),
                }
                await uow.flush()
                found = {}
                for action, (kind, obj_id) in checks.items():
                    events = await uow.audit.for_object(tenant_id, kind, obj_id)
                    found[action] = [e.action for e in events]
                    has_action = action in found[action]
                    if not has_action:
                        # check full audit for the action to see if it was recorded but under different obj kind lookup
                        pass
                missing = [a for a in checks if a not in found[a]]
            record("SEM-151", f"actions checked={list(checks)}; missing audit rows for={missing}")
        except Exception as e:
            record("SEM-151", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ================= SEM-152: propose_discovered writes no audit =================
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                a, _ = await svc.declare(tenant_id=tenant_id, name="PD Ds A")
                b, _ = await svc.declare(tenant_id=tenant_id, name="PD Ds B")
                rel_svc = RelationshipService(uow)
                entity, version = await rel_svc.propose_discovered(
                    tenant_id=tenant_id,
                    declaration=RelationshipDeclaration(
                        kind=RelationshipKind.REFERENCES,
                        from_dataset_id=str(a.id), to_dataset_id=str(b.id),
                        match_keys=(MatchKey("k"),),
                    ),
                    discovered_by="scanner", confidence=0.9, evidence={"x": 1},
                )
                await uow.flush()
                events = await uow.audit.for_object(tenant_id, "relationship", str(entity.id))
            record("SEM-152", f"audit events for propose_discovered = {[e.action for e in events]} (count={len(events)})")
        except Exception as e:
            record("SEM-152", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ================= SEM-153: bind_attribute writes no audit =================
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="BA Dataset")
                attr, _ = await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="col1")
                conn_svc = ConnectionService(uow)
                conn, _ = await conn_svc.configure(tenant_id=tenant_id, name="BA Conn", source_type="postgres")
                bind_svc = BindingService(uow)
                bentity, bversion = await bind_svc.bind_attribute(
                    tenant_id=tenant_id, dataset_id=str(ds.id), attribute_id=str(attr.id),
                    connection_id=str(conn.id), physical_ref={"col": "c1"}, transform="upper(c1)"
                )
                await uow.flush()
                events = await uow.audit.for_object(tenant_id, "attribute", str(attr.id))
                events_binding_kind = await uow.audit.for_object(tenant_id, "binding", str(bentity.id))
            record("SEM-153", f"audit events for bind_attribute (obj_kind=attribute) = {[e.action for e in events]}; (obj_kind=binding) = {[e.action for e in events_binding_kind]}")
        except Exception as e:
            record("SEM-153", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ================= SEM-154: system action recorded as system =================
        try:
            async with database.unit_of_work() as uow:
                conn_svc = ConnectionService(uow)
                conn, _ = await conn_svc.configure(tenant_id=tenant_id, name="Health Conn", source_type="postgres")
                await conn_svc.record_health(tenant_id=tenant_id, connection_id=str(conn.id), state="healthy")
                await uow.flush()
                events_h = await uow.audit.for_object(tenant_id, "connection", str(conn.id))

                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="Drift Ds")
                bind_svc = BindingService(uow)
                bentity, _ = await bind_svc.bind_dataset(
                    tenant_id=tenant_id, dataset_id=str(ds.id), connection_id=str(conn.id),
                    physical_ref={"table": "t"}
                )
                await bind_svc.record_drift(tenant_id=tenant_id, binding_id=str(bentity.id), drift_state="missing")
                await uow.flush()
                events_d = await uow.audit.for_object(tenant_id, "dataset", str(ds.id))
            print("DEBUG events_h:", [(e.action, e.actor_kind, e.actor_id) for e in events_h])
            print("DEBUG events_d:", [(e.action, e.actor_kind, e.actor_id) for e in events_d])
            hc = [(e.action, e.actor_kind, e.actor_id) for e in events_h if e.action == "connection.health_recorded"]
            dc = [(e.action, e.actor_kind, e.actor_id) for e in events_d if e.action == "binding.drifted"]
            record("SEM-154", f"health_recorded events={hc}; drifted events={dc}")
        except Exception as e:
            record("SEM-154", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        print("=== DONE base.py section ===")
    finally:
        await database.stop()
        database.sync_engine().dispose()


asyncio.run(main())
