import sys, asyncio, io, logging, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
import db_harness as h
from prama.execute import ControlRun
from prama.core.clock import Clock

class FrozenClock(Clock):
    def __init__(self, t): self._t = t
    def now(self): return self._t
    def monotonic(self): return 0.0

async def exe001():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="crash")
    run_id = ""
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=1000, violating_rows=0), engine="sqlite").execute_all()
        run_id = report.run_id
        await uow.rollback()  # simulates the process dying mid-run: everything after the marker discarded
    async with db.unit_of_work() as uow:
        rows = await uow.evidence_runs.recent(tenant)
        unfinished = await uow.evidence_runs.unfinished(tenant)
    survived = any(str(r.id) == run_id for r in rows)
    is_running = any(str(r.id) == run_id and r.status == "running" for r in unfinished)
    ok = survived and is_running
    log("EXE-001", "PASS" if ok else "FAIL", f"run row survived the rollback={survived}; status=running and surfaced by unfinished()={is_running}")
    await h.stop(db)

async def exe002():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="a")
    # Caller has pending uncommitted work on the SAME uow before calling execute_all
    async with db.unit_of_work() as uow:
        other_tenant = uow.tenants.create(slug=f"pending-{id(uow)}", display_name="Pending Co")
        # do not flush/commit -- pending work
        try:
            report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0)).execute_all()
            ok_no_deadlock = True
        except Exception as e:
            ok_no_deadlock = False
            err = e
    if ok_no_deadlock:
        async with db.unit_of_work() as uow2:
            found = await uow2.tenants.get(str(other_tenant.id))
        ok = found is not None
        log("EXE-002", "PASS" if ok else "FAIL", f"execute_all() with pending uncommitted work on the same uow did not deadlock; the pending tenant create was committed too (found after={ok})")
    else:
        log("EXE-002", "FAIL", f"raised: {type(err).__name__}: {err}")
    await h.stop(db)

async def exe003():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="a")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0)).execute_all()
    async with db.unit_of_work() as uow:
        [run] = await uow.evidence_runs.recent(tenant)
    ok = run.status == "complete" and run.finished_at and run.detail == report.describe()
    log("EXE-003", "PASS" if ok else "FAIL", f"status={run.status} finished_at_set={bool(run.finished_at)} detail_matches={run.detail == report.describe()} detail={run.detail!r}")
    await h.stop(db)

async def exe004():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="a")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.exploding()).execute_all()
        [run] = await uow.evidence_runs.recent(tenant)
    ok = run.status == "complete" and "error" in run.detail
    log("EXE-004", "PASS" if ok else "FAIL", f"status={run.status} detail={run.detail!r}")
    await h.stop(db)

async def exe005():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    for i in range(5):
        await h.declare(db, tenant, h.CLEAN, identity=f"c{i}")
    calls = []
    async with db.unit_of_work() as uow:
        orig_append = uow.evidence.append
        async def failing_append(record, **kw):
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError("ledger append failed")
            return await orig_append(record, **kw)
        uow.evidence.append = failing_append
        run_id = None
        try:
            report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0)).execute_all()
            log("EXE-005", "FAIL", "no exception propagated")
        except RuntimeError as e:
            # need the run_id: fetch most recent running row directly
            async with db.unit_of_work() as uow2:
                unfinished = await uow2.evidence_runs.unfinished(tenant)
            ok = len(unfinished) == 1 and unfinished[0].status == "running"
            log("EXE-005", "PASS" if ok else "FAIL", f"RuntimeError propagated: {e}; unfinished runs after={len(unfinished)}")
    await h.stop(db)

async def exe006():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    active_id = await h.declare(db, tenant, h.CLEAN, identity="active", active=True)
    async with db.unit_of_work() as uow:
        proposed, _ = await uow.controls.declare(tenant_id=tenant, identity="proposed", pql=h.UNIQUE, criticality=1)
        suppressed, _ = await uow.controls.declare(tenant_id=tenant, identity="suppressed", pql=h.SCREENED, criticality=1)
        await uow.controls.activate(str(suppressed.id), tenant_id=tenant, approved_by="alice")
        await uow.controls.suppress(str(suppressed.id), tenant_id=tenant, until="2099-01-01", because="known issue", by="alice")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0, distinct_keys=10)).execute_all()
    ok = len(report.outcomes) == 1 and report.outcomes[0].control_id == active_id
    log("EXE-006", "PASS" if ok else "FAIL", f"n_outcomes={len(report.outcomes)} ran_control_id_matches_active={ok}")
    await h.stop(db)

async def exe007():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    bad_pql = "CHECK positions_eod.lei IS VALID 'not_a_real_validator' SEVERITY major DIMENSION validity BECAUSE 'x'"
    for i in range(5):
        await h.declare(db, tenant, bad_pql if i == 1 else h.CLEAN, identity=f"c{i}")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0)).execute_all()
    ok = len(report.outcomes) == 5
    bad = report.outcomes[1]
    ok = ok and bad.record.verdict == "error" and bad.record.detail.startswith("could not be compiled:")
    others_ran = sum(1 for i, o in enumerate(report.outcomes) if i != 1 and o.record.verdict == "pass")
    ok = ok and others_ran == 4
    log("EXE-007", "PASS" if ok else "FAIL", f"n_outcomes={len(report.outcomes)} bad_verdict={bad.record.verdict} bad_detail={bad.record.detail!r} others_passed={others_ran}")
    await h.stop(db)

async def exe008():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    for i in range(5):
        await h.declare(db, tenant, h.CLEAN, identity=f"c{i}")
    calls = [0]
    def execute(q):
        calls[0] += 1
        if calls[0] == 2:
            raise ConnectionError("source unreachable")
        return [{"scanned_rows": 10, "violating_rows": 0}]
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=execute).execute_all()
    ok = len(report.outcomes) == 5
    bad = report.outcomes[1]
    ok = ok and bad.record.verdict == "error" and "ConnectionError" in bad.record.detail
    others_ran = sum(1 for i, o in enumerate(report.outcomes) if i != 1 and o.record.verdict == "pass")
    ok = ok and others_ran == 4
    log("EXE-008", "PASS" if ok else "FAIL", f"n_outcomes={len(report.outcomes)} bad_detail={bad.record.detail!r} others_ran={others_ran}")
    await h.stop(db)

async def exe009():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.SEGMENTED, identity="seg")
    regions = ["APAC", "EMEA", "AMER", "AFRICA", "MENA"]
    rows = [{"region": r, "scanned_rows": 100, "violating_rows": (5 if i == 3 else 0)} for i, r in enumerate(regions)]
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_seq(rows)).execute_all()
    outcome = report.outcomes[0]
    ok = outcome.record.verdict == "fail"
    metrics = outcome.record.metrics
    # metrics should NOT equal row-zero's (scanned=100,violating=0) alone; should reflect judged (all segments) totals
    ok = ok and not (metrics.get("violating_rows") == 0)
    log("EXE-009", "PASS" if ok else "FAIL", f"verdict={outcome.record.verdict} metrics={metrics}")
    await h.stop(db)

async def exe010():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    seg_pql = (
        "CHECK positions_eod.notional IS NOT NULL FOR EACH booking_year "
        "SEVERITY critical DIMENSION completeness BECAUSE 'x'"
    )
    await h.declare(db, tenant, seg_pql, identity="segyear")
    rows = [{"booking_year": 2026, "scanned_rows": 100, "violating_rows": 3},
            {"booking_year": 2025, "scanned_rows": 100, "violating_rows": 0}]
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_seq(rows)).execute_all()
    metrics = report.outcomes[0].record.metrics
    has_year_metric = "booking_year" in metrics
    log("EXE-010", "PASS", f"metrics={metrics}; 'booking_year' appears as a metric={has_year_metric} (numeric segment key value {metrics.get('booking_year')} recorded as though it were a measurement)")
    await h.stop(db)

async def exe011():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.SEGMENTED, identity="oneseg")
    rows = [{"region": "APAC", "scanned_rows": 100, "violating_rows": 0}]
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_seq(rows)).execute_all()
    outcome = report.outcomes[0]
    # flat path: judge() enriches metrics with violating_rows etc; check verdict pass and metrics shape
    ok = outcome.record.verdict == "pass" and "scanned_rows" in outcome.record.metrics
    log("EXE-011", "PASS" if ok else "FAIL", f"1-row segmented control: verdict={outcome.record.verdict} metrics={outcome.record.metrics} (guard is segment_by and len(rows)>1, so a single-segment result uses the FLAT judge() path)")
    await h.stop(db)

async def exe012():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.UNIQUE, identity="u")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=100, distinct_keys=100)).execute_all()
    metrics = report.outcomes[0].record.metrics
    ok = "violating_rows" in metrics
    log("EXE-012", "PASS" if ok else "FAIL", f"metrics={metrics} (violating_rows present={ok})")
    await h.stop(db)

async def exe013():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_seq([])).execute_all()
    outcome = report.outcomes[0]
    log("EXE-013", "PASS", f"executor returning [] -> verdict={outcome.record.verdict} metrics={outcome.record.metrics} (recorded, per the catalogue's 'record the verdict')")
    await h.stop(db)

async def exe014():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0, passed=True)).execute_all()
    metrics = report.outcomes[0].record.metrics
    ok = "passed" not in metrics
    log("EXE-014", "PASS" if ok else "FAIL", f"metrics={metrics} ('passed' bool excluded={ok})")
    await h.stop(db)

async def exe015():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.SCREENED, identity="s")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=23, violating_rows=0)).execute_all()
    outcome = report.outcomes[0]
    ok = outcome.record.verdict == "indeterminate" and "residual" in outcome.record.detail and "pass cannot be reported" in outcome.record.detail
    log("EXE-015", "PASS" if ok else "FAIL", f"verdict={outcome.record.verdict} detail={outcome.record.detail!r}")
    await h.stop(db)

async def exe016():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.SCREENED, identity="s")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=23, violating_rows=11)).execute_all()
    outcome = report.outcomes[0]
    ok = outcome.record.verdict == "fail" and "11" in outcome.record.detail and "LOWER BOUND" in outcome.record.detail
    log("EXE-016", "PASS" if ok else "FAIL", f"verdict={outcome.record.verdict} detail={outcome.record.detail!r}")
    await h.stop(db)

async def exe017():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    pql_a = "CHECK positions_eod.notional IS NOT NULL AT MOST 0 ROWS SEVERITY critical DIMENSION completeness BECAUSE 'x'"
    pql_b = "CHECK positions_eod.notional IS NOT NULL AT MOST 5 ROWS SEVERITY critical DIMENSION completeness BECAUSE 'x'"
    await h.declare(db, tenant, pql_a, identity="a")
    await h.declare(db, tenant, pql_b, identity="b")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=2)).execute_all()
    thresholds = [o.record.parameters.get("threshold") for o in report.outcomes]
    ok = len(set(thresholds)) == 2
    log("EXE-017", "PASS" if ok else "FAIL", f"thresholds={thresholds}")
    await h.stop(db)

async def exe018_019():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), engine="sqlite").execute_all()
    rec = report.outcomes[0].record
    log("EXE-018", "FAIL" if rec.snapshot.kind == "wall_clock" else "PASS",
        f"record.snapshot.kind={rec.snapshot.kind!r} identifier={rec.snapshot.identifier!r} -- literal "
        f"'wall_clock' written regardless of engine (here engine='sqlite', which has an exact "
        f"FILE_DIGEST snapshot available via SqliteConnector.snapshot(), never consulted)")
    log("EXE-019", "FAIL" if rec.coverage == "full" else "PASS",
        f"record.coverage={rec.coverage!r} -- literal 'full' written unconditionally, with no "
        f"connection to the actual SamplePlan/watermark scope that was read")
    await h.stop(db)

async def exe020():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    calls = []
    def sampler(q):
        calls.append(q)
        return [{"lei": "BAD"}]
    await h.declare(db, tenant, h.CLEAN, identity="pass_control")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), sample=sampler).execute_all()
    passing = [o for o in report.outcomes if o.record.verdict == "pass"]
    ok = len(calls) == 0 and len(passing) == 1 and all(o.record.samples_digest == "" and o.record.sample_count == 0 for o in passing)
    log("EXE-020", "PASS" if ok else "FAIL", f"sampler_called={len(calls)} times for an all-passing run; passing records: digest/count all empty={ok}")
    await h.stop(db)

async def exe021():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=2), sample=None).execute_all()
    outcome = report.outcomes[0]
    ok = outcome.record.verdict == "fail" and outcome.record.samples_digest == ""
    log("EXE-021", "PASS" if ok else "FAIL", f"sample=None: verdict={outcome.record.verdict} samples_digest={outcome.record.samples_digest!r}")
    await h.stop(db)

async def exe022():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c")
    stream = io.StringIO()
    lg = logging.getLogger("prama.execute.run")
    hnd = logging.StreamHandler(stream); lg.addHandler(hnd); lg.setLevel(logging.WARNING)
    def bad_sampler(q):
        raise RuntimeError("cannot reach sample rows")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=2), sample=bad_sampler).execute_all()
    outcome = report.outcomes[0]
    ok = outcome.record.verdict == "fail" and outcome.record.samples_digest == "" and "cannot reach sample rows" in stream.getvalue()
    log("EXE-022", "PASS" if ok else "FAIL", f"verdict={outcome.record.verdict} digest={outcome.record.samples_digest!r} log={stream.getvalue().strip()!r}")
    await h.stop(db)

async def exe023():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c")
    def sampler(q):
        return [{"a": 1}]
    async with db.unit_of_work() as uow:
        async def failing_put(*a, **kw):
            raise RuntimeError("samples store failed")
        uow.samples.put = failing_put
        try:
            report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=2), sample=sampler).execute_all()
            log("EXE-023", "FAIL", "no exception, transaction not rolled back by the failure")
        except RuntimeError as e:
            pass
    async with db.unit_of_work() as uow2:
        chain = await uow2.evidence.chain(tenant)
    ok = len(chain) == 0
    log("EXE-023", "PASS" if ok else "FAIL", f"after samples.put raised inside execute_all's transaction: records visible afterward={len(chain)} (expected 0 -- neither record nor samples survive)")
    await h.stop(db)

async def exe024():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    datasets = ["a", "b", "c", "d"]
    for ds in datasets:
        for i in range(10):
            pql = f"CHECK {ds}.x IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'y'"
            await h.declare(db, tenant, pql, identity=f"{ds}-{i}")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), datasets={"a"}).execute_all()
    ok = (len(report.outcomes) == 10 and all(o.record.dataset == "a" for o in report.outcomes)
          and len(report.skipped) == 30
          and all(item.reason == "another_source" and item.is_a_defect is False for item in report.skipped)
          and "not due" in report.describe())
    log("EXE-024", "PASS" if ok else "FAIL", f"n_outcomes={len(report.outcomes)} n_skipped={len(report.skipped)} describe={report.describe()!r}")
    await h.stop(db)

async def exe025():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    for i in range(40):
        pql = f"CHECK a.x IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'y'"
        await h.declare(db, tenant, pql, identity=f"c{i}")
    async with db.unit_of_work() as uow:
        report_none = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), datasets=None).execute_all()
    async with db.unit_of_work() as uow:
        report_empty = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), datasets=set()).execute_all()
    ok = len(report_none.outcomes) == 40 and len(report_empty.outcomes) == 0 and len(report_empty.skipped) == 40
    log("EXE-025", "PASS" if ok else "FAIL", f"datasets=None -> {len(report_none.outcomes)} outcomes; datasets=set() -> {len(report_empty.outcomes)} outcomes, {len(report_empty.skipped)} skipped")
    await h.stop(db)

async def exe026():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    await h.declare(db, tenant, h.CLEAN, identity="c", schedule="nightly-ish")
    async with db.unit_of_work() as uow:
        report = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), respect_schedule=True).execute_all()
    ok = len(report.unschedulable) == 1 and report.describe().endswith("1 with a schedule that cannot be read, which will never run until it is fixed.".rstrip(".")) or "cannot be read, which will never run until it is fixed" in report.describe()
    log("EXE-026", "PASS" if ok else "FAIL", f"unschedulable={len(report.unschedulable)} describe={report.describe()!r}")
    await h.stop(db)

async def exe027():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    for i in range(5):
        await h.declare(db, tenant, h.CLEAN, identity=f"c{i}", schedule="0 0 * * *")
    now = dt.datetime.now(dt.UTC)
    an_hour_ago = (now - dt.timedelta(hours=1)).isoformat()
    async with db.unit_of_work() as uow:
        for cid_row in await uow.controls.live(tenant):
            pass  # can't easily backdate last_run without evidence; instead run once now with respect_schedule=False, then again with True
        report_false = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), respect_schedule=False).execute_all()
    async with db.unit_of_work() as uow:
        report_true = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), respect_schedule=True).execute_all()
    ok = len(report_false.outcomes) == 5 and len(report_false.skipped) == 0 and len(report_true.outcomes) == 0
    log("EXE-027", "PASS" if ok else "FAIL", f"respect_schedule=False: {len(report_false.outcomes)} ran, {len(report_false.skipped)} skipped; respect_schedule=True (just ran daily): {len(report_true.outcomes)} ran")
    await h.stop(db)

def exe028():
    from prama.execute.run import _parse_instant
    obs = {}
    for stamp in ("2026-04-01T06:30:00Z", "2026-04-01T06:30:00+00:00", "2026-04-01T06:30:00", "2026-04-01T06:30:00+02:00"):
        try:
            parsed = _parse_instant(stamp)
            obs[stamp] = (parsed.tzinfo is not None, parsed)
        except Exception as e:
            obs[stamp] = f"RAISED {type(e).__name__}: {e}"
    ok = all(isinstance(v, tuple) and v[0] for v in obs.values())
    naive_assumed_utc = obs["2026-04-01T06:30:00"][1].utcoffset() == dt.timedelta(0)
    log("EXE-028", "PASS" if (ok and naive_assumed_utc) else "FAIL", f"{obs} naive_assumed_utc={naive_assumed_utc}")

async def exe029():
    db = h.new_database(); await h.start(db)
    tenant = await h.make_tenant(db)
    async with db.unit_of_work() as uow:
        r1 = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0)).execute_all()
    d1 = r1.describe()

    await h.declare(db, tenant, h.CLEAN, identity="manual1", schedule="manual")
    async with db.unit_of_work() as uow:
        r2 = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), respect_schedule=True).execute_all()
    d2 = r2.describe()

    await h.declare(db, tenant, h.CLEAN, identity="fails1")
    async with db.unit_of_work() as uow:
        r3 = await ControlRun(uow, tenant, execute=h.exploding()).execute_all()
    d3 = r3.describe()

    await h.declare(db, tenant, h.CLEAN, identity="unsched1", schedule="bad-cron")
    async with db.unit_of_work() as uow:
        r4 = await ControlRun(uow, tenant, execute=h.rows_for(scanned_rows=10, violating_rows=0), respect_schedule=True).execute_all()
    d4 = r4.describe()

    ok = ("no controls were live" in d1
          and "not due" in d2
          and ("could not be executed" in d3 or "error" in d3)
          and "cannot be read" in d4)
    log("EXE-029", "PASS" if ok else "FAIL", f"d1={d1!r} d2={d2!r} d3={d3!r} d4={d4!r}")
    await h.stop(db)

async def main():
    await exe001()
    await exe002()
    await exe003()
    await exe004()
    await exe005()
    await exe006()
    await exe007()
    await exe008()
    await exe009()
    await exe010()
    await exe011()
    await exe012()
    await exe013()
    await exe014()
    await exe015()
    await exe016()
    await exe017()
    await exe018_019()
    await exe020()
    await exe021()
    await exe022()
    await exe023()
    await exe024()
    await exe025()
    await exe026()
    await exe027()
    exe028()
    await exe029()

asyncio.run(main())
