import asyncio
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db import Database
from prama.semantic.services import DatasetService

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


def record(case_id, outcome):
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

        # ============ SEM-155: declare with name alone; defaults ============
        try:
            async with database.unit_of_work() as uow:
                entity, version = await DatasetService(uow).declare(
                    tenant_id=tenant_id, name="Global Positions"
                )
                obs = {
                    "shape": version.shape, "criticality": version.criticality,
                    "temporality": version.temporality, "sensitivity": version.sensitivity,
                    "authoritativeness": version.authoritativeness,
                    "lifecycle_state": version.lifecycle_state,
                }
            record("SEM-155", obs)
        except Exception as e:
            record("SEM-155", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-156: unbound dataset is first class ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="Unbound One")
                ds2, _ = await svc.declare(tenant_id=tenant_id, name="Unbound Two")
                from prama.semantic.services import EstateService, RelationshipService
                from prama.semantic.relationships import MatchKey, RelationshipDeclaration, RelationshipKind
                estate = EstateService(uow)
                gaps = await estate.coverage_gaps(tenant_id)
                in_gaps = "Unbound One" in gaps["unbound"]
                listed = await uow.datasets.list_current(tenant_id, limit=1000)
                on_list = any(d.name == "Unbound One" for d in listed)
                rel_svc = RelationshipService(uow)
                rel_entity, rel_version = await rel_svc.declare(
                    tenant_id=tenant_id,
                    declaration=RelationshipDeclaration(
                        kind=RelationshipKind.REFERENCES,
                        from_dataset_id=str(ds.id), to_dataset_id=str(ds2.id),
                        match_keys=(MatchKey("k"),),
                    ),
                )
                rel_ok = rel_version.is_confirmed
            record("SEM-156", f"in coverage_gaps['unbound']={in_gaps}; in list_current={on_list}; relationship declared and confirmed={rel_ok}")
        except Exception as e:
            record("SEM-156", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-157: declare approved -> active; unapproved -> proposed ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                _, v_unapproved = await svc.declare(
                    tenant_id=tenant_id, name="T3 Unapproved", criticality=3, approved_by=None
                )
                _, v_approved = await svc.declare(
                    tenant_id=tenant_id, name="T3 Approved", criticality=3, approved_by="bob"
                )
            record("SEM-157", f"unapproved.lifecycle_state={v_unapproved.lifecycle_state}; approved.lifecycle_state={v_approved.lifecycle_state}")
        except Exception as e:
            record("SEM-157", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-158: duplicate name refused (punctuation-insensitive) ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                await svc.declare(tenant_id=tenant_id, name="Global Positions Dup")
                r1 = None
                try:
                    await svc.declare(tenant_id=tenant_id, name="global positions dup")
                except ConflictError as e:
                    r1 = f"ConflictError: {e}"
                r2 = None
                try:
                    await svc.declare(tenant_id=tenant_id, name="Global-Positions-Dup")
                except ConflictError as e:
                    r2 = f"ConflictError: {e}"
            record("SEM-158", f"lower-case variant -> {r1}; punctuation variant -> {r2}")
        except Exception as e:
            record("SEM-158", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-159: same name, two tenants, both created, isolated ============
        try:
            async with database.unit_of_work() as uow:
                entity_a, _ = await DatasetService(uow).declare(tenant_id=tenant_id, name="Shared Name DS")
            async with database.unit_of_work() as uow:
                entity_b, _ = await DatasetService(uow).declare(tenant_id=tenant_b_id, name="Shared Name DS")
            async with database.unit_of_work() as uow:
                found_in_a_for_b_tenant = await uow.datasets.by_slug(tenant_b_id, "shared_name_ds")
                found_in_b_for_a_tenant = await uow.datasets.by_slug(tenant_id, "shared_name_ds")
                a_current = await uow.datasets.current(str(entity_a.id), tenant_id=tenant_id)
                a_current_from_b = await uow.datasets.current(str(entity_a.id), tenant_id=tenant_b_id)
            record("SEM-159", f"both created (a={entity_a.id!r}, b={entity_b.id!r}); a_current from tenant A={a_current is not None}; a's dataset visible under tenant B scope={a_current_from_b is not None}")
        except Exception as e:
            record("SEM-159", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-160: Tier 1 self-approved refused before write ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                before_count = len(await uow.datasets.list_current(tenant_id, limit=10000))
                try:
                    await svc.declare(
                        tenant_id=tenant_id, name="Tier1 Self Approved", criticality=1,
                        authored_by="alice", approved_by="alice",
                    )
                    outcome = "NO EXCEPTION RAISED (unexpected)"
                except ValidationError as e:
                    outcome = f"ValidationError: {e}"
                after_count = len(await uow.datasets.list_current(tenant_id, limit=10000))
                found_slug = await uow.datasets.by_slug(tenant_id, "tier1_self_approved")
                # audit check
                events = await uow.audit.recent(tenant_id, limit=200)
                related_events = [e for e in events if "tier1" in (e.detail_json or {}).get("slug", "")]
            record("SEM-160", f"{outcome}; dataset_count before={before_count} after={after_count}; by_slug found={found_slug is not None}; audit rows mentioning slug={len(related_events)}")
        except Exception as e:
            record("SEM-160", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-161: unvalidated criticality reaches DB ============
        try:
            results = {}
            for crit in (0, 9):
                async with database.unit_of_work() as uow:
                    svc = DatasetService(uow)
                    try:
                        entity, version = await svc.declare(
                            tenant_id=tenant_id, name=f"Bad Crit {crit}", criticality=crit
                        )
                        results[crit] = f"accepted; version.criticality={version.criticality}"
                    except Exception as e:
                        results[crit] = f"{type(e).__module__}.{type(e).__name__}: {e}"
                        await uow.rollback()
            record("SEM-161", results)
        except Exception as e:
            record("SEM-161", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-162: unvalidated shape reaches DB ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                try:
                    entity, version = await svc.declare(
                        tenant_id=tenant_id, name="Bad Shape DS", shape="spreadsheet"
                    )
                    outcome = f"accepted; version.shape={version.shape}"
                except Exception as e:
                    outcome = f"{type(e).__module__}.{type(e).__name__}: {e}"
                    await uow.rollback()
            record("SEM-162", outcome)
        except Exception as e:
            record("SEM-162", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-163: unvalidated temporality/sensitivity/authoritativeness ============
        try:
            results = {}
            for field, badval in (
                ("temporality", "bitemporal"), ("sensitivity", "secret"), ("authoritativeness", "best_effort")
            ):
                async with database.unit_of_work() as uow:
                    svc = DatasetService(uow)
                    try:
                        kwargs = {field: badval}
                        entity, version = await svc.declare(
                            tenant_id=tenant_id, name=f"Bad {field}", **kwargs
                        )
                        results[field] = f"accepted; version.{field}={getattr(version, field)}"
                    except Exception as e:
                        results[field] = f"{type(e).__name__}: {e}"
            # Now check derive/persisted.py::_enum fallback behavior for a bad value that did reach storage
            fallback_obs = "not tested"
            try:
                from prama.derive.persisted import dataset_declaration_of
                async with database.unit_of_work() as uow:
                    svc = DatasetService(uow)
                    entity, version = await svc.declare(tenant_id=tenant_id, name="Bad Sensitivity For Derive", sensitivity="secret")
                    decl = dataset_declaration_of(version)
                    fallback_obs = f"derive read back sensitivity={decl.sensitivity!r} (raw stored value was 'secret')"
            except Exception as e:
                fallback_obs = f"EXC during derive check: {type(e).__name__}: {e}"
            record("SEM-163", f"{results}; derive fallback: {fallback_obs}")
        except Exception as e:
            record("SEM-163", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-164: amend without reason refused ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                entity, _ = await svc.declare(tenant_id=tenant_id, name="Amend Reason DS")
                results = {}
                for reason in ("", "   "):
                    try:
                        await svc.amend(tenant_id=tenant_id, dataset_id=str(entity.id), reason=reason, purpose="x")
                        results[repr(reason)] = "NO EXCEPTION (unexpected)"
                    except ValidationError as e:
                        results[repr(reason)] = f"ValidationError: {e}"
            record("SEM-164", results)
        except Exception as e:
            record("SEM-164", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-165: correct without reason refused ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                entity, _ = await svc.declare(tenant_id=tenant_id, name="Correct Reason DS")
                try:
                    await svc.correct(tenant_id=tenant_id, dataset_id=str(entity.id), reason="", description="x")
                    outcome = "NO EXCEPTION (unexpected)"
                except ValidationError as e:
                    outcome = f"ValidationError: {e}"
            record("SEM-165", outcome)
        except Exception as e:
            record("SEM-165", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-166: amend checks policy against NEW criticality ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                entity, _ = await svc.declare(tenant_id=tenant_id, name="T4 To T1 DS", criticality=4)
                try:
                    await svc.amend(
                        tenant_id=tenant_id, dataset_id=str(entity.id), reason="promote to tier1",
                        criticality=1, authored_by="alice", approved_by="alice",
                    )
                    outcome = "NO EXCEPTION (unexpected) -- self-approved promotion to Tier 1 succeeded"
                except ValidationError as e:
                    outcome = f"ValidationError: {e}"
            record("SEM-166", outcome)
        except Exception as e:
            record("SEM-166", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-167: amendment not touching criticality uses current (Tier1) ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                entity, _ = await svc.declare(
                    tenant_id=tenant_id, name="Tier1 Stays DS", criticality=1,
                    authored_by="alice", approved_by="bob",
                )
                try:
                    await svc.amend(
                        tenant_id=tenant_id, dataset_id=str(entity.id), reason="update description only",
                        description="new description", authored_by="alice", approved_by="alice",
                    )
                    outcome = "NO EXCEPTION (unexpected) -- description-only amendment to Tier1 bypassed policy"
                except ValidationError as e:
                    outcome = f"ValidationError: {e}"
            record("SEM-167", outcome)
        except Exception as e:
            record("SEM-167", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-168: correct bypasses approval policy entirely ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                entity, _ = await svc.declare(
                    tenant_id=tenant_id, name="Tier1 Correct Bypass DS", criticality=1,
                    authored_by="alice", approved_by="bob",
                )
                try:
                    version = await svc.correct(
                        tenant_id=tenant_id, dataset_id=str(entity.id), reason="wrong grain",
                        authored_by="alice", criticality=1, description="corrected description",
                    )
                    outcome = f"SUCCEEDED with no approver -- version.criticality={version.criticality}, version.approved_by={version.approved_by!r}"
                except ValidationError as e:
                    outcome = f"REFUSED -- ValidationError: {e}"
            record("SEM-168", outcome)
        except Exception as e:
            record("SEM-168", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-169: amend missing dataset -> NotFoundError ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                try:
                    await svc.amend(
                        tenant_id=tenant_id, dataset_id="01AAAAAAAAAAAAAAAAAAAAAAAA", reason="x"
                    )
                    outcome = "NO EXCEPTION (unexpected)"
                except NotFoundError as e:
                    outcome = f"NotFoundError: {e}"
            record("SEM-169", outcome)
        except Exception as e:
            record("SEM-169", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-170: amend another tenant's dataset -> NotFoundError not 403 ============
        try:
            async with database.unit_of_work() as uow:
                entity_a, _ = await DatasetService(uow).declare(tenant_id=tenant_id, name="CrossTenant DS")
                a_id = str(entity_a.id)
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                try:
                    await svc.amend(tenant_id=tenant_b_id, dataset_id=a_id, reason="trying cross tenant")
                    outcome = "NO EXCEPTION (unexpected)"
                except NotFoundError as e:
                    outcome = f"NotFoundError: {e}"
                except Exception as e:
                    outcome = f"OTHER EXC {type(e).__name__}: {e}"
                # verify nothing written: current version under tenant A unaffected
                current_a = await uow.datasets.current(a_id, tenant_id=tenant_id)
            record("SEM-170", f"{outcome}; tenant A's current version version_number={current_a.version if current_a else None}")
        except Exception as e:
            record("SEM-170", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-171: declare_attribute on missing dataset -> NotFoundError ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                try:
                    await svc.declare_attribute(
                        tenant_id=tenant_id, dataset_id="01AAAAAAAAAAAAAAAAAAAAAAAA", name="x"
                    )
                    outcome = "NO EXCEPTION (unexpected)"
                except NotFoundError as e:
                    outcome = f"NotFoundError: {e}"
            record("SEM-171", outcome)
        except Exception as e:
            record("SEM-171", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-172: duplicate attribute name refused ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="Dup Attr DS")
                await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="amount")
                try:
                    await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="amount")
                    outcome = "NO EXCEPTION (unexpected)"
                except ConflictError as e:
                    outcome = f"ConflictError: {e}"
            record("SEM-172", outcome)
        except Exception as e:
            record("SEM-172", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-173: attribute names matched exactly, not by slug (case) ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="Case Attr DS")
                await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="amount")
                r1 = "accepted"
                try:
                    await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="Amount")
                except ConflictError as e:
                    r1 = f"ConflictError: {e}"
                r2 = "accepted"
                try:
                    await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="AMOUNT")
                except ConflictError as e:
                    r2 = f"ConflictError: {e}"
            record("SEM-173", f"'Amount' -> {r1}; 'AMOUNT' -> {r2}")
        except Exception as e:
            record("SEM-173", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-174: ordinal is declaration order ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="Ordinal DS")
                _, v1 = await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="a1")
                _, v2 = await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="a2")
                _, v3 = await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="a3")
                ordinals = [v1.ordinal, v2.ordinal, v3.ordinal]
                # retire a1 then declare a4 - check if 4th gets ordinal 3 (len(existing)) even though max ordinal diverges
                attr1_id = None
                existing = await uow.attributes.for_dataset(str(ds.id), tenant_id=tenant_id)
                a1_entity_id = [a.attribute_id for a in existing if a.name == "a1"][0]
                await uow.attributes.retire(a1_entity_id, tenant_id=tenant_id)
                _, v4 = await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(ds.id), name="a4")
            record("SEM-174", f"first three ordinals={ordinals}; after retiring a1, a4's ordinal={v4.ordinal} (existing count at declare time was 2 since a1 retired)")
        except Exception as e:
            record("SEM-174", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-175: attribute extra fields pass through unvalidated ============
        results = {}
        async with database.unit_of_work() as uow:
            svc = DatasetService(uow)
            ds175, _ = await svc.declare(tenant_id=tenant_id, name="Extra Fields DS")
            ds175_id = str(ds175.id)

        for label, kwargs in (
            ("optionality=sometimes", {"optionality": "sometimes"}),
            ("value_domain_json.kind=colour", {"value_domain_json": {"kind": "colour"}}),
            ("numeric_scale=-3", {"numeric_scale": -3}),
            ("currency_attribute=no_such_column (service-layer)", {"currency_attribute": "no_such_column"}),
        ):
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                try:
                    name = "attr_" + label.split("=")[0].split(".")[0].replace(" ", "_")
                    _, v = await svc.declare_attribute(
                        tenant_id=tenant_id, dataset_id=ds175_id, name=name, **kwargs
                    )
                    field = list(kwargs)[0]
                    results[label] = f"accepted; stored={getattr(v, field, '<attr not on model>')!r}"
                except Exception as e:
                    results[label] = f"{type(e).__module__}.{type(e).__name__}: {e}"
                    await uow.rollback()

        # verify the currency_attribute claim reaches Gamma as Unsatisfiable attribute.currency
        try:
            from prama.derive.generator import ControlGenerator, Unsatisfiable
            from prama.derive.persisted import dataset_declaration_of, attribute_declaration_of
            async with database.unit_of_work() as uow:
                ds_version = await uow.datasets.by_slug(tenant_id, "extra_fields_ds")
                attrs = await uow.attributes.for_dataset(ds175_id, tenant_id=tenant_id)
                ccy_attr = [a for a in attrs if a.name == "attr_currency_attribute"][0]
                declaration = dataset_declaration_of(ds_version, attributes=[ccy_attr])
            gen = ControlGenerator()
            generation = gen.generate(declaration)
            currency_unsat = [u for u in generation.unsatisfiable if u.rule == "attribute.currency"]
            results["Gamma_generation_for_currency_attribute"] = (
                f"unsatisfiable_rules_found={[(u.rule, u.reason) for u in currency_unsat]}"
            )
        except Exception as e:
            results["Gamma_generation_for_currency_attribute"] = f"EXC {type(e).__module__}.{type(e).__name__}: {e}"
            traceback.print_exc()

        record("SEM-175", results)

        # ============ SEM-176: is_cde + obligations in audit detail / obligations_json ============
        try:
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="CDE DS")
                entity, version = await svc.declare_attribute(
                    tenant_id=tenant_id, dataset_id=str(ds.id), name="cde_attr",
                    is_cde=True, obligations=["FR Y-14Q"], authored_by="alice",
                )
                await uow.flush()
                events = await uow.audit.for_object(tenant_id, "attribute", str(entity.id))
                detail = events[0].detail_json if events else None
            record("SEM-176", f"audit detail={detail}; version.obligations_json={version.obligations_json}")
        except Exception as e:
            record("SEM-176", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ Extra check: set_steps() also bypasses approval policy (flagged defect) ============
        try:
            from prama.semantic.services.graph import JourneyService
            async with database.unit_of_work() as uow:
                svc = DatasetService(uow)
                ds, _ = await svc.declare(tenant_id=tenant_id, name="Journey Bypass DS")
                journey_svc = JourneyService(uow)
                entity, version = await journey_svc.declare(
                    tenant_id=tenant_id, name="Tier1 Journey", criticality=1,
                    authored_by="alice", approved_by="bob",
                    steps=[{"kind": "dataset", "dataset_id": str(ds.id)}],
                )
                import inspect
                sig = str(inspect.signature(journey_svc.set_steps))
                new_version = await journey_svc.set_steps(
                    tenant_id=tenant_id, journey_id=str(entity.id), reason="sole-author change",
                    authored_by="alice",
                    steps=[{"kind": "dataset", "dataset_id": str(ds.id)}],
                )
            print(f"EXTRA CHECK set_steps signature={sig}; set_steps on Tier-1 journey by sole author (no approver param exists at all) -> SUCCEEDED, new version={new_version.version}, approved_by={new_version.approved_by!r}")
        except Exception as e:
            print(f"EXTRA CHECK set_steps bypass -> EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        print("=== DONE datasets.py section ===")
    finally:
        await database.stop()
        database.sync_engine().dispose()


asyncio.run(main())
