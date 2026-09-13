import sys, os, asyncio, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.db import Database
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.errors import NotFoundError, ConflictError, ValidationError
from prama.core.ids import new_ulid
from datetime import datetime, UTC, timedelta

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-sem-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        tA = uow.tenants.create(slug="sa", display_name="SA")
        tB = uow.tenants.create(slug="sb", display_name="SB")
        await uow.flush()
        tidA, tidB = str(tA.id), str(tB.id)

    # DB-195: model triple consistency for the nine VersionedDao semantic subclasses
    from prama.db.dao import semantic as semmod
    import inspect as _insp
    triples = {}
    for name in ["DomainDao","DatasetDao","AttributeDao","ConceptDao","ConceptPropertyDao","RelationshipDao","JourneyDao","ConnectionDao","BindingDao"]:
        cls = getattr(semmod, name)
        vm = cls.version_model
        ek = cls.entity_key
        has_col = ek in vm.__table__.columns
        triples[name] = has_col
    R("DB-195", all(triples.values()), str(triples))

    # DB-196/197: by-slug/by-name tenant scoped, miss -> None
    async with db.unit_of_work() as uow:
        eA, vA = await uow.datasets.create(tenant_id=tidA, name="Shared", slug="shared-slug")
        eB, vB = await uow.datasets.create(tenant_id=tidB, name="SharedB", slug="shared-slug")
    async with db.unit_of_work() as uow:
        foundA = await uow.datasets.by_slug(tidA, "shared-slug")
        foundB = await uow.datasets.by_slug(tidB, "shared-slug")
        missA = await uow.datasets.by_slug(tidA, "no-such-slug")
    R("DB-196", foundA.name == "Shared" and foundB.name == "SharedB", f"A:{foundA.name}, B:{foundB.name}")
    R("DB-197", missA is None, repr(missA))

    # DB-198: AttributeDao.for_dataset cross-tenant refuses
    async with db.unit_of_work() as uow:
        eDs, vDs = await uow.datasets.create(tenant_id=tidA, name="DSforAttrs", slug="ds-attrs")
        dsid = str(eDs.id)
        eAttr, vAttr = await uow.attributes.create(tenant_id=tidA, identity_fields={"dataset_id": dsid}, name="attr1")
    async with db.unit_of_work() as uow:
        crossB = await uow.attributes.for_dataset(dsid, tenant_id=tidB)
        okA = await uow.attributes.for_dataset(dsid, tenant_id=tidA)
    R("DB-198", crossB == [] and len(okA) == 1, f"cross-tenant result={crossB}, own-tenant count={len(okA)}")

    # DB-199: ConceptPropertyDao.for_concept
    async with db.unit_of_work() as uow:
        eC, vC = await uow.concepts.create(tenant_id=tidA, name="ConceptX")
        cid = str(eC.id)
        eCP, vCP = await uow.concept_properties.create(tenant_id=tidA, identity_fields={"concept_id": cid}, name="propX")
    async with db.unit_of_work() as uow:
        crossB199 = await uow.concept_properties.for_concept(cid, tenant_id=tidB)
        okA199 = await uow.concept_properties.for_concept(cid, tenant_id=tidA)
    R("DB-199", crossB199 == [] and len(okA199) == 1, f"cross={crossB199}, own={len(okA199)}")

    # DB-200: BindingDao.for_dataset / for_attribute cross-tenant
    async with db.unit_of_work() as uow:
        eConn, vConn = await uow.connections.create(tenant_id=tidA, name="conn1", slug="conn1", source_type="postgres")
        connid = str(eConn.id)
        eBind, vBind = await uow.bindings.create(tenant_id=tidA, dataset_id=dsid, attribute_id=str(eAttr.id), connection_id=connid, target_kind="attribute", physical_ref_json={"table": "schema.table"})
    async with db.unit_of_work() as uow:
        crossB200a = await uow.bindings.for_dataset(dsid, tenant_id=tidB)
        crossB200b = await uow.bindings.for_attribute(str(eAttr.id), tenant_id=tidB)
        okA200 = await uow.bindings.for_dataset(dsid, tenant_id=tidA)
    R("DB-200", crossB200a == [] and crossB200b is None and len(okA200) == 1,
      f"for_dataset cross={crossB200a}, for_attribute cross={crossB200b}, own={len(okA200)}")

    # DB-201: AttributeDao.mapped_to_property -- now REQUIRES tenant_id (B1 remediation)
    async with db.unit_of_work() as uow:
        eDsB_temp, _ = await uow.datasets.create(tenant_id=tidB, name="DSB", slug="ds-b")
        eAttrB, vAttrB = await uow.attributes.create(tenant_id=tidB, identity_fields={"dataset_id": str(eDsB_temp.id)}, name="attrB")
        await uow.flush()
        vAttrB.concept_property_id = str(eCP.id)  # collide on same property id as tenant A's attribute
    import inspect as _insp201
    from prama.db.dao.semantic import AttributeDao as _AD201
    takes_tenant = "tenant_id" in _insp.signature(_AD201.mapped_to_property).parameters
    unscoped_call_refused = False
    async with db.unit_of_work() as uow:
        try:
            await uow.attributes.mapped_to_property(str(eCP.id))  # type: ignore[call-arg]
        except TypeError:
            unscoped_call_refused = True
        mappedA = await uow.attributes.mapped_to_property(str(eCP.id), tenant_id=tidA)
        mappedB = await uow.attributes.mapped_to_property(str(eCP.id), tenant_id=tidB)
    # tenant B's attribute is the one mapped to this property id; tenant A owns the property itself but has no
    # attribute mapped to it. Scoped correctly: A sees 0 (no leak of B's row into A's context), B sees its own 1.
    no_leak = len(mappedA) == 0 and len(mappedB) == 1
    R("DB-201", takes_tenant and unscoped_call_refused and no_leak,
      f"mapped_to_property(property_id) now takes tenant_id={takes_tenant} (required kw-only); calling it "
      f"without tenant_id raises TypeError={unscoped_call_refused}; scoped calls: tenant A (not the owner of the "
      f"matching attribute) sees {len(mappedA)} row(s), tenant B (the owner) sees {len(mappedB)} row(s) -- no "
      f"cross-tenant leak")

    # DB-202: DatasetDao.unbound
    async with db.unit_of_work() as uow:
        eU, vU = await uow.datasets.create(tenant_id=tidA, name="Unbound1", slug="unbound1", shape="unbound")
        eBnd, vBnd = await uow.datasets.create(tenant_id=tidA, name="Bound1", slug="bound1", shape="table")
    async with db.unit_of_work() as uow:
        unbound_list = await uow.datasets.unbound(tidA)
    R("DB-202", "Unbound1" in [v.name for v in unbound_list] and "Bound1" not in [v.name for v in unbound_list],
      f"unbound()={[v.name for v in unbound_list]}")

    # DB-203: by_criticality exact
    async with db.unit_of_work() as uow:
        for tier in (1,2,3,4):
            await uow.datasets.create(tenant_id=tidA, name=f"Tier{tier}", slug=f"tier{tier}", criticality=tier)
    async with db.unit_of_work() as uow:
        tier2 = await uow.datasets.by_criticality(tidA, 2)
        tier0 = await uow.datasets.by_criticality(tidA, 0)
    R("DB-203", [v.name for v in tier2] == ["Tier2"] and tier0 == [], f"tier2={[v.name for v in tier2]}, tier0={tier0}")

    # DB-204: critical_data_elements cross-tenant
    async with db.unit_of_work() as uow:
        eDsA2, vDsA2 = await uow.datasets.create(tenant_id=tidA, name="DSA2", slug="ds-a2")
        eAttrCDE_A, vAttrCDE_A = await uow.attributes.create(tenant_id=tidA, identity_fields={"dataset_id": str(eDsA2.id)}, name="cdeA", is_cde=True)
        eDsB2, vDsB2 = await uow.datasets.create(tenant_id=tidB, name="DSB2", slug="ds-b2")
        eAttrCDE_B, vAttrCDE_B = await uow.attributes.create(tenant_id=tidB, identity_fields={"dataset_id": str(eDsB2.id)}, name="cdeB", is_cde=True)
    async with db.unit_of_work() as uow:
        cdeA = await uow.attributes.critical_data_elements(tidA)
    R("DB-204", {v.name for v in cdeA} == {"cdeA"}, f"CDEs in tenant A={[v.name for v in cdeA]}")

    # DB-205: RelationshipDao.touching matches either side
    async with db.unit_of_work() as uow:
        eDsX, vDsX = await uow.datasets.create(tenant_id=tidA, name="DSX", slug="ds-x")
        eDsY, vDsY = await uow.datasets.create(tenant_id=tidA, name="DSY", slug="ds-y")
        eRel, vRel = await uow.relationships.create(tenant_id=tidA, from_dataset_id=str(eDsX.id), to_dataset_id=str(eDsY.id), kind="feeds", status="confirmed")
    async with db.unit_of_work() as uow:
        touchX = await uow.relationships.touching(tidA, str(eDsX.id))
        touchY = await uow.relationships.touching(tidA, str(eDsY.id))
    R("DB-205", len(touchX) == 1 and len(touchY) == 1, f"touching(X)={len(touchX)}, touching(Y)={len(touchY)}")

    # DB-206: confirmed excludes proposed
    async with db.unit_of_work() as uow:
        eDsZ, vDsZ = await uow.datasets.create(tenant_id=tidA, name="DSZ", slug="ds-z")
        eRelProp, vRelProp = await uow.relationships.create(tenant_id=tidA, from_dataset_id=str(eDsX.id), to_dataset_id=str(eDsZ.id), kind="feeds", status="proposed")
    async with db.unit_of_work() as uow:
        confirmed = await uow.relationships.confirmed(tidA)
    R("DB-206", len(confirmed) == 1, f"confirmed count={len(confirmed)}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
