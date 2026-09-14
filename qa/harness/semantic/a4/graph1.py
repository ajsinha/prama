import asyncio
import tempfile
import traceback
from pathlib import Path

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db import Database
from prama.semantic.services import DatasetService
from prama.semantic.services.graph import (
    BindingService,
    ConceptService,
    ConnectionService,
    JourneyService,
)
from prama.semantic.services.connectivity import ConnectivityService
from prama.connect.builtin import register_builtin
from prama.connect.registry import ConnectorRegistry

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

results = {}


def record(case_id, ok, observed):
    results[case_id] = (("PASS" if ok else "FAIL"), observed)
    print(f"{case_id}: {'PASS' if ok else 'FAIL'} :: {observed}")


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


async def new_db():
    tmp_dir = Path(tempfile.mkdtemp())
    config = make_config(tmp_dir)
    database = Database.from_config(config)
    database.initialise(applied_by="qa")
    await database.start()
    return database


async def make_tenant(database, slug="acme"):
    async with database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug=slug, display_name=slug)
        await uow.flush()
        return str(tenant.id)


async def main():
    # ---------- SEM-196 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            svc = ConceptService(uow)
            await svc.declare_concept(tenant_id=tenant, name="Party")
        try:
            async with database.unit_of_work() as uow:
                svc = ConceptService(uow)
                await svc.declare_concept(tenant_id=tenant, name="Party")
            sem196_first = "no exception (FAIL - expected ConflictError)"
        except ConflictError as e:
            sem196_first = f"ConflictError: {e.message}"
        try:
            async with database.unit_of_work() as uow:
                svc = ConceptService(uow)
                entity, version = await svc.declare_concept(tenant_id=tenant, name="party")
            sem196_second = f"accepted, name={version.name!r}"
            second_ok = True
        except Exception as e:
            sem196_second = f"{type(e).__name__}: {e}"
            second_ok = False
        ok = sem196_first.startswith("ConflictError") and second_ok
        record("SEM-196", ok, f"first={sem196_first}; second={sem196_second}")
    except Exception:
        record("SEM-196", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-197 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            svc = ConceptService(uow)
            try:
                await svc.declare_property(
                    tenant_id=tenant, concept_id="01INVENTEDCONCEPTID0000000", name="ISIN"
                )
                record("SEM-197", False, "no exception raised")
            except NotFoundError as e:
                record("SEM-197", bool(e.remedy), f"NotFoundError remedy={e.remedy!r}")
    except Exception:
        record("SEM-197", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-198 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            csvc = ConceptService(uow)
            concept, _ = await csvc.declare_concept(tenant_id=tenant, name="Instrument")
            concept_id = str(concept.id)
            await csvc.declare_property(tenant_id=tenant, concept_id=concept_id, name="ISIN")
        try:
            async with database.unit_of_work() as uow:
                csvc = ConceptService(uow)
                await csvc.declare_property(tenant_id=tenant, concept_id=concept_id, name="ISIN")
            record("SEM-198", False, "no exception raised")
        except ConflictError as e:
            record("SEM-198", True, f"ConflictError: {e.message}")
    except Exception:
        record("SEM-198", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-199, SEM-200 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, _ = await dsvc.declare(tenant_id=tenant, name="Trades")
            entity, _ = await dsvc.declare_attribute(
                tenant_id=tenant, dataset_id=str(dataset.id), name="isin"
            )
            attribute_id = str(entity.id)
            csvc = ConceptService(uow)
            concept, _ = await csvc.declare_concept(tenant_id=tenant, name="Instrument")
            prop, _ = await csvc.declare_property(
                tenant_id=tenant, concept_id=str(concept.id), name="ISIN"
            )
            property_id = str(prop.id)
        async with database.unit_of_work() as uow:
            csvc = ConceptService(uow)
            version = await csvc.map_attribute(
                tenant_id=tenant,
                attribute_id=attribute_id,
                property_id=property_id,
                mapped_by="alice",
            )
        mapped_id = getattr(version, "concept_property_id", None)
        ok = mapped_id == property_id
        record(
            "SEM-199",
            ok,
            f"amendment.concept_property_id={mapped_id!r} (expected {property_id!r})",
        )

        try:
            async with database.unit_of_work() as uow:
                csvc = ConceptService(uow)
                await csvc.map_attribute(
                    tenant_id=tenant,
                    attribute_id=attribute_id,
                    property_id="01INVENTEDPROPERTYID00000",
                    mapped_by="alice",
                )
            record("SEM-200", False, "no exception raised")
        except NotFoundError as e:
            record("SEM-200", True, f"NotFoundError: {e.message}")
    except Exception:
        record("SEM-199", False, "EXC:" + traceback.format_exc())
        record("SEM-200", False, "blocked by SEM-199 failure")
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-201 ----------
    database = await new_db()
    try:
        tenant_a = await make_tenant(database, "tenant-a")
        tenant_b = await make_tenant(database, "tenant-b")
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            csvc = ConceptService(uow)
            dataset_a, _ = await dsvc.declare(tenant_id=tenant_a, name="Trades A")
            attr_a, _ = await dsvc.declare_attribute(
                tenant_id=tenant_a, dataset_id=str(dataset_a.id), name="isin"
            )
            dataset_b, _ = await dsvc.declare(tenant_id=tenant_b, name="Trades B")
            attr_b, _ = await dsvc.declare_attribute(
                tenant_id=tenant_b, dataset_id=str(dataset_b.id), name="isin"
            )
            concept_a, _ = await csvc.declare_concept(tenant_id=tenant_a, name="Instrument")
            prop_a, _ = await csvc.declare_property(
                tenant_id=tenant_a, concept_id=str(concept_a.id), name="ISIN"
            )
        try:
            async with database.unit_of_work() as uow:
                csvc = ConceptService(uow)
                await csvc.map_attribute(
                    tenant_id=tenant_a,
                    attribute_id=str(attr_b.id),  # tenant B's attribute
                    property_id=str(prop_a.id),  # tenant A's property
                    mapped_by="alice",
                )
            record("SEM-201", False, "no exception raised - cross tenant map succeeded!")
        except NotFoundError as e:
            record("SEM-201", True, f"NotFoundError: {e.message}")
        except Exception as e:
            record("SEM-201", False, f"{type(e).__name__}: {e}")
    except Exception:
        record("SEM-201", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-202 ----------
    database = await new_db()
    try:
        tenant_a = await make_tenant(database, "tenant-a")
        tenant_b = await make_tenant(database, "tenant-b")
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            csvc = ConceptService(uow)

            dataset_a, _ = await dsvc.declare(tenant_id=tenant_a, name="Trades A")
            attr_a, _ = await dsvc.declare_attribute(
                tenant_id=tenant_a, dataset_id=str(dataset_a.id), name="isin"
            )
            concept_a, _ = await csvc.declare_concept(tenant_id=tenant_a, name="Instrument")
            prop_a, _ = await csvc.declare_property(
                tenant_id=tenant_a, concept_id=str(concept_a.id), name="ISIN"
            )

            dataset_b, _ = await dsvc.declare(tenant_id=tenant_b, name="Trades B")
            attr_b, _ = await dsvc.declare_attribute(
                tenant_id=tenant_b, dataset_id=str(dataset_b.id), name="isin"
            )
            concept_b, _ = await csvc.declare_concept(tenant_id=tenant_b, name="Instrument")
            prop_b, _ = await csvc.declare_property(
                tenant_id=tenant_b, concept_id=str(concept_b.id), name="ISIN"
            )

            await csvc.map_attribute(
                tenant_id=tenant_a,
                attribute_id=str(attr_a.id),
                property_id=str(prop_a.id),
                mapped_by="alice",
            )
            await csvc.map_attribute(
                tenant_id=tenant_b,
                attribute_id=str(attr_b.id),
                property_id=str(prop_b.id),
                mapped_by="bob",
            )
        async with database.unit_of_work() as uow:
            # round 4: AttributeDao.mapped_to_property() has a required
            # tenant_id= keyword-only argument (round 3's finding, confirmed
            # unchanged in this tree -- see src/prama/db/dao/semantic.py).
            rows_for_a = await uow.attributes.mapped_to_property(
                str(prop_a.id), tenant_id=tenant_a
            )
            rows_for_b = await uow.attributes.mapped_to_property(
                str(prop_b.id), tenant_id=tenant_b
            )
            # explicit cross-tenant probe: tenant_b asking for tenant_a's
            # property_id must not see tenant_a's attribute. Not "the call
            # didn't raise" -- an actual attempted read across the boundary.
            rows_cross = await uow.attributes.mapped_to_property(
                str(prop_a.id), tenant_id=tenant_b
            )
        ids_a = {str(r.attribute_id) for r in rows_for_a}
        ids_b = {str(r.attribute_id) for r in rows_for_b}
        ids_cross = {str(r.attribute_id) for r in rows_cross}
        # also confirm the call is refused outright when tenant_id is omitted
        no_tenant_typeerror = None
        try:
            await uow.attributes.mapped_to_property(str(prop_a.id))  # type: ignore[call-arg]
        except TypeError as e:
            no_tenant_typeerror = str(e)
        ok = (
            ids_a == {str(attr_a.id)}
            and ids_b == {str(attr_b.id)}
            and ids_cross == set()
            and no_tenant_typeerror is not None
        )
        record(
            "SEM-202",
            ok,
            f"same-tenant reads isolated (ids_a={ids_a}, ids_b={ids_b}); "
            f"cross-tenant read (tenant_b requesting tenant_a's property_id)={ids_cross!r}; "
            f"omitting tenant_id raises TypeError={no_tenant_typeerror!r}",
        )
    except Exception:
        record("SEM-202", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-203 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            d1, _ = await dsvc.declare(tenant_id=tenant, name="Trades")
            d2, _ = await dsvc.declare(tenant_id=tenant, name="Positions")
            d3, _ = await dsvc.declare(tenant_id=tenant, name="Ledger")
            jsvc = JourneyService(uow)
            steps = [
                {"kind": "dataset", "dataset_id": str(d1.id), "ordinal": 99},
                {"kind": "dataset", "dataset_id": str(d2.id), "ordinal": 5},
                {"kind": "dataset", "dataset_id": str(d3.id), "ordinal": 1},
            ]
            entity, version = await jsvc.declare(
                tenant_id=tenant, name="Trade Lifecycle", steps=steps
            )
        ordinals = [s["ordinal"] for s in version.steps_json]
        ok = ordinals == [0, 1, 2] and version.slug == "trade_lifecycle"
        record(
            "SEM-203",
            ok,
            f"slug={version.slug!r}, ordinals={ordinals}, steps count={len(version.steps_json)}",
        )
    except Exception:
        record("SEM-203", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-204 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant,
                    name="Bad Journey",
                    steps=[{"kind": "spreadsheet"}],
                )
                record("SEM-204", False, "no exception raised")
            except ValidationError as e:
                names_present = all(k in e.remedy for k in ("dataset", "black_box", "manual"))
                position_named = "0" in e.message
                record(
                    "SEM-204",
                    names_present and position_named,
                    f"ValidationError message={e.message!r} remedy={e.remedy!r}",
                )
    except Exception:
        record("SEM-204", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-205 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant, name="Bad Journey 2", steps=[{"kind": "dataset"}]
                )
                record("SEM-205", False, "no exception raised")
            except ValidationError as e:
                ok = "black_box" in e.remedy
                record("SEM-205", ok, f"ValidationError message={e.message!r} remedy={e.remedy!r}")
    except Exception:
        record("SEM-205", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-206 ----------
    database = await new_db()
    try:
        tenant_a = await make_tenant(database, "tenant-a")
        tenant_b = await make_tenant(database, "tenant-b")
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            other_dataset, _ = await dsvc.declare(tenant_id=tenant_b, name="Other Tenant DS")
        observed = []
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant_a,
                    name="Invented Ref Journey",
                    steps=[{"kind": "dataset", "dataset_id": "01INVENTEDDATASETID000000"}],
                )
                observed.append("invented id: no exception (FAIL)")
            except NotFoundError as e:
                observed.append(f"invented id: NotFoundError position-named={'0' in e.message}")
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant_a,
                    name="Cross Tenant Ref Journey",
                    steps=[{"kind": "dataset", "dataset_id": str(other_dataset.id)}],
                )
                observed.append("cross-tenant id: no exception (FAIL)")
            except NotFoundError as e:
                observed.append(f"cross-tenant id: NotFoundError position-named={'0' in e.message}")
        ok = all("NotFoundError" in o for o in observed)
        record("SEM-206", ok, "; ".join(observed))
    except Exception:
        record("SEM-206", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-207 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        observed = []
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant, name="No Desc BB", steps=[{"kind": "black_box"}]
                )
                observed.append("black_box no desc: no exception (FAIL)")
            except ValidationError as e:
                observed.append("black_box no desc: ValidationError OK")
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant,
                    name="Blank Desc Manual",
                    steps=[{"kind": "manual", "description": "  "}],
                )
                observed.append("manual blank desc: no exception (FAIL)")
            except ValidationError as e:
                observed.append("manual blank desc: ValidationError OK")
        ok = all("OK" in o for o in observed)
        record("SEM-207", ok, "; ".join(observed))
    except Exception:
        record("SEM-207", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-208 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            entity, version = await jsvc.declare(
                tenant_id=tenant,
                name="Ordinal Test",
                steps=[
                    {"kind": "manual", "description": "step A", "ordinal": 50},
                    {"kind": "manual", "description": "step B", "ordinal": 10},
                    {"kind": "manual", "description": "step C", "ordinal": 99},
                ],
            )
        ordinals = [s["ordinal"] for s in version.steps_json]
        descs = [s["description"] for s in version.steps_json]
        ok = ordinals == [0, 1, 2] and descs == ["step A", "step B", "step C"]
        record("SEM-208", ok, f"ordinals={ordinals}, order preserved despite caller ordinals={descs}")
    except Exception:
        record("SEM-208", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-209 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            d1, _ = await dsvc.declare(tenant_id=tenant, name="D1")
            d2, _ = await dsvc.declare(tenant_id=tenant, name="D2")
            d3, _ = await dsvc.declare(tenant_id=tenant, name="D3")
            jsvc = JourneyService(uow)
            entity, _ = await jsvc.declare(
                tenant_id=tenant,
                name="Reorder Test",
                steps=[
                    {"kind": "dataset", "dataset_id": str(d1.id)},
                    {"kind": "dataset", "dataset_id": str(d2.id)},
                    {"kind": "dataset", "dataset_id": str(d3.id)},
                ],
            )
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            version = await jsvc.set_steps(
                tenant_id=tenant,
                journey_id=str(entity.id),
                steps=[
                    {"kind": "dataset", "dataset_id": str(d2.id)},
                    {"kind": "dataset", "dataset_id": str(d1.id)},
                ],
                reason="reordering",
            )
        new_order = [s["dataset_id"] for s in version.steps_json]
        ok = new_order == [str(d2.id), str(d1.id)]
        # Now check empty reason
        empty_reason_result = None
        try:
            async with database.unit_of_work() as uow:
                jsvc = JourneyService(uow)
                await jsvc.set_steps(
                    tenant_id=tenant,
                    journey_id=str(entity.id),
                    steps=[{"kind": "dataset", "dataset_id": str(d1.id)}],
                    reason="",
                )
            empty_reason_result = "accepted empty reason"
        except ValidationError as e:
            empty_reason_result = f"refused empty reason: {e.message}"
        record(
            "SEM-209",
            ok,
            f"new order={new_order}; empty reason behaviour: {empty_reason_result}",
        )
    except Exception:
        record("SEM-209", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-210 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                await jsvc.declare(
                    tenant_id=tenant,
                    name="Tier1 Journey",
                    criticality=1,
                    authored_by="alice",
                    approved_by="alice",
                )
                record("SEM-210", False, "no exception - self-approved tier1 journey accepted")
            except ValidationError as e:
                record("SEM-210", True, f"ValidationError: {e.message}")
    except Exception:
        record("SEM-210", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-211 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            entity, _ = await jsvc.declare(
                tenant_id=tenant,
                name="Tier1 Journey Approved",
                criticality=1,
                authored_by="alice",
                approved_by="bob",
                steps=[{"kind": "manual", "description": "FINREP step"}],
            )
        async with database.unit_of_work() as uow:
            jsvc = JourneyService(uow)
            try:
                version = await jsvc.set_steps(
                    tenant_id=tenant,
                    journey_id=str(entity.id),
                    steps=[],
                    reason="removed FINREP step",
                    authored_by="alice",
                )
                record(
                    "SEM-211",
                    True,
                    f"succeeded with single actor, no approver: steps={version.steps_json}",
                )
            except ValidationError as e:
                record(
                    "SEM-211",
                    False,
                    f"raised ValidationError (expected success per catalogue): {e.message}",
                )
    except Exception:
        record("SEM-211", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-212 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        secret_keys = list(ConnectionService.SECRET_KEYS)
        observed = []
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            try:
                await csvc.configure(
                    tenant_id=tenant,
                    name="Conn Password",
                    source_type="postgres",
                    config={"password": "hunter2"},
                )
                observed.append("password: no exception (FAIL)")
            except ValidationError as e:
                observed.append(f"password: ValidationError keys={e.context.get('keys')}")

        for key in secret_keys:
            async with database.unit_of_work() as uow:
                csvc = ConnectionService(uow)
                try:
                    await csvc.configure(
                        tenant_id=tenant,
                        name=f"Conn {key}",
                        source_type="postgres",
                        config={key: "hunter2"},
                    )
                    observed.append(f"{key}: no exception (FAIL)")
                except ValidationError as e:
                    observed.append(f"{key}: OK remedy_has_credential_ref={'credential_ref' in e.remedy}")

        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            try:
                await csvc.configure(
                    tenant_id=tenant,
                    name="Conn Upper",
                    source_type="postgres",
                    config={"PASSWORD": "hunter2"},
                )
                observed.append("PASSWORD upper: no exception (FAIL)")
            except ValidationError as e:
                observed.append(f"PASSWORD upper: OK keys={e.context.get('keys')}")
        ok = all("FAIL" not in o for o in observed)
        record("SEM-212", ok, "; ".join(observed))
    except Exception:
        record("SEM-212", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-213 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        observed = []
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            try:
                entity, _ = await csvc.configure(
                    tenant_id=tenant,
                    name="Conn Empty Str",
                    source_type="postgres",
                    config={"password": ""},
                )
                observed.append("empty string password: accepted OK")
            except Exception as e:
                observed.append(f"empty string password: raised {type(e).__name__}: {e} (FAIL)")
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            try:
                entity, _ = await csvc.configure(
                    tenant_id=tenant,
                    name="Conn None",
                    source_type="postgres",
                    config={"password": None},
                )
                observed.append("None password: accepted OK")
            except Exception as e:
                observed.append(f"None password: raised {type(e).__name__}: {e} (FAIL)")
        ok = all("FAIL" not in o for o in observed)
        record("SEM-213", ok, "; ".join(observed))
    except Exception:
        record("SEM-213", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-214 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        observed = []
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            try:
                entity, _ = await csvc.configure(
                    tenant_id=tenant,
                    name="Conn Nested Pw",
                    source_type="postgres",
                    config={"auth": {"password": "hunter2"}},
                )
                observed.append("nested auth.password: accepted (matches catalogue: currently accepted)")
            except ValidationError as e:
                observed.append(f"nested auth.password: refused (FAIL vs catalogue) {e.message}")
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            try:
                entity, _ = await csvc.configure(
                    tenant_id=tenant,
                    name="Conn Jdbc Url",
                    source_type="postgres",
                    config={"jdbc_url": "jdbc:postgresql://host/db?password=hunter2"},
                )
                observed.append("jdbc_url with embedded password: accepted (matches catalogue)")
            except ValidationError as e:
                observed.append(f"jdbc_url embedded password: refused (FAIL vs catalogue) {e.message}")
        ok = all("FAIL" not in o for o in observed)
        record("SEM-214", ok, "; ".join(observed))
    except Exception:
        record("SEM-214", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-215, SEM-216, SEM-217 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        import os

        os.environ["PG_PASSWORD"] = "hunter2-secret-value"
        registry = register_builtin(ConnectorRegistry())
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            entity, version = await csvc.configure(
                tenant_id=tenant,
                name="PG Conn",
                source_type="postgresql",
                credential_ref="env://PG_PASSWORD",
                config={"host": "localhost", "database": "acme", "schemas": ["public"]},
            )
            connection_id = str(entity.id)
        async with database.unit_of_work() as uow:
            connsvc = ConnectivityService(uow, registry=registry)
            try:
                connector = await connsvc.connector_for(connection_id)
                cred_field = type(connector).credential_field
                injected = getattr(connector, "_password", None) or getattr(
                    connector, cred_field, None
                )
                observed215 = f"connector built; credential_field={cred_field!r} _password={getattr(connector, '_password', 'N/A')!r}"
                ok215 = getattr(connector, "_password", None) == "hunter2-secret-value"
            except Exception as e:
                observed215 = f"connector build raised {type(e).__name__}: {e}"
                ok215 = False
        async with database.unit_of_work() as uow:
            stored = await uow.connections.current(connection_id, tenant_id=tenant)
        stored_unchanged = stored.config_json == {
            "host": "localhost",
            "database": "acme",
            "schemas": ["public"],
        }
        record(
            "SEM-215",
            ok215 and stored_unchanged,
            f"{observed215}; stored_config_json={stored.config_json!r} (unchanged={stored_unchanged})",
        )

        # SEM-216: credential_ref None
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            entity2, _ = await csvc.configure(
                tenant_id=tenant,
                name="FS Conn",
                source_type="filesystem",
                credential_ref=None,
                config={"root_path": "/data/in"},
            )
            connection_id2 = str(entity2.id)
        async with database.unit_of_work() as uow:
            connsvc = ConnectivityService(uow, registry=registry)
            try:
                connector = await connsvc.connector_for(connection_id2)
                observed216 = f"connector built OK: {type(connector).__name__}"
                ok216 = True
            except ValidationError as e:
                observed216 = f"ValidationError (no connector installed for 'filesystem'?): {e.message}"
                ok216 = "no connector is installed" in e.message
            except Exception as e:
                observed216 = f"{type(e).__name__}: {e}"
                ok216 = False
        record("SEM-216", ok216, observed216)

        # SEM-217: source_type with no connector
        async with database.unit_of_work() as uow:
            csvc = ConnectionService(uow)
            entity3, _ = await csvc.configure(
                tenant_id=tenant,
                name="Teradata Conn",
                source_type="teradata",
                config={},
            )
            connection_id3 = str(entity3.id)
        async with database.unit_of_work() as uow:
            connsvc = ConnectivityService(uow, registry=registry)
            try:
                await connsvc.connector_for(connection_id3)
                observed217 = "no exception raised (FAIL)"
                ok217 = False
            except ValidationError as e:
                installed_list_present = "Installed:" in e.remedy
                ok217 = installed_list_present and "source_type" in e.context
                observed217 = f"ValidationError remedy={e.remedy!r} context={e.context!r}"
        record("SEM-217", ok217, observed217)
    except Exception:
        record("SEM-215", False, "EXC:" + traceback.format_exc())
        record("SEM-216", False, "blocked")
        record("SEM-217", False, "blocked")
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-218 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, _ = await dsvc.declare(tenant_id=tenant, name="Bindable DS")
            csvc = ConnectionService(uow)
            conn, _ = await csvc.configure(tenant_id=tenant, name="A conn", source_type="file")
        observed = []
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            try:
                await bsvc.bind_dataset(
                    tenant_id=tenant,
                    dataset_id="01INVENTEDDATASETID000000",
                    connection_id=str(conn.id),
                    physical_ref={},
                )
                observed.append("invented dataset: no exception (FAIL)")
            except NotFoundError as e:
                observed.append(f"invented dataset: NotFoundError {e.message!r} remedy={e.remedy!r}")
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            try:
                await bsvc.bind_dataset(
                    tenant_id=tenant,
                    dataset_id=str(dataset.id),
                    connection_id="01INVENTEDCONNECTIONID000",
                    physical_ref={},
                )
                observed.append("invented connection: no exception (FAIL)")
            except NotFoundError as e:
                observed.append(f"invented connection: NotFoundError {e.message!r} remedy={e.remedy!r}")
        ok = all("NotFoundError" in o for o in observed)
        record("SEM-218", ok, "; ".join(observed))
    except Exception:
        record("SEM-218", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-219 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, _ = await dsvc.declare(tenant_id=tenant, name="Unbound DS")
            csvc = ConnectionService(uow)
            conn, _ = await csvc.configure(tenant_id=tenant, name="Conn X", source_type="file")
            dataset_id = str(dataset.id)
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=dataset_id,
                connection_id=str(conn.id),
                physical_ref={"path": "x"},
                shape="table",
            )
        async with database.unit_of_work() as uow:
            current = await uow.datasets.current(dataset_id, tenant_id=tenant)
            from prama.semantic.services.estate import EstateService

            gaps = await EstateService(uow).coverage_gaps(tenant)
        ok = current.shape == "table" and current.is_bound and current.name not in gaps["unbound"]
        record(
            "SEM-219",
            ok,
            f"shape={current.shape!r} is_bound={current.is_bound} in unbound_gap={current.name in gaps['unbound']}",
        )
    except Exception:
        record("SEM-219", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-220 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, _ = await dsvc.declare(tenant_id=tenant, name="Proposed Bind DS")
            csvc = ConnectionService(uow)
            conn, _ = await csvc.configure(tenant_id=tenant, name="Conn Y", source_type="file")
            dataset_id = str(dataset.id)
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            entity, version = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=dataset_id,
                connection_id=str(conn.id),
                physical_ref={"path": "y"},
                confirmed=False,
            )
        async with database.unit_of_work() as uow:
            current = await uow.datasets.current(dataset_id, tenant_id=tenant)
        ok = version.status == "proposed" and version.drift_state == "unknown" and current.is_bound
        record(
            "SEM-220",
            ok,
            f"status={version.status!r} drift_state={version.drift_state!r} dataset.is_bound={current.is_bound} shape={current.shape!r}",
        )
    except Exception:
        record("SEM-220", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-221 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, _ = await dsvc.declare(tenant_id=tenant, name="Bad Shape DS")
            csvc = ConnectionService(uow)
            conn, _ = await csvc.configure(tenant_id=tenant, name="Conn Z", source_type="file")
            dataset_id = str(dataset.id)
        try:
            async with database.unit_of_work() as uow:
                bsvc = BindingService(uow)
                entity, version = await bsvc.bind_dataset(
                    tenant_id=tenant,
                    dataset_id=dataset_id,
                    connection_id=str(conn.id),
                    physical_ref={},
                    shape="parquet_directory",
                )
            record(
                "SEM-221",
                False,
                "invalid shape was accepted and committed with no error at all "
                "(catalogue expects the column CHECK, per SEM-162, to refuse it)",
            )
        except Exception as e:
            # SEM-162 (same code path) documents the expected behaviour as
            # "refused by the column CHECK" -- an unvalidated value reaching an
            # uncaught database-level rejection, not a friendly ValidationError.
            hit_check_constraint = "ck_sem_dataset_shape" in str(e)
            record(
                "SEM-221",
                hit_check_constraint,
                f"raised {type(e).__name__} on commit: no application-level "
                f"ValidationError intercepts the shape before the write; the value "
                f"reaches the database exactly as SEM-162 describes and is refused "
                f"there ({'ck_sem_dataset_shape' if hit_check_constraint else 'other cause'})",
            )
    except Exception:
        record("SEM-221", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-222, SEM-223, SEM-224 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            d_missing, _ = await dsvc.declare(tenant_id=tenant, name="D Missing")
            d_changed, _ = await dsvc.declare(tenant_id=tenant, name="D Changed")
            d_intact, _ = await dsvc.declare(tenant_id=tenant, name="D Intact")
            csvc = ConnectionService(uow)
            conn, _ = await csvc.configure(tenant_id=tenant, name="Conn Drift", source_type="file")
            bsvc = BindingService(uow)
            b_missing, _ = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=str(d_missing.id),
                connection_id=str(conn.id),
                physical_ref={},
            )
            b_changed, _ = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=str(d_changed.id),
                connection_id=str(conn.id),
                physical_ref={},
            )
            b_intact, _ = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=str(d_intact.id),
                connection_id=str(conn.id),
                physical_ref={},
            )
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            v_missing = await bsvc.record_drift(
                tenant_id=tenant, binding_id=str(b_missing.id), drift_state="missing"
            )
        changed_error = None
        v_changed = None
        try:
            async with database.unit_of_work() as uow:
                bsvc = BindingService(uow)
                v_changed = await bsvc.record_drift(
                    tenant_id=tenant, binding_id=str(b_changed.id), drift_state="changed"
                )
        except Exception as e:
            changed_error = f"{type(e).__name__}: {str(e)[:150]}"
        if v_changed is not None:
            ok222 = v_missing.status == "broken" and v_changed.status == "confirmed"
            observed222 = (
                f"missing->status={v_missing.status!r}; "
                f"changed->status={v_changed.status!r} (was confirmed)"
            )
        else:
            ok222 = False
            observed222 = (
                f"missing->status={v_missing.status!r} (OK); "
                f"'changed' step RAISED instead of succeeding: {changed_error} "
                f"-- the DB CHECK constraint ck_sem_binding_drift only permits "
                f"('unknown','intact','missing','retyped','renamed'), so 'changed' "
                f"is rejected at the database layer as an unhandled IntegrityError, "
                f"not stored as the catalogue expects"
            )
        record("SEM-222", ok222, observed222)

        gone_error = None
        v_gone = None
        try:
            async with database.unit_of_work() as uow:
                bsvc = BindingService(uow)
                v_gone = await bsvc.record_drift(
                    tenant_id=tenant, binding_id=str(b_intact.id), drift_state="gone"
                )
        except Exception as e:
            gone_error = f"{type(e).__name__}: {str(e)[:150]}"
        if v_gone is not None:
            ok223 = v_gone.drift_state == "gone" and v_gone.status == "confirmed"
            observed223 = (
                f"drift_state stored={v_gone.drift_state!r}; "
                f"status unchanged={v_gone.status!r} (was confirmed)"
            )
        else:
            ok223 = False
            observed223 = (
                f"'gone' RAISED instead of being stored: {gone_error} -- the DB CHECK "
                f"constraint ck_sem_binding_drift rejects any value outside "
                f"('unknown','intact','missing','retyped','renamed'); an 'unknown' "
                f"drift state (in the sense of not one of the five known literals) is "
                f"in fact refused, not accepted"
            )
        record("SEM-223", ok223, observed223)

        # SEM-224: use a fresh, independent fixture with only DB-permitted
        # drift_state values (missing/retyped/intact) so the case is not
        # blocked by the SEM-222/223 findings above.
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            d2_missing, _ = await dsvc.declare(tenant_id=tenant, name="D2 Missing")
            d2_retyped, _ = await dsvc.declare(tenant_id=tenant, name="D2 Retyped")
            d2_intact, _ = await dsvc.declare(tenant_id=tenant, name="D2 Intact")
            bsvc = BindingService(uow)
            b2_missing, _ = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=str(d2_missing.id),
                connection_id=str(conn.id),
                physical_ref={},
            )
            b2_retyped, _ = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=str(d2_retyped.id),
                connection_id=str(conn.id),
                physical_ref={},
            )
            b2_intact, _ = await bsvc.bind_dataset(
                tenant_id=tenant,
                dataset_id=str(d2_intact.id),
                connection_id=str(conn.id),
                physical_ref={},
            )
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            await bsvc.record_drift(
                tenant_id=tenant, binding_id=str(b2_missing.id), drift_state="missing"
            )
        async with database.unit_of_work() as uow:
            bsvc = BindingService(uow)
            await bsvc.record_drift(
                tenant_id=tenant, binding_id=str(b2_retyped.id), drift_state="retyped"
            )
        # b2_intact stays drift_state="intact" (its default from bind_dataset)
        async with database.unit_of_work() as uow:
            from prama.semantic.services.estate import EstateService

            gaps = await EstateService(uow).coverage_gaps(tenant)
        drifted_ids = set(gaps["drifted_bindings"])
        ok224 = (
            str(d2_missing.id) in drifted_ids
            and str(d2_retyped.id) in drifted_ids
            and str(d2_intact.id) not in drifted_ids
        )
        record(
            "SEM-224",
            ok224,
            f"drifted_bindings={drifted_ids}; d2_missing={d2_missing.id} "
            f"d2_retyped={d2_retyped.id} d2_intact={d2_intact.id}",
        )
    except Exception:
        record("SEM-222", False, "EXC:" + traceback.format_exc())
        record("SEM-223", False, "blocked")
        record("SEM-224", False, "blocked")
    finally:
        await database.stop()
        database.sync_engine().dispose()

    print("\n\n==== SUMMARY ====")
    for k, (r, o) in results.items():
        print(f"{k}\t{r}\t{o}")


asyncio.run(main())
