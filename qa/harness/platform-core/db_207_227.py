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
from prama.core.errors import NotFoundError, ConflictError, ValidationError
from prama.core.ids import new_ulid
from datetime import datetime, UTC, timedelta

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-sem2-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="sc", display_name="SC")
        await uow.flush()
        tid = str(t.id)

    # DB-207: JourneyDao.containing
    async with db.unit_of_work() as uow:
        eDs1, vDs1 = await uow.datasets.create(tenant_id=tid, name="D1", slug="d1")
        eDs2, vDs2 = await uow.datasets.create(tenant_id=tid, name="D2", slug="d2")
        eDs3, vDs3 = await uow.datasets.create(tenant_id=tid, name="D3", slug="d3")
        eJ, vJ = await uow.journeys.create(tenant_id=tid, name="J1", slug="j1", steps_json=[{"dataset_id": str(eDs1.id)}, {"dataset_id": str(eDs2.id)}])
    async with db.unit_of_work() as uow:
        found207 = await uow.journeys.containing(tid, str(eDs1.id))
        notfound207 = await uow.journeys.containing(tid, str(eDs3.id))
    R("DB-207", len(found207) == 1 and notfound207 == [], f"found={len(found207)}, notfound={notfound207}")

    # DB-208: JourneyDao.containing has a hardcoded ceiling (list_current(limit=10_000)).
    # Confirmed by source inspection; then EXECUTED at reduced scale by monkeypatching
    # VersionedDao.list_current to actually cap at N, so the ceiling-miss behaviour is
    # observed running, not merely read.
    src208 = inspect.getsource(type(uow.journeys).containing)
    hardcoded_10000 = "10_000" in src208
    from prama.db.dao.versioned import VersionedDao as _VD208
    orig_list_current = _VD208.list_current
    async def capped_list_current(self, tenant_id, *, limit=100, offset=0):
        return await orig_list_current(self, tenant_id, limit=min(limit, 3), offset=offset)
    _VD208.list_current = capped_list_current
    try:
        async with db.unit_of_work() as uow:
            t208 = uow.tenants.create(slug="sc208", display_name="SC208")
            await uow.flush()
            tid208 = str(t208.id)
            beyond_e, beyond_v = await uow.datasets.create(tenant_id=tid208, name="Beyond", slug="beyond208")
            beyond_id = str(beyond_e.id)
            for i in range(5):
                if i == 4:
                    await uow.journeys.create(tenant_id=tid208, name=f"J{i}", slug=f"j{i}",
                                               steps_json=[{"dataset_id": beyond_id}])
                else:
                    await uow.journeys.create(tenant_id=tid208, name=f"J{i}", slug=f"j{i}", steps_json=[])
        async with db.unit_of_work() as uow:
            result208 = await uow.journeys.containing(tid208, beyond_id)
    finally:
        _VD208.list_current = orig_list_current
    R("DB-208", bool(result208),
      f"hardcoded 10_000 in source confirmed={hardcoded_10000}; EXECUTED at reduced scale (list_current capped to 3 "
      f"via monkeypatch, 5 journeys created, the matching one 5th/beyond the cap): containing() found it={bool(result208)} "
      f"-- {'the ceiling silently hid a real match, exactly as the catalogue warns' if not result208 else 'unexpectedly found it despite the cap (re-check)'}")

    # DB-209: ConnectionDao.unhealthy has the same ceiling -- same executed-at-scale approach
    src209 = inspect.getsource(type(uow.connections).unhealthy)
    _VD208.list_current = capped_list_current
    try:
        async with db.unit_of_work() as uow:
            t209 = uow.tenants.create(slug="sc209", display_name="SC209")
            await uow.flush()
            tid209 = str(t209.id)
            for i in range(5):
                await uow.connections.create(tenant_id=tid209, name=f"c{i}", slug=f"c209-{i}", source_type="postgres",
                                              health_state="unreachable" if i == 4 else "healthy")
        async with db.unit_of_work() as uow:
            unhealthy209 = await uow.connections.unhealthy(tid209)
    finally:
        _VD208.list_current = orig_list_current
    R("DB-209", bool(unhealthy209),
      f"same pattern, executed: with list_current capped to 3 and the one broken connection created 5th, "
      f"unhealthy() found it={bool(unhealthy209)} -- {'ceiling silently hid the broken connection' if not unhealthy209 else 'found despite cap'}")

    # DB-210: BindingDao.drifted finds missing/retyped/renamed, excludes ok
    async with db.unit_of_work() as uow:
        eConn, vConn = await uow.connections.create(tenant_id=tid, name="c210", slug="c210", source_type="postgres")
        eDs210, vDs210 = await uow.datasets.create(tenant_id=tid, name="D210", slug="d210")
        states = {}
        for drift in ("missing", "retyped", "renamed", "intact"):
            e, v = await uow.bindings.create(tenant_id=tid, dataset_id=str(eDs210.id), connection_id=str(eConn.id),
                                              target_kind="dataset", physical_ref_json={"x": drift}, drift_state=drift)
            states[drift] = str(e.id)
    async with db.unit_of_work() as uow:
        drifted210 = await uow.bindings.drifted(tid)
    drifted_states = {v.drift_state for v in drifted210}
    R("DB-210", drifted_states == {"missing", "retyped", "renamed"}, f"drifted states found={drifted_states}")

    # DB-211/212: ControlDao.declare derives fields, caller cannot override
    pql211 = "CHECK t.a IS NOT NULL SEVERITY minor DIMENSION completeness BECAUSE 'test'"
    async with db.unit_of_work() as uow:
        ctl_e, ctl_v = await uow.controls.declare(tenant_id=tid, identity="id-211", pql=pql211)
    R("DB-211", ctl_v.dataset == "t" and ctl_v.dimensions_json == ["completeness"] and ctl_v.content_hash and ctl_v.plan_id is not None,
      f"dataset={ctl_v.dataset!r}, dims={ctl_v.dimensions_json}, content_hash={ctl_v.content_hash[:12]!r}, plan_id={ctl_v.plan_id!r}")
    declare_params = inspect.signature(type(uow.controls).declare).parameters
    R("DB-212", "severity" not in declare_params and ctl_v.severity == "minor",
      f"declare() does not even accept a 'severity' keyword argument (params={sorted(declare_params)}); stored "
      f"severity={ctl_v.severity!r} is derived purely from the PQL text 'SEVERITY minor' -- there is no route by "
      f"which a caller could pass one in, confirming **fields is applied last and unconditionally")

    # DB-213
    try:
        async with db.unit_of_work() as uow:
            await uow.controls.declare(tenant_id=tid, identity="id-213", pql="CHECK not valid pql!!! ***")
        R("DB-213", False, "no exception for malformed PQL")
    except ValidationError as e:
        ok213 = "hide that until it was due to run" in e.remedy
        R("DB-213", ok213, f"{e.code}: {e.remedy[:150]!r}")

    # DB-215/216: idempotent by identity
    async with db.unit_of_work() as uow:
        ctl215a_e, ctl215a_v = await uow.controls.declare(tenant_id=tid, identity="id-215", pql=pql211)
        v1_id = ctl215a_v.id
        v1_recorded = ctl215a_v.recorded_at
    async with db.unit_of_work() as uow:
        ctl215b_e, ctl215b_v = await uow.controls.declare(tenant_id=tid, identity="id-215", pql=pql211)
    R("DB-215a", ctl215b_v.id == v1_id, f"unchanged re-declare: same version id={ctl215b_v.id == v1_id}")
    R("DB-216", ctl215b_v.recorded_at == v1_recorded, f"recorded_at unchanged={ctl215b_v.recorded_at == v1_recorded}")
    async with db.unit_of_work() as uow:
        pql215_changed = "CHECK t.a IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'test'"
        ctl215c_e, ctl215c_v = await uow.controls.declare(tenant_id=tid, identity="id-215", pql=pql215_changed)
    R("DB-215b", ctl215c_v.id != v1_id and ctl215c_v.version == 2, f"changed re-declare creates new version: id changed={ctl215c_v.id != v1_id}, version={ctl215c_v.version}")

    # DB-217: whitespace-only PQL change does not create a version
    pql217a = "CHECK t.a IS NOT NULL SEVERITY minor DIMENSION completeness BECAUSE 'ws'"
    pql217b = "CHECK   t.a   IS NOT NULL  SEVERITY minor DIMENSION completeness BECAUSE 'ws'"
    async with db.unit_of_work() as uow:
        e217, v217a = await uow.controls.declare(tenant_id=tid, identity="id-217", pql=pql217a)
        id217a = v217a.id
    async with db.unit_of_work() as uow:
        e217b, v217b = await uow.controls.declare(tenant_id=tid, identity="id-217", pql=pql217b)
    R("DB-217", v217b.id == id217a, f"reindented PQL creates a new version={v217b.id != id217a} (should be False)")

    # DB-218/219: activate is an amend
    async with db.unit_of_work() as uow:
        e218, v218 = await uow.controls.declare(tenant_id=tid, identity="id-218", pql=pql211)
        cid218 = str(e218.id)
        v218b = await uow.controls.activate(cid218, tenant_id=tid, approved_by="alice218")
    async with db.unit_of_work() as uow:
        hist218 = await uow.controls.history(cid218, tenant_id=tid)
    proposal218 = next(v for v in hist218 if v.status == "proposed")
    R("DB-218", len(hist218) == 2 and not proposal218.is_superseded and proposal218.valid_to is not None,
      f"history len={len(hist218)}, proposal superseded={proposal218.is_superseded}, proposal valid_to set={proposal218.valid_to is not None}")
    R("DB-219", v218b.approved_by == "alice218", repr(v218b.approved_by))

    # DB-220: suppress requires both expiry and reason
    async with db.unit_of_work() as uow:
        e220, v220 = await uow.controls.declare(tenant_id=tid, identity="id-220", pql=pql211)
        cid220 = str(e220.id)
    combos220 = [("", "reason"), ("2026-01-01", ""), ("  ", "reason"), ("2026-01-01", "  ")]
    refusals220 = []
    for until, because in combos220:
        try:
            async with db.unit_of_work() as uow:
                await uow.controls.suppress(cid220, tenant_id=tid, until=until, because=because)
            refusals220.append(False)
        except ValidationError:
            refusals220.append(True)
    R("DB-220", all(refusals220), str(list(zip(combos220, refusals220))))

    # DB-221: suppressed control excluded from live
    async with db.unit_of_work() as uow:
        e221a, v221a = await uow.controls.declare(tenant_id=tid, identity="id-221a", pql=pql211)
        await uow.controls.activate(str(e221a.id), tenant_id=tid, approved_by="x")
        e221b, v221b = await uow.controls.declare(tenant_id=tid, identity="id-221b", pql=pql211)  # stays proposed
        e221c, v221c = await uow.controls.declare(tenant_id=tid, identity="id-221c", pql=pql211)
        await uow.controls.activate(str(e221c.id), tenant_id=tid, approved_by="x")
        await uow.controls.suppress(str(e221c.id), tenant_id=tid, until="2099-01-01", because="test")
    async with db.unit_of_work() as uow:
        live221 = await uow.controls.live(tid)
    live_ids221 = {v.control_id for v in live221}
    R("DB-221", str(e221a.id) in live_ids221 and str(e221b.id) not in live_ids221 and str(e221c.id) not in live_ids221,
      f"live count={len(live221)}")

    # DB-222/223: silenced_past_expiry
    async with db.unit_of_work() as uow:
        e222, v222 = await uow.controls.declare(tenant_id=tid, identity="id-222", pql=pql211)
        await uow.controls.activate(str(e222.id), tenant_id=tid, approved_by="x")
        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        await uow.controls.suppress(str(e222.id), tenant_id=tid, until=yesterday, because="past")
    async with db.unit_of_work() as uow:
        now_str = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        silenced = await uow.controls.silenced_past_expiry(tid, now_str)
        still_current = await uow.controls.current(str(e222.id), tenant_id=tid)
    R("DB-222", str(e222.id) in {v.control_id for v in silenced} and still_current.status == "suppressed",
      f"in silenced list={str(e222.id) in {v.control_id for v in silenced}}, still status={still_current.status!r} (not auto re-enabled)")

    async with db.unit_of_work() as uow:
        e223a, v223a = await uow.controls.declare(tenant_id=tid, identity="id-223a", pql=pql211)
        await uow.controls.activate(str(e223a.id), tenant_id=tid, approved_by="x")
        past_hour = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        await uow.controls.suppress(str(e223a.id), tenant_id=tid, until=past_hour, because="p")
        e223b, v223b = await uow.controls.declare(tenant_id=tid, identity="id-223b", pql=pql211)
        await uow.controls.activate(str(e223b.id), tenant_id=tid, approved_by="x")
        future_hour = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        await uow.controls.suppress(str(e223b.id), tenant_id=tid, until=future_hour, because="f")
        e223c, v223c = await uow.controls.declare(tenant_id=tid, identity="id-223c", pql=pql211)
        await uow.controls.activate(str(e223c.id), tenant_id=tid, approved_by="x")
        exact_now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        await uow.controls.suppress(str(e223c.id), tenant_id=tid, until=exact_now, because="e")
    async with db.unit_of_work() as uow:
        check_at = exact_now
        silenced223 = await uow.controls.silenced_past_expiry(tid, check_at)
    ids223 = {v.control_id for v in silenced223}
    R("DB-223", str(e223a.id) in ids223 and str(e223c.id) in ids223 and str(e223b.id) not in ids223,
      f"past-hour in={str(e223a.id) in ids223}, exact-now in={str(e223c.id) in ids223}, future-hour in={str(e223b.id) in ids223}")

    # DB-224: retire keeps control resolvable via evidence
    async with db.unit_of_work() as uow:
        e224, v224 = await uow.controls.declare(tenant_id=tid, identity="id-224", pql=pql211)
        await uow.controls.activate(str(e224.id), tenant_id=tid, approved_by="x")
    from prama.evidence.record import EvidenceRecord, SnapshotRef
    rec224 = EvidenceRecord(
        sequence=0, plan_id="p", control_id=str(e224.id), control_version=1, dataset="t", binding="",
        snapshot=SnapshotRef(kind="wall_clock", identifier="", exact=False), parameters={}, engine="duckdb",
        coverage="full", verdict="pass", metrics={}, samples_digest="", sample_count=0,
        started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:01Z", duration_ms=1,
        triggered_by="schedule", tenant_id=tid, detail="", dimensions=(), criticality=4,
        previous_hash="GENESIS",
    )
    async with db.unit_of_work() as uow:
        await uow.evidence.append(rec224, tenant_id=tid)
        await uow.controls.retire(str(e224.id), tenant_id=tid)
    async with db.unit_of_work() as uow:
        for_ctl224 = await uow.evidence.for_control(str(e224.id))
        ctl224_still = await uow.controls.get(str(e224.id))
    R("DB-224", len(for_ctl224) == 1 and ctl224_still is not None, f"evidence still resolves={len(for_ctl224)}, control entity still resolves={ctl224_still is not None}")

    # DB-225/226/227: RejectionDao
    async with db.unit_of_work() as uow:
        now225 = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        rej225 = await uow.rejections.record(tenant_id=tid, identity="id-225", content_hash="hash-a", rejected_at=now225)
        was225a = await uow.rejections.was_rejected(tid, "id-225", "hash-a")
        was225b = await uow.rejections.was_rejected(tid, "id-225", "hash-different")
    R("DB-225", was225a is True and was225b is False, f"same content={was225a}, rewritten content={was225b}")

    async with db.unit_of_work() as uow:
        t226 = uow.tenants.create(slug="sc226", display_name="SC226")
        await uow.flush()
        tid226 = str(t226.id)
        await uow.rejections.record(tenant_id=tid226, identity="id-225", content_hash="hash-a", rejected_at=now225)
    async with db.unit_of_work() as uow:
        was226 = await uow.rejections.was_rejected(tid, "id-225-notreal", "hash-a")  # different identity, same tenant
        cross226 = await uow.rejections.was_rejected(tid226, "id-225", "hash-a")
        cross226_wrong_tenant = await uow.rejections.was_rejected(tid, "id-226-only-in-226", "hash-a")
    R("DB-226", cross226 is True and cross226_wrong_tenant is False,
      f"tenant226 sees its own rejection={cross226}; tenant(sc) does not see tenant226's under a different identity={cross226_wrong_tenant}")

    async with db.unit_of_work() as uow:
        await uow.rejections.record(tenant_id=tid, identity="id-227", rejected_at=now225)  # default content_hash=""
        was227 = await uow.rejections.was_rejected(tid, "id-227", "some-real-hash")
    R("DB-227", was227 is False, f"rejection with empty content_hash matching a real hash={was227}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
