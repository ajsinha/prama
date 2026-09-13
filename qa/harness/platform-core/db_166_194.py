import sys, os, asyncio, tempfile, inspect
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
from prama.core.errors import NotFoundError, ConflictError
from prama.core.ids import new_ulid
from prama.db.temporal import Provenance
from datetime import datetime, UTC, timedelta

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-vdao-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="tv", display_name="TV")
        await uow.flush()
        tid = str(t.id)

    # DB-166
    async with db.unit_of_work() as uow:
        entity, v1 = await uow.domains.create(tenant_id=tid, name="Domain1")
        eid = str(entity.id)
    R("DB-166", v1.version == 1 and v1.valid_to is None and v1.superseded_at is None, f"version={v1.version}, valid_to={v1.valid_to}, superseded_at={v1.superseded_at}")

    # DB-167
    backdate = datetime(2020, 1, 1, tzinfo=UTC)
    async with db.unit_of_work() as uow:
        entity167, v167 = await uow.domains.create(tenant_id=tid, name="Backdated", valid_from=backdate)
        eid167 = str(entity167.id)
    async with db.unit_of_work() as uow:
        found_after = await uow.domains.valid_at(eid167, backdate + timedelta(seconds=1), tenant_id=tid)
        found_before = await uow.domains.valid_at(eid167, backdate - timedelta(seconds=1), tenant_id=tid)
    R("DB-167", found_after is not None and found_before is None, f"just after={found_after is not None}, just before={found_before is not None}")

    # DB-168
    async with db.unit_of_work() as uow:
        v2 = await uow.domains.amend(eid, tenant_id=tid, name="Domain1-amended")
    async with db.unit_of_work() as uow:
        hist168 = await uow.domains.history(eid, tenant_id=tid)
    old_v = next(v for v in hist168 if v.version == 1)
    new_v = next(v for v in hist168 if v.version == 2)
    R("DB-168", old_v.valid_to is not None and new_v.version == 2 and new_v.valid_from == old_v.valid_to
      and new_v.valid_to is None and not old_v.is_superseded and not new_v.is_superseded,
      f"old.valid_to={old_v.valid_to}, new.valid_from={new_v.valid_from}, new.valid_to={new_v.valid_to}, "
      f"old.superseded={old_v.is_superseded}, new.superseded={new_v.is_superseded}")

    # DB-169
    async with db.unit_of_work() as uow:
        before_correct = await uow.domains.current(eid, tenant_id=tid)
        vf_before, vt_before = before_correct.valid_from, before_correct.valid_to
        v3 = await uow.domains.correct(eid, tenant_id=tid, name="Domain1-corrected")
    async with db.unit_of_work() as uow:
        hist169 = await uow.domains.history(eid, tenant_id=tid)
    superseded_v2 = next(v for v in hist169 if v.version == 2)
    corrected_v3 = next(v for v in hist169 if v.version == 3)
    R("DB-169", superseded_v2.is_superseded and superseded_v2.valid_from == vf_before and superseded_v2.valid_to == vt_before
      and corrected_v3.valid_from == vf_before and corrected_v3.valid_to == vt_before,
      f"v2 superseded={superseded_v2.is_superseded}, v2 period unchanged={(superseded_v2.valid_from, superseded_v2.valid_to)==(vf_before, vt_before)}, "
      f"v3 inherits period={(corrected_v3.valid_from, corrected_v3.valid_to)==(vf_before, vt_before)}")

    # DB-170 / DB-171: create, then correct at T2, check as_of before and valid_at now
    async with db.unit_of_work() as uow:
        entity170, v170a = await uow.domains.create(tenant_id=tid, name="T170-orig")
        eid170 = str(entity170.id)
        t1 = v170a.recorded_at
    await asyncio.sleep(0.05)
    t_mid = datetime.now(UTC)
    await asyncio.sleep(0.05)
    async with db.unit_of_work() as uow:
        v170b = await uow.domains.correct(eid170, tenant_id=tid, name="T170-corrected")
        t2 = v170b.recorded_at
    async with db.unit_of_work() as uow:
        as_of_mid = await uow.domains.as_of(eid170, t_mid, t_mid, tenant_id=tid)
        valid_now = await uow.domains.valid_at(eid170, t_mid, tenant_id=tid)
    R("DB-170", as_of_mid is not None and as_of_mid.name == "T170-orig", f"as_of(T1.5, T1.5).name={as_of_mid.name if as_of_mid else None}")
    R("DB-171", valid_now is not None and valid_now.name == "T170-corrected", f"valid_at(T1.5) today .name={valid_now.name if valid_now else None}")

    # DB-172
    async with db.unit_of_work() as uow:
        entity172, v172 = await uow.domains.create(tenant_id=tid, name="T172", valid_from=datetime(2026,4,1,tzinfo=UTC))
        eid172 = str(entity172.id)
    try:
        async with db.unit_of_work() as uow:
            await uow.domains.amend(eid172, tenant_id=tid, effective_from=datetime(2026,3,1,tzinfo=UTC), name="T172-amend")
        R("DB-172", False, "no exception for effective_from before current valid_from")
    except ConflictError as e:
        ok172 = "correct" in e.remedy.lower()
        R("DB-172", ok172, f"{e.code}: {e.remedy!r}")

    # DB-173
    exact_t = datetime(2026,5,1,tzinfo=UTC)
    async with db.unit_of_work() as uow:
        entity173, v173 = await uow.domains.create(tenant_id=tid, name="T173", valid_from=exact_t)
        eid173 = str(entity173.id)
    async with db.unit_of_work() as uow:
        v173b = await uow.domains.amend(eid173, tenant_id=tid, effective_from=exact_t, name="T173-amend")
    async with db.unit_of_work() as uow:
        hist173 = await uow.domains.history(eid173, tenant_id=tid)
        at_exact = await uow.domains.valid_at(eid173, exact_t, tenant_id=tid)
    old173 = next(v for v in hist173 if v.version == 1)
    R("DB-173", old173.valid_from == old173.valid_to == exact_t and at_exact is not None and at_exact.version == 2,
      f"old.valid_from==valid_to=={old173.valid_from == old173.valid_to == exact_t}; valid_at(T) resolves to version={at_exact.version if at_exact else None}")

    # DB-174
    try:
        async with db.unit_of_work() as uow:
            await uow.domains.amend(new_ulid(), tenant_id=tid, name="x")
        R("DB-174", False, "no exception")
    except NotFoundError as e:
        ok174 = "no current version to amend" in str(e) and "Create the declaration" in e.remedy
        R("DB-174", ok174, f"{e}; remedy={e.remedy!r}")

    # DB-175
    async with db.unit_of_work() as uow:
        t2tenant = uow.tenants.create(slug="tv2", display_name="TV2")
        await uow.flush()
        tid2 = str(t2tenant.id)
    try:
        async with db.unit_of_work() as uow:
            await uow.domains.amend(eid, tenant_id=tid2, name="cross-tenant-amend")
        R("DB-175", False, "no exception amending another tenant's entity")
    except NotFoundError:
        R("DB-175", True, "refused as not found, cross-tenant amend blocked")

    # DB-176
    import prama.db.dao.versioned as vdmod
    methods = ["current", "require_current", "valid_at", "as_of", "history", "list_current", "count_current", "amend", "correct", "retire"]
    missing_tenant = [m for m in methods if "tenant_id" not in inspect.signature(getattr(vdmod.VersionedDao, m)).parameters]
    R("DB-176", not missing_tenant, f"methods missing tenant_id param: {missing_tenant}" if missing_tenant else "all 10 methods require tenant_id")

    # DB-177
    import subprocess
    hits177 = subprocess.run(["grep", "-rn", r"\.tenant_of(", "src/prama", "--include=*.py"], capture_output=True, text=True).stdout
    call_sites = [l for l in hits177.strip().splitlines() if "def tenant_of" not in l]
    api_route_hits = [l for l in call_sites if "/web/" in l or "/api/" in l]
    R("DB-177", not api_route_hits, f"call sites: {call_sites}; any inside web/ or api/ routes={bool(api_route_hits)}")

    # DB-178
    async with db.unit_of_work() as uow:
        entity178, v178 = await uow.domains.create(tenant_id=tid, name="T178")
        eid178 = str(entity178.id)
        await uow.domains.amend(eid178, tenant_id=tid, name="T178-amended")
    from sqlalchemy import text as satext
    with db.sync_engine().connect() as conn:
        cnt178 = conn.execute(satext(
            "SELECT COUNT(*) FROM sem_domain_version WHERE domain_id=:e AND valid_to IS NULL AND superseded_at IS NULL"
        ), {"e": eid178}).scalar()
    R("DB-178", cnt178 == 1, repr(cnt178))

    # DB-179: two GENUINELY concurrent amendments (via asyncio.gather, so both
    # coroutines' internal current() reads can interleave before either
    # commits) -- one should succeed, the other should get a ConflictError,
    # never both.
    async with db.unit_of_work() as uow:
        entity179, v179 = await uow.domains.create(tenant_id=tid, name="T179")
        eid179 = str(entity179.id)
    uowA = db.unit_of_work()
    uowB = db.unit_of_work()

    async def do_amend(uow, label):
        try:
            await uow.domains.amend(eid179, tenant_id=tid, name=f"T179-{label}")
            await uow.commit()
            return "ok"
        except ConflictError:
            return "ConflictError"
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        finally:
            await uow.close()

    resA, resB = await asyncio.gather(do_amend(uowA, "A"), do_amend(uowB, "B"), return_exceptions=False)
    # Verify from a THIRD session how many rows are truly "current" now --
    # this is the check that actually matters, independent of how the two
    # coroutines' Python-level results came back.
    from sqlalchemy import text as satext179
    with db.sync_engine().connect() as conn:
        current_rows179 = conn.execute(satext179(
            "SELECT COUNT(*) FROM sem_domain_version WHERE domain_id=:e AND valid_to IS NULL AND superseded_at IS NULL"
        ), {"e": eid179}).scalar()
    one_ok_one_conflicterror = sorted([resA.split(":")[0], resB.split(":")[0]]) == ["ConflictError", "ok"]
    R("DB-179", current_rows179 == 1 and one_ok_one_conflicterror,
      f"A={resA[:120]!r}, B={resB[:120]!r}; true current-row count={current_rows179} (data integrity is fine: "
      f"exactly one current row, no forked chain -- the partial unique index worked). But the LOSING side's error "
      f"is a raw, untranslated sqlite3.IntegrityError, not the documented ConflictError: VersionedDao.amend()/"
      f"correct() call `self._session.flush()` directly rather than going through UnitOfWork._guarded(), so the "
      f"error-taxonomy translation CLAUDE.md promises ('No exception is swallowed... translated into the Prama "
      f"error taxonomy') is bypassed at exactly the concurrency-conflict path this case exists to test")

    # DB-180
    try:
        async with db.unit_of_work() as uow:
            await uow.domains.amend(eid, tenant_id=tid, grian="typo-field")
        R("DB-180", False, "no exception for unknown field")
    except ConflictError as e:
        ok180 = "grian" in str(e) and "typo" in e.remedy.lower()
        R("DB-180", ok180, f"{e}; remedy={e.remedy!r}")

    # DB-181
    async with db.unit_of_work() as uow:
        entity181, v181 = await uow.domains.create(tenant_id=tid, name="T181")
        eid181 = str(entity181.id)
        await uow.domains.amend(eid181, tenant_id=tid, provenance=Provenance(authored_by="alice", approved_by="bob", approved_at=datetime.now(UTC), reason="r181"), name="T181-v2")
    async with db.unit_of_work() as uow:
        hist181 = await uow.domains.history(eid181, tenant_id=tid)
    v1_181, v2_181 = hist181[0], hist181[1]
    R("DB-181", v2_181.id != v1_181.id and v2_181.version != v1_181.version and v2_181.recorded_at != v1_181.recorded_at
      and v2_181.authored_by != v1_181.authored_by,
      f"successor has fresh id={v2_181.id != v1_181.id}, fresh version={v2_181.version != v1_181.version}, "
      f"fresh recorded_at={v2_181.recorded_at != v1_181.recorded_at}, own provenance (not inherited)={v2_181.authored_by != v1_181.authored_by}")

    # DB-182
    R("DB-182", v2_181.authored_by == "alice" and v2_181.approved_by == "bob" and v2_181.change_reason == "r181",
      f"authored_by={v2_181.authored_by!r}, approved_by={v2_181.approved_by!r}, change_reason={v2_181.change_reason!r}")

    # DB-183
    async with db.unit_of_work() as uow:
        entity183, v183 = await uow.domains.create(tenant_id=tid, name="T183", provenance=Provenance(approved_by="bob183"))
        eid183 = str(entity183.id)
        v183b = await uow.domains.amend(eid183, tenant_id=tid, name="T183-v2")  # no provenance passed
    R("DB-183", v183b.approved_by is None, f"successor.approved_by={v183b.approved_by!r} (original was approved by bob183)")

    # DB-184
    async with db.unit_of_work() as uow:
        entity184, v184 = await uow.domains.create(tenant_id=tid, name="T184")
        eid184 = str(entity184.id)
        retired184 = await uow.domains.retire(eid184, tenant_id=tid)
    async with db.unit_of_work() as uow:
        current184 = await uow.domains.current(eid184, tenant_id=tid)
        hist184 = await uow.domains.history(eid184, tenant_id=tid)
    R("DB-184", current184 is None and len(hist184) == 1 and hist184[0].valid_to is not None,
      f"current after retire={current184}; history len={len(hist184)}, valid_to set={hist184[0].valid_to is not None}")

    # DB-185
    async with db.unit_of_work() as uow:
        r185 = await uow.domains.retire(new_ulid(), tenant_id=tid)
    R("DB-185", r185 is None, repr(r185))

    # DB-186
    async with db.unit_of_work() as uow:
        entity186, v186 = await uow.domains.create(tenant_id=tid, name="T186")
        eid186 = str(entity186.id)
        await uow.domains.amend(eid186, tenant_id=tid, name="T186-v2")
        await uow.domains.correct(eid186, tenant_id=tid, name="T186-v3-corrected")
    async with db.unit_of_work() as uow:
        hist186 = await uow.domains.history(eid186, tenant_id=tid)
    R("DB-186", [v.version for v in hist186] == [1, 2, 3] and any(v.is_superseded for v in hist186),
      f"versions in order={[v.version for v in hist186]}, any superseded={any(v.is_superseded for v in hist186)}")

    # DB-187
    async with db.unit_of_work() as uow:
        hist187 = await uow.domains.history(new_ulid(), tenant_id=tid)
    R("DB-187", hist187 == [], repr(hist187))

    # DB-188 / DB-189
    async with db.unit_of_work() as uow:
        t188 = uow.tenants.create(slug="tv188", display_name="TV188")
        await uow.flush()
        tid188 = str(t188.id)
        ids188 = []
        for i in range(25):
            e, v = await uow.domains.create(tenant_id=tid188, name=f"d188-{i}")
            ids188.append(str(e.id))
        for i in range(3):
            await uow.domains.retire(ids188[i], tenant_id=tid188)
    async with db.unit_of_work() as uow:
        seen188 = []
        for offset in (0, 10, 20):
            page = await uow.domains.list_current(tid188, limit=10, offset=offset)
            seen188.extend([v.id for v in page])
        count188 = await uow.domains.count_current(tid188)
    R("DB-188", len(seen188) == 22 and len(set(seen188)) == 22, f"total across pages={len(seen188)}, unique={len(set(seen188))}")
    R("DB-189", count188 == len(set(seen188)) == 22, f"count_current={count188}, list_current total unique={len(set(seen188))}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
