import sys, os, asyncio, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from datetime import datetime, UTC, timedelta
from prama.db.temporal import Versioned, TemporalQuery
from prama.db.models.semantic import SemDomainVersion

# DB-190/193/194 need a real DB with several version rows
from prama.db import Database
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.core.ids import new_ulid

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-temporal-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="ttq", display_name="TTQ")
        await uow.flush()
        tid = str(t.id)
        entity, v1 = await uow.domains.create(tenant_id=tid, name="TQ1")
        eid = str(entity.id)
        v2 = await uow.domains.amend(eid, tenant_id=tid, name="TQ2")
        v3 = await uow.domains.correct(eid, tenant_id=tid, name="TQ3")

    # DB-190: TemporalQuery.current excludes both closed and superseded
    from sqlalchemy import select
    async with db.unit_of_work() as uow:
        stmt = TemporalQuery.current(select(SemDomainVersion).where(SemDomainVersion.domain_id == eid), SemDomainVersion)
        result = (await uow._session.execute(stmt)).scalars().all()
    R("DB-190", len(result) == 1 and result[0].name == "TQ3", f"current() returned {[(r.version, r.name) for r in result]}")

    # DB-191: Versioned.was_valid_at half-open [T1, T2)
    class Fake(Versioned):
        pass
    f = Fake()
    T1 = datetime(2026, 1, 1, tzinfo=UTC)
    T2 = datetime(2026, 2, 1, tzinfo=UTC)
    f.valid_from = T1
    f.valid_to = T2
    eps = timedelta(microseconds=1)
    checks191 = {
        "T1-eps": f.was_valid_at(T1 - eps),
        "T1": f.was_valid_at(T1),
        "T2-eps": f.was_valid_at(T2 - eps),
        "T2": f.was_valid_at(T2),
        "T2+eps": f.was_valid_at(T2 + eps),
    }
    expected191 = {"T1-eps": False, "T1": True, "T2-eps": True, "T2": False, "T2+eps": False}
    R("DB-191", checks191 == expected191, str(checks191))

    # DB-192: was_believed_at, same pattern with recorded_at/superseded_at
    f2 = Fake()
    f2.recorded_at = T1
    f2.superseded_at = T2
    checks192 = {
        "T1-eps": f2.was_believed_at(T1 - eps),
        "T1": f2.was_believed_at(T1),
        "T2-eps": f2.was_believed_at(T2 - eps),
        "T2": f2.was_believed_at(T2),
        "T2+eps": f2.was_believed_at(T2 + eps),
    }
    R("DB-192", checks192 == expected191, str(checks192))

    # DB-193: as_of never returns more than one row, swept over a grid
    async with db.unit_of_work() as uow:
        all_versions = await uow.domains.history(eid, tenant_id=tid)
    times = set()
    for v in all_versions:
        times.add(v.valid_from)
        if v.valid_to:
            times.add(v.valid_to)
        times.add(v.recorded_at)
        if v.superseded_at:
            times.add(v.superseded_at)
    times.add(datetime.now(UTC))
    grid = sorted(times)
    multi_hits = []
    async with db.unit_of_work() as uow:
        for valid_at in grid:
            for known_at in grid:
                stmt193 = TemporalQuery.as_of(
                    select(SemDomainVersion).where(SemDomainVersion.domain_id == eid),
                    SemDomainVersion, valid_at, known_at,
                )
                rows193 = (await uow._session.execute(stmt193)).scalars().all()
                if len(rows193) > 1:
                    multi_hits.append((valid_at, known_at, len(rows193)))
    R("DB-193", not multi_hits, f"grid points tested={len(grid)**2}; points with >1 row={multi_hits}")

    # DB-194: Versioned.is_current agrees with TemporalQuery.current SQL predicate
    async with db.unit_of_work() as uow:
        stmt194 = select(SemDomainVersion).where(SemDomainVersion.domain_id == eid)
        all_rows194 = (await uow._session.execute(stmt194)).scalars().all()
        current_stmt194 = TemporalQuery.current(select(SemDomainVersion).where(SemDomainVersion.domain_id == eid), SemDomainVersion)
        sql_current194 = set(r.id for r in (await uow._session.execute(current_stmt194)).scalars().all())
    python_current194 = set(r.id for r in all_rows194 if r.is_current)
    R("DB-194", python_current194 == sql_current194, f"python.is_current membership={python_current194}, SQL current()={sql_current194}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
