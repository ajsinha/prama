import asyncio
import tempfile
import traceback
from pathlib import Path

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.semantic.services import DatasetService
from prama.semantic.services.graph import ConceptService, JourneyService
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.services import RelationshipService
from prama.semantic.services.estate import EstateService
from prama.semantic.values import Grain, Rhythm, Frequency

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
    # ---------- SEM-225 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            d1, _ = await dsvc.declare(
                tenant_id=tenant,
                name="D1",
                owner_id="alice",
                criticality=1,
                grain=Grain(("id",)),
                rhythm=Rhythm(Frequency.DAILY),
                authored_by="alice",
                approved_by="bob",
            )
            d2, _ = await dsvc.declare(tenant_id=tenant, name="D2", owner_id="bob")
            d3, _ = await dsvc.declare(tenant_id=tenant, name="D3")  # unowned, no grain
            await dsvc.declare_attribute(
                tenant_id=tenant,
                dataset_id=str(d1.id),
                name="a1",
                definition="def1",
                is_cde=True,
            )
            await dsvc.declare_attribute(
                tenant_id=tenant, dataset_id=str(d1.id), name="a2"
            )  # no def
            await dsvc.declare_attribute(tenant_id=tenant, dataset_id=str(d2.id), name="b1")
            csvc = ConceptService(uow)
            concept, _ = await csvc.declare_concept(tenant_id=tenant, name="Concept1")
            prop, _ = await csvc.declare_property(
                tenant_id=tenant, concept_id=str(concept.id), name="Prop1"
            )
            attrs_d1 = await uow.attributes.for_dataset(str(d1.id), tenant_id=tenant)
            await csvc.map_attribute(
                tenant_id=tenant,
                attribute_id=str(attrs_d1[0].attribute_id),
                property_id=str(prop.id),
            )
            rsvc = RelationshipService(uow)
            await rsvc.declare(
                tenant_id=tenant,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=str(d1.id),
                    to_dataset_id=str(d2.id),
                    match_keys=(MatchKey("id"),),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="USD"),
                ),
            )
            jsvc = JourneyService(uow)
            await jsvc.declare(
                tenant_id=tenant,
                name="J1",
                steps=[{"kind": "dataset", "dataset_id": str(d1.id)}],
            )
        async with database.unit_of_work() as uow:
            facts = await EstateService(uow).gather_facts(tenant)
        # hand count:
        expected = dict(
            datasets=3,
            datasets_owned=2,
            datasets_with_grain=1,
            datasets_with_rhythm=1,
            datasets_bound=0,
            attributes=3,
            attributes_defined=1,
            attributes_mapped_to_concepts=1,
            critical_data_elements=1,
            tier_one_datasets=1,
            tier_one_datasets_with_grain=1,
            relationships_confirmed=1,
            journeys=1,
            journey_datasets=1,
        )
        actual = dict(
            datasets=facts.datasets,
            datasets_owned=facts.datasets_owned,
            datasets_with_grain=facts.datasets_with_grain,
            datasets_with_rhythm=facts.datasets_with_rhythm,
            datasets_bound=facts.datasets_bound,
            attributes=facts.attributes,
            attributes_defined=facts.attributes_defined,
            attributes_mapped_to_concepts=facts.attributes_mapped_to_concepts,
            critical_data_elements=facts.critical_data_elements,
            tier_one_datasets=facts.tier_one_datasets,
            tier_one_datasets_with_grain=facts.tier_one_datasets_with_grain,
            relationships_confirmed=facts.relationships_confirmed,
            journeys=facts.journeys,
            journey_datasets=facts.journey_datasets,
        )
        ok = expected == actual
        record("SEM-225", ok, f"expected={expected} actual={actual}")

        # save these ids for SEM-226/227
        sem226_ids = (tenant, str(d1.id), str(d2.id), str(d3.id))
    except Exception:
        record("SEM-225", False, "EXC:" + traceback.format_exc())
        sem226_ids = None
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-226, SEM-227 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            from prama.semantic.services.graph import ConceptService as _CS
            from prama.db.dao.semantic import DomainDao

            domain_a = await uow.domains.create(tenant_id=tenant, name="Domain A")
            domain_b = await uow.domains.create(tenant_id=tenant, name="Domain B")
            domain_empty = await uow.domains.create(tenant_id=tenant, name="Domain Empty")
            domain_a_id = str(domain_a[0].id)
            domain_b_id = str(domain_b[0].id)
            domain_empty_id = str(domain_empty[0].id)

            dsvc = DatasetService(uow)
            da1, _ = await dsvc.declare(tenant_id=tenant, name="DA1", domain_id=domain_a_id)
            da2, _ = await dsvc.declare(tenant_id=tenant, name="DA2", domain_id=domain_a_id)
            db1, _ = await dsvc.declare(tenant_id=tenant, name="DB1", domain_id=domain_b_id)

            rsvc = RelationshipService(uow)
            await rsvc.declare(
                tenant_id=tenant,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=str(db1.id),
                    to_dataset_id=str(da1.id),
                    match_keys=(MatchKey("id"),),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="USD"),
                ),
            )
        async with database.unit_of_work() as uow:
            facts_a = await EstateService(uow).gather_facts(tenant, domain_id=domain_a_id)
        ok226 = facts_a.datasets == 2 and facts_a.relationships_confirmed == 1
        record(
            "SEM-226",
            ok226,
            f"domain A: datasets={facts_a.datasets} (expect 2) "
            f"relationships_confirmed={facts_a.relationships_confirmed} (expect 1, "
            f"touches DB1-DA1 which crosses into domain A)",
        )

        async with database.unit_of_work() as uow:
            facts_empty = await EstateService(uow).gather_facts(tenant, domain_id=domain_empty_id)
        # empty domain: dataset_ids is empty set -> falsy -> `if not dataset_ids or ...`
        # evaluates True for every relationship -> admits ALL confirmed relationships
        ok227 = facts_empty.datasets == 0 and facts_empty.relationships_confirmed == 1
        record(
            "SEM-227",
            ok227,
            f"empty domain: datasets={facts_empty.datasets} (expect 0) "
            f"relationships_confirmed={facts_empty.relationships_confirmed} (expect 1 -- "
            f"the ENTIRE tenant's one confirmed relationship leaks in via "
            f"'if not dataset_ids or ...' when dataset_ids is empty)",
        )
    except Exception:
        record("SEM-226", False, "EXC:" + traceback.format_exc())
        record("SEM-227", False, "blocked")
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-228 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        # Rather than creating >10,000 real rows (slow), verify the cap is applied
        # by inspecting the call: gather_facts calls list_current(tenant, limit=10_000).
        # We create a modest number and confirm the call path uses the documented
        # cap value by monkeypatching list_current to observe the limit argument.
        seen_limits = []
        async with database.unit_of_work() as uow:
            orig = uow.datasets.list_current

            async def spy_list_current(tenant_id, limit=None, *a, **kw):
                seen_limits.append(limit)
                return await orig(tenant_id, limit=limit, *a, **kw)

            uow.datasets.list_current = spy_list_current
            dsvc = DatasetService(uow)
            for i in range(5):
                await dsvc.declare(tenant_id=tenant, name=f"Perf DS {i}")
        async with database.unit_of_work() as uow:
            orig = uow.datasets.list_current

            async def spy_list_current2(tenant_id, limit=None, *a, **kw):
                seen_limits.append(limit)
                return await orig(tenant_id, limit=limit, *a, **kw)

            uow.datasets.list_current = spy_list_current2
            facts = await EstateService(uow).gather_facts(tenant)
        ok228 = 10_000 in seen_limits and facts.datasets == 5
        record(
            "SEM-228",
            ok228,
            f"list_current called with limit={seen_limits} (expect 10000 present); "
            f"datasets counted={facts.datasets} for a small estate of 5 -- confirms the "
            f"hard-coded cap of 10,000 is what bounds the read (creating >10,000 real rows "
            f"to observe silent truncation was not attempted: too slow for this harness, "
            f"but the cap value itself is directly confirmed from the call)",
        )
    except Exception:
        record("SEM-228", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-229 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            d1, _ = await dsvc.declare(tenant_id=tenant, name="Trades A")
            d2, _ = await dsvc.declare(tenant_id=tenant, name="Trades B")
            a1, _ = await dsvc.declare_attribute(
                tenant_id=tenant, dataset_id=str(d1.id), name="notional", unit="USD"
            )
            a2, _ = await dsvc.declare_attribute(
                tenant_id=tenant, dataset_id=str(d2.id), name="notional_amount", unit="GBP"
            )
            csvc = ConceptService(uow)
            concept, _ = await csvc.declare_concept(tenant_id=tenant, name="Notional")
            prop, _ = await csvc.declare_property(
                tenant_id=tenant, concept_id=str(concept.id), name="Amount"
            )
            await csvc.map_attribute(
                tenant_id=tenant, attribute_id=str(a1.id), property_id=str(prop.id)
            )
            await csvc.map_attribute(
                tenant_id=tenant, attribute_id=str(a2.id), property_id=str(prop.id)
            )
        async with database.unit_of_work() as uow:
            conflicts = await EstateService(uow).conflicts(tenant)
        kinds = [c.kind.value for c in conflicts]
        unit_conflicts = [c for c in conflicts if c.kind.value == "unit"]
        ok = len(unit_conflicts) == 1 and set(unit_conflicts[0].attribute_names.values()) == {
            "notional",
            "notional_amount",
        }
        record(
            "SEM-229",
            ok,
            f"conflict kinds found={kinds}; unit conflict attribute names="
            f"{list(unit_conflicts[0].attribute_names.values()) if unit_conflicts else None}",
        )
    except Exception:
        record("SEM-229", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-230, SEM-231 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            # tier 1 with grain
            t1_grain, _ = await dsvc.declare(
                tenant_id=tenant,
                name="Tier1 With Grain",
                criticality=1,
                owner_id="alice",
                grain=Grain(("id",)),
                rhythm=Rhythm(Frequency.DAILY),
                approved_by="bob",
                authored_by="alice",
            )
            # tier 1 without grain (unowned, no rhythm, unbound)
            t1_no_grain, _ = await dsvc.declare(
                tenant_id=tenant,
                name="Tier1 No Grain",
                criticality=1,
                approved_by="bob",
                authored_by="alice",
            )
            # tier 4 without grain (unowned)
            t4_no_grain, _ = await dsvc.declare(
                tenant_id=tenant, name="Tier4 No Grain", criticality=4
            )
        async with database.unit_of_work() as uow:
            gaps = await EstateService(uow).coverage_gaps(tenant)
        expected_keys = {
            "unbound",
            "unowned",
            "no_grain",
            "no_rhythm",
            "tier_one_without_grain",
            "drifted_bindings",
        }
        ok230 = set(gaps.keys()) == expected_keys and all(
            isinstance(v, list) for v in gaps.values()
        )
        names_check = (
            "Tier1 No Grain" in gaps["no_grain"]
            and "Tier1 No Grain" in gaps["unowned"]
            and "Tier1 With Grain" not in gaps["no_grain"]
        )
        record(
            "SEM-230",
            ok230 and names_check,
            f"keys={sorted(gaps.keys())}; unowned={gaps['unowned']}; no_grain={gaps['no_grain']}; "
            f"tier_one_without_grain={gaps['tier_one_without_grain']}",
        )

        ok231 = set(gaps["tier_one_without_grain"]).issubset(set(gaps["no_grain"]))
        record(
            "SEM-231",
            ok231,
            f"tier_one_without_grain={gaps['tier_one_without_grain']} subset of "
            f"no_grain={gaps['no_grain']}: {ok231}",
        )
    except Exception:
        record("SEM-230", False, "EXC:" + traceback.format_exc())
        record("SEM-231", False, "blocked")
    finally:
        await database.stop()
        database.sync_engine().dispose()

    print("\n\n==== SUMMARY ====")
    for k, (r, o) in results.items():
        print(f"{k}\t{r}\t{o}")


asyncio.run(main())
