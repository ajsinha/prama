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
from prama.core.errors import NotFoundError, ConflictError
from prama.core.ids import new_ulid
from prama.evidence.record import EvidenceRecord, SnapshotRef, GENESIS
from datetime import datetime, UTC, timedelta

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

def mk_record(tenant_id, seq=0, verdict="pass", finished="2026-01-01T00:00:01Z", **kw):
    return EvidenceRecord(
        sequence=seq, plan_id=kw.get("plan_id", "p"), control_id=kw.get("control_id", ""),
        control_version=1, dataset=kw.get("dataset", "t"), binding="",
        snapshot=SnapshotRef(kind="wall_clock", identifier="", exact=False), parameters={},
        engine="duckdb", coverage="full", verdict=verdict, metrics={}, samples_digest="",
        sample_count=kw.get("sample_count", 0), started_at="2026-01-01T00:00:00Z", finished_at=finished, duration_ms=1,
        triggered_by="schedule", tenant_id=tenant_id, detail="", dimensions=(), criticality=4,
        previous_hash=kw.get("previous_hash", "garbage-not-genesis"),
    )

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-evid2-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="ev2", display_name="EV2")
        await uow.flush()
        tid = str(t.id)

    # DB-240: in_period inclusive at both ends, ordered by sequence
    async with db.unit_of_work() as uow:
        await uow.evidence.append(mk_record(tid, finished="2026-01-01T00:00:00Z"), tenant_id=tid)  # seq 0, at start
        await uow.evidence.append(mk_record(tid, finished="2026-01-05T00:00:00Z"), tenant_id=tid)   # seq 1, middle
        await uow.evidence.append(mk_record(tid, finished="2026-01-10T00:00:00Z"), tenant_id=tid)   # seq 2, at end
        await uow.evidence.append(mk_record(tid, finished="2026-01-11T00:00:00Z"), tenant_id=tid)   # seq 3, outside
    async with db.unit_of_work() as uow:
        inperiod = await uow.evidence.in_period(tid, "2026-01-01T00:00:00Z", "2026-01-10T00:00:00Z")
    R("DB-240", [r.sequence for r in inperiod] == [0, 1, 2], f"sequences={[r.sequence for r in inperiod]}")

    # DB-241: period_root stable
    async with db.unit_of_work() as uow:
        root1, count1 = await uow.evidence.period_root(tid, "2026-01-01T00:00:00Z", "2026-01-10T00:00:00Z")
        root2, count2 = await uow.evidence.period_root(tid, "2026-01-01T00:00:00Z", "2026-01-10T00:00:00Z")
    R("DB-241", root1 == root2 and count1 == count2 == 3, f"root1={root1[:12]}, root2={root2[:12]}, count={count1},{count2}")

    # DB-242: period_root over empty period
    async with db.unit_of_work() as uow:
        root_empty, count_empty = await uow.evidence.period_root(tid, "2099-01-01T00:00:00Z", "2099-01-02T00:00:00Z")
    R("DB-242", count_empty == 0 and isinstance(root_empty, str) and root_empty != "",
      f"count={count_empty}, root={root_empty!r}")

    # DB-243: failing includes error, skipped, indeterminate as well as fail
    async with db.unit_of_work() as uow:
        t243 = uow.tenants.create(slug="ev243", display_name="EV243")
        await uow.flush()
        tid243 = str(t243.id)
        for v in ("pass", "fail", "error", "skipped", "indeterminate"):
            await uow.evidence.append(mk_record(tid243, verdict=v), tenant_id=tid243)
    async with db.unit_of_work() as uow:
        failing243 = await uow.evidence.failing(tid243)
    R("DB-243", len(failing243) == 4 and {r.verdict for r in failing243} == {"fail","error","skipped","indeterminate"},
      f"count={len(failing243)}, verdicts={ {r.verdict for r in failing243} }")

    # DB-244: for_control not tenant-scoped
    async with db.unit_of_work() as uow:
        tA244 = uow.tenants.create(slug="ev244a", display_name="EV244A")
        tB244 = uow.tenants.create(slug="ev244b", display_name="EV244B")
        await uow.flush()
        tidA244, tidB244 = str(tA244.id), str(tB244.id)
        shared_ctl_id = new_ulid()
        await uow.evidence.append(mk_record(tidA244, control_id=shared_ctl_id, detail="tenantA-secret"), tenant_id=tidA244)
    import inspect
    from prama.db.dao.evidence import EvidenceDao
    takes_tenant_244 = "tenant_id" in inspect.signature(EvidenceDao.for_control).parameters
    unscoped_244_refused = False
    async with db.unit_of_work() as uow:
        try:
            await uow.evidence.for_control(shared_ctl_id)  # type: ignore[call-arg]
        except TypeError:
            unscoped_244_refused = True
        # tenant B asking (correctly, with its own tenant_id) for tenant A's control id sees nothing
        leak244 = await uow.evidence.for_control(shared_ctl_id, tenant_id=tidB244)
        ownA244 = await uow.evidence.for_control(shared_ctl_id, tenant_id=tidA244)
    R("DB-244", takes_tenant_244 and unscoped_244_refused and leak244 == [] and len(ownA244) == 1,
      f"for_control(control_id) now takes tenant_id={takes_tenant_244} (required kw-only); calling without it "
      f"raises TypeError={unscoped_244_refused}; tenant B scoped call for tenant A's control id returns "
      f"{len(leak244)} record(s) (must be 0); tenant A's own scoped call returns {len(ownA244)}")

    # DB-245: for_run -- now REQUIRES tenant_id (B1 remediation)
    async with db.unit_of_work() as uow:
        run245 = await uow.evidence_runs.start(tenant_id=tidA244, started_at="2026-01-01T00:00:00Z")
        await uow.evidence.append(mk_record(tidA244, detail="run-secret"), tenant_id=tidA244, run_id=str(run245.id))
    takes_tenant_245 = "tenant_id" in inspect.signature(EvidenceDao.for_run).parameters
    unscoped_245_refused = False
    async with db.unit_of_work() as uow:
        try:
            await uow.evidence.for_run(str(run245.id))  # type: ignore[call-arg]
        except TypeError:
            unscoped_245_refused = True
        leak245 = await uow.evidence.for_run(str(run245.id), tenant_id=tidB244)
        ownA245 = await uow.evidence.for_run(str(run245.id), tenant_id=tidA244)
    R("DB-245", takes_tenant_245 and unscoped_245_refused and leak245 == [] and len(ownA245) == 1,
      f"for_run(run_id) now takes tenant_id={takes_tenant_245} (required kw-only); calling without it raises "
      f"TypeError={unscoped_245_refused}; tenant B scoped call for tenant A's run id returns {len(leak245)} "
      f"record(s) (must be 0); tenant A's own scoped call returns {len(ownA245)}")

    # DB-246: latest_per_control counts each control once
    async with db.unit_of_work() as uow:
        t246 = uow.tenants.create(slug="ev246", display_name="EV246")
        await uow.flush()
        tid246 = str(t246.id)
        ctl_busy = new_ulid()
        ctl_rare = new_ulid()
        for i in range(60):
            await uow.evidence.append(mk_record(tid246, control_id=ctl_busy), tenant_id=tid246)
        await uow.evidence.append(mk_record(tid246, control_id=ctl_rare), tenant_id=tid246)
    async with db.unit_of_work() as uow:
        latest246 = await uow.evidence.latest_per_control(tid246)
    R("DB-246", len(latest246) == 2, f"distinct controls tracked={len(latest246)} (from 61 total records)")

    # DB-247: latest_per_control reads the whole chain (default limit 10000) -- execute at reduced scale
    from prama.db.dao.evidence import EvidenceDao as _EvD
    orig_chain = _EvD.chain
    async def capped_chain(self, tenant_id, *, limit=10000):
        return await orig_chain(self, tenant_id, limit=min(limit, 5))
    _EvD.chain = capped_chain
    try:
        async with db.unit_of_work() as uow:
            t247 = uow.tenants.create(slug="ev247", display_name="EV247")
            await uow.flush()
            tid247 = str(t247.id)
            for i in range(4):
                await uow.evidence.append(mk_record(tid247, control_id=f"old-{i}"), tenant_id=tid247)
            newest_ctl = new_ulid()
            await uow.evidence.append(mk_record(tid247, control_id=newest_ctl), tenant_id=tid247)  # 5th, beyond cap of 5? no this is the 5th=within cap
            await uow.evidence.append(mk_record(tid247, control_id="one-more-beyond-cap"), tenant_id=tid247)  # 6th, beyond cap
        async with db.unit_of_work() as uow:
            latest247 = await uow.evidence.latest_per_control(tid247)
    finally:
        _EvD.chain = orig_chain
    R("DB-247", "one-more-beyond-cap" not in latest247,
      f"with chain() capped at 5 (simulating the real default cap of 10,000), the 6th control's record is "
      f"{'missing' if 'one-more-beyond-cap' not in latest247 else 'present'} from latest_per_control() -- "
      f"{'confirming a scorecard silently stops seeing the newest controls past the cap' if 'one-more-beyond-cap' not in latest247 else 'unexpectedly present'}")

    # DB-248: last_run_at counts an errored run as a run
    async with db.unit_of_work() as uow:
        t248 = uow.tenants.create(slug="ev248", display_name="EV248")
        await uow.flush()
        tid248 = str(t248.id)
        ctl248 = new_ulid()
        for i in range(3):
            await uow.evidence.append(mk_record(tid248, control_id=ctl248, verdict="error", finished_at="2026-01-0%dT00:00:00Z" % (i+1)) if False else
                                       mk_record(tid248, control_id=ctl248, verdict="error", finished=f"2026-01-0{i+1}T00:00:00Z"), tenant_id=tid248)
    async with db.unit_of_work() as uow:
        last_run_at248 = await uow.evidence.last_run_at(tid248)
    R("DB-248", ctl248 in last_run_at248 and last_run_at248[ctl248] == "2026-01-03T00:00:00Z",
      f"last_run_at for an always-erroring control={last_run_at248.get(ctl248)!r}")

    # DB-249: EvidenceRunDao.finish counts records
    async with db.unit_of_work() as uow:
        t249 = uow.tenants.create(slug="ev249", display_name="EV249")
        await uow.flush()
        tid249 = str(t249.id)
        run249 = await uow.evidence_runs.start(tenant_id=tid249, started_at="2026-01-01T00:00:00Z")
        for i in range(3):
            await uow.evidence.append(mk_record(tid249), tenant_id=tid249, run_id=str(run249.id))
        finished249 = await uow.evidence_runs.finish(str(run249.id), finished_at="2026-01-01T01:00:00Z")
    R("DB-249", finished249.record_count == 3, repr(finished249.record_count))

    # DB-250: unfinished
    async with db.unit_of_work() as uow:
        t250 = uow.tenants.create(slug="ev250", display_name="EV250")
        await uow.flush()
        tid250 = str(t250.id)
        run250 = await uow.evidence_runs.start(tenant_id=tid250, started_at="2026-01-01T00:00:00Z")  # never finished
    async with db.unit_of_work() as uow:
        unfinished250 = await uow.evidence_runs.unfinished(tid250)
    R("DB-250", any(r.id == run250.id for r in unfinished250), f"unfinished count={len(unfinished250)}")

    # DB-251: SampleDao.put idempotent on digest
    async with db.unit_of_work() as uow:
        t251 = uow.tenants.create(slug="ev251", display_name="EV251")
        await uow.flush()
        tid251 = str(t251.id)
        s1 = await uow.samples.put(tenant_id=tid251, digest="digest251", rows=[{"a":1}], created_at="2026-01-01T00:00:00Z", expires_at="2026-02-01T00:00:00Z")
        s2 = await uow.samples.put(tenant_id=tid251, digest="digest251", rows=[{"a":1}], created_at="2026-01-01T00:00:00Z", expires_at="2099-01-01T00:00:00Z")
    R("DB-251", s2.expires_at == s1.expires_at, f"first expiry={s1.expires_at!r}, after second put expiry={s2.expires_at!r} (must be unchanged)")

    # DB-252: expired finds only past-expiry samples, never NULL expiry
    async with db.unit_of_work() as uow:
        t252 = uow.tenants.create(slug="ev252", display_name="EV252")
        await uow.flush()
        tid252 = str(t252.id)
        now252 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")
        past = (datetime(2026,6,14,12,0,0,tzinfo=UTC)).isoformat().replace("+00:00","Z")
        exact = now252
        future = (datetime(2026,6,16,12,0,0,tzinfo=UTC)).isoformat().replace("+00:00","Z")
        await uow.samples.put(tenant_id=tid252, digest="d-past-252", rows=[{"x":1}], created_at=now252, expires_at=past)
        await uow.samples.put(tenant_id=tid252, digest="d-exact-252", rows=[{"x":1}], created_at=now252, expires_at=exact)
        await uow.samples.put(tenant_id=tid252, digest="d-future-252", rows=[{"x":1}], created_at=now252, expires_at=future)
        await uow.samples.put(tenant_id=tid252, digest="d-null-252", rows=[{"x":1}], created_at=now252, expires_at=None)
    async with db.unit_of_work() as uow:
        expired252 = await uow.samples.expired(now252)
    digests252 = {s.digest for s in expired252} & {"d-past-252", "d-exact-252", "d-future-252", "d-null-252"}
    R("DB-252", digests252 == {"d-past-252", "d-exact-252"}, f"expired digests (this test's own)={digests252}")

    # DB-253: forget deletes sample but not record
    async with db.unit_of_work() as uow:
        rec253 = await uow.evidence.append(mk_record(tid251, sample_count=5), tenant_id=tid251)
        seq253 = rec253.sequence
        await uow.samples.put(tenant_id=tid251, digest="d-forget", rows=[{"y":1}], created_at=now252, expires_at=future)
    async with db.unit_of_work() as uow:
        forgot253 = await uow.samples.forget("d-forget")
        still_gone_sample = await uow.samples.get("d-forget")
        record_still_says = await uow.evidence.row_at(tid251, seq253)
    R("DB-253", forgot253 is True and still_gone_sample is None and record_still_says is not None and record_still_says.sample_count == 5,
      f"forgot={forgot253}, sample gone={still_gone_sample is None}, record survives with sample_count={record_still_says.sample_count if record_still_says else None}")

    # DB-254: forget of unknown digest
    async with db.unit_of_work() as uow:
        forgot254 = await uow.samples.forget("no-such-digest-at-all")
    R("DB-254", forgot254 is False, repr(forgot254))

    # DB-255: SampleDao not tenant-scoped on read
    import inspect as _insp255
    from prama.db.dao.evidence import SampleDao
    R("DB-255", "tenant_id" not in _insp255.signature(SampleDao.expired).parameters and "tenant_id" not in _insp255.signature(SampleDao.forget).parameters,
      f"expired() params={list(_insp255.signature(SampleDao.expired).parameters)}, forget() params={list(_insp255.signature(SampleDao.forget).parameters)} "
      f"-- confirmed neither takes a tenant, matching the documented deliberate design (content-addressed digest is "
      f"the identity; a retention sweep legitimately crosses tenants)")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
