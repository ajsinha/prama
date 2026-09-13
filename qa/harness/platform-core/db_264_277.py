import sys, os, asyncio, tempfile, dataclasses, enum
from decimal import Decimal
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
from prama.recon.classify import Break, BreakKind

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

def mk_break(key, kind=BreakKind.GENUINE, left=Decimal("1.00"), right=Decimal("2.00")):
    return Break(key=key, kind=kind, left=left, right=right, because="test")

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-recon-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="rc", display_name="RC")
        await uow.flush()
        tid = str(t.id)

    # DB-264: observe returns (new, seen_again, cleared)
    async with db.unit_of_work() as uow:
        breaks264 = [mk_break(f"k{i}") for i in range(40)]
        result264 = await uow.breaks.observe(breaks264, tenant_id=tid, definition="def264", when="2026-01-01T00:00:00Z")
    R("DB-264", result264 == (40, 0, 40) if False else result264 == (40, 0, 0), f"observe() first run -> {result264} (expected (40 new, 0 again, 0 cleared) on a fresh queue)")

    async with db.unit_of_work() as uow:
        breaks264b = [mk_break(f"k{i}b") for i in range(40)]  # forty DIFFERENT ones
        result264b = await uow.breaks.observe(breaks264b, tenant_id=tid, definition="def264", when="2026-01-02T00:00:00Z")
    R("DB-264b", result264b == (40, 0, 40), f"second run with 40 different keys -> {result264b} (expected 40 new, 0 again, 40 cleared -- 'forty cleared and forty appeared')")

    # DB-265: re-seen break keeps first_seen
    async with db.unit_of_work() as uow:
        t265 = uow.tenants.create(slug="rc265", display_name="RC265")
        await uow.flush()
        tid265 = str(t265.id)
        await uow.breaks.observe([mk_break("k265")], tenant_id=tid265, definition="def265", when="2025-08-05T00:00:00Z")  # 40 days before a later date
    async with db.unit_of_work() as uow:
        await uow.breaks.observe([mk_break("k265")], tenant_id=tid265, definition="def265", when="2025-09-14T00:00:00Z")
    async with db.unit_of_work() as uow:
        rows265 = await uow.breaks.for_definition(tid265, "def265")
    R("DB-265", rows265[0].first_seen == "2025-08-05T00:00:00Z" and rows265[0].last_seen == "2025-09-14T00:00:00Z",
      f"first_seen={rows265[0].first_seen!r}, last_seen={rows265[0].last_seen!r}")

    # DB-266: absent break is cleared
    async with db.unit_of_work() as uow:
        t266 = uow.tenants.create(slug="rc266", display_name="RC266")
        await uow.flush()
        tid266 = str(t266.id)
        await uow.breaks.observe([mk_break("k266")], tenant_id=tid266, definition="def266", when="2026-01-01T00:00:00Z")
    async with db.unit_of_work() as uow:
        await uow.breaks.observe([], tenant_id=tid266, definition="def266", when="2026-01-02T00:00:00Z")
    async with db.unit_of_work() as uow:
        rows266 = await uow.breaks.for_definition(tid266, "def266")
    R("DB-266", rows266[0].state == "cleared" and rows266[0].cleared_at == "2026-01-02T00:00:00Z", f"state={rows266[0].state!r}, cleared_at={rows266[0].cleared_at!r}")

    # DB-267: accepted break not cleared by absence
    async with db.unit_of_work() as uow:
        t267 = uow.tenants.create(slug="rc267", display_name="RC267")
        await uow.flush()
        tid267 = str(t267.id)
        await uow.breaks.observe([mk_break("k267")], tenant_id=tid267, definition="def267", when="2026-01-01T00:00:00Z")
    async with db.unit_of_work() as uow:
        rows267_pre = await uow.breaks.for_definition(tid267, "def267")
        bid267 = str(rows267_pre[0].id)
        await uow.breaks.accept(bid267, tid267, reason="known FX timing diff", by="qa", at="2026-01-01T12:00:00Z")
    async with db.unit_of_work() as uow:
        await uow.breaks.observe([], tenant_id=tid267, definition="def267", when="2026-01-02T00:00:00Z")
    async with db.unit_of_work() as uow:
        rows267 = await uow.breaks.for_definition(tid267, "def267")
    R("DB-267", rows267[0].state == "accepted", f"state after being absent from a run={rows267[0].state!r}")

    # DB-268: cleared break that returns is re-opened with original age
    async with db.unit_of_work() as uow:
        t268 = uow.tenants.create(slug="rc268", display_name="RC268")
        await uow.flush()
        tid268 = str(t268.id)
        await uow.breaks.observe([mk_break("k268")], tenant_id=tid268, definition="def268", when="2025-01-01T00:00:00Z")
        await uow.breaks.observe([], tenant_id=tid268, definition="def268", when="2025-06-01T00:00:00Z")  # cleared
    async with db.unit_of_work() as uow:
        await uow.breaks.observe([mk_break("k268")], tenant_id=tid268, definition="def268", when="2026-01-01T00:00:00Z")  # returns
    async with db.unit_of_work() as uow:
        rows268 = await uow.breaks.for_definition(tid268, "def268")
    R("DB-268", rows268[0].state == "open" and rows268[0].cleared_at is None and rows268[0].first_seen == "2025-01-01T00:00:00Z",
      f"state={rows268[0].state!r}, cleared_at={rows268[0].cleared_at!r}, first_seen={rows268[0].first_seen!r}")

    # DB-269: outstanding includes accepted
    async with db.unit_of_work() as uow:
        t269 = uow.tenants.create(slug="rc269", display_name="RC269")
        await uow.flush()
        tid269 = str(t269.id)
        await uow.breaks.observe([mk_break(f"k269-{i}") for i in range(5)], tenant_id=tid269, definition="def269", when="2026-01-01T00:00:00Z")
        rows269 = await uow.breaks.for_definition(tid269, "def269")
        ids269 = [str(r.id) for r in rows269]
    async with db.unit_of_work() as uow:
        await uow.breaks.assign(ids269[1], tid269, owner="bob", by="qa", at="t")
        await uow.breaks.explain(ids269[2], tid269, text="found the cause", by="qa", at="t")
        await uow.breaks.accept(ids269[3], tid269, reason="known", by="qa", at="t")
        await uow.breaks.observe([mk_break(f"k269-{i}") for i in (0,1,2,3)], tenant_id=tid269, definition="def269", when="2026-01-02T00:00:00Z")  # index 4 clears
    async with db.unit_of_work() as uow:
        outstanding269 = await uow.breaks.outstanding(tid269, "def269")
    R("DB-269", len(outstanding269) == 4, f"outstanding count={len(outstanding269)} (open, assigned, explained, accepted -- excludes the 1 cleared)")

    # DB-270: definitions includes all-cleared reconciliations
    async with db.unit_of_work() as uow:
        t270 = uow.tenants.create(slug="rc270", display_name="RC270")
        await uow.flush()
        tid270 = str(t270.id)
        await uow.breaks.observe([mk_break("k270")], tenant_id=tid270, definition="def270-allcleared", when="2026-01-01T00:00:00Z")
        await uow.breaks.observe([], tenant_id=tid270, definition="def270-allcleared", when="2026-01-02T00:00:00Z")
    async with db.unit_of_work() as uow:
        defs270 = await uow.breaks.definitions(tid270)
    R("DB-270", "def270-allcleared" in defs270, f"definitions()={defs270}")

    # DB-271: assign/explain/accept refuse empty input
    async with db.unit_of_work() as uow:
        t271 = uow.tenants.create(slug="rc271", display_name="RC271")
        await uow.flush()
        tid271 = str(t271.id)
        await uow.breaks.observe([mk_break("k271")], tenant_id=tid271, definition="def271", when="2026-01-01T00:00:00Z")
        rows271 = await uow.breaks.for_definition(tid271, "def271")
        bid271 = str(rows271[0].id)
    refusals271 = []
    for fn, kw in [
        (uow_lambda := None, None),
    ]:
        pass
    async def try271(coro_factory):
        try:
            async with db.unit_of_work() as uow:
                await coro_factory(uow)
            return False
        except ValidationError:
            return True
    r1 = await try271(lambda uow: uow.breaks.assign(bid271, tid271, owner="  ", by="qa", at="t"))
    r2 = await try271(lambda uow: uow.breaks.explain(bid271, tid271, text="", by="qa", at="t"))
    r3 = await try271(lambda uow: uow.breaks.accept(bid271, tid271, reason="  ", by="qa", at="t"))
    R("DB-271", r1 and r2 and r3, f"assign('  ')={r1}, explain('')={r2}, accept('  ')={r3}")

    # DB-272: handover recorded in comment trail
    async with db.unit_of_work() as uow:
        await uow.breaks.assign(bid271, tid271, owner="alice", by="qa", at="2026-01-01T00:00:00Z")
    async with db.unit_of_work() as uow:
        await uow.breaks.assign(bid271, tid271, owner="bob", by="qa", at="2026-01-02T00:00:00Z")
    async with db.unit_of_work() as uow:
        row272 = await uow.breaks.get(bid271)
    comments272 = row272.comments_json or []
    handover_comment = [c for c in comments272 if "Reassigned from alice to bob" in c.get("text", "")]
    R("DB-272", bool(handover_comment), f"comments={comments272}")

    # DB-273: accepting a cleared break refused
    async with db.unit_of_work() as uow:
        t273 = uow.tenants.create(slug="rc273", display_name="RC273")
        await uow.flush()
        tid273 = str(t273.id)
        await uow.breaks.observe([mk_break("k273")], tenant_id=tid273, definition="def273", when="2026-01-01T00:00:00Z")
        await uow.breaks.observe([], tenant_id=tid273, definition="def273", when="2026-01-02T00:00:00Z")
        rows273 = await uow.breaks.for_definition(tid273, "def273")
        bid273 = str(rows273[0].id)
    try:
        async with db.unit_of_work() as uow:
            await uow.breaks.accept(bid273, tid273, reason="x", by="qa", at="t")
        R("DB-273", False, "no exception accepting a cleared break")
    except ConflictError as e:
        ok273 = "gone" in str(e).lower()
        R("DB-273", ok273, str(e))

    # DB-274: explain/assign append, never rewrite
    async with db.unit_of_work() as uow:
        t274 = uow.tenants.create(slug="rc274", display_name="RC274")
        await uow.flush()
        tid274 = str(t274.id)
        await uow.breaks.observe([mk_break("k274")], tenant_id=tid274, definition="def274", when="2026-01-01T00:00:00Z")
        rows274 = await uow.breaks.for_definition(tid274, "def274")
        bid274 = str(rows274[0].id)
        await uow.breaks.explain(bid274, tid274, text="first note", by="qa", at="t1")
        await uow.breaks.explain(bid274, tid274, text="second note", by="qa", at="t2")
    async with db.unit_of_work() as uow:
        await uow.breaks.explain(bid274, tid274, text="third note", by="qa", at="t3")
    async with db.unit_of_work() as uow:
        row274 = await uow.breaks.get(bid274)
    texts274 = [c["text"] for c in row274.comments_json]
    R("DB-274", texts274 == ["first note", "second note", "third note"], f"comments={texts274}")

    # DB-275: delete refused
    try:
        async with db.unit_of_work() as uow:
            row275 = await uow.breaks.get(bid274)
            await uow.breaks.delete(row275)
        R("DB-275", False, "no exception")
    except ConflictError as e:
        ok275 = "four hundred breaks" in str(e)
        R("DB-275", ok275, str(e))

    # DB-276: in_tenant reports absent for wrong tenant
    async with db.unit_of_work() as uow:
        t276 = uow.tenants.create(slug="rc276", display_name="RC276")
        await uow.flush()
        tid276 = str(t276.id)
    try:
        async with db.unit_of_work() as uow:
            await uow.breaks.in_tenant(bid274, tid276)
        R("DB-276", False, "no exception")
    except NotFoundError:
        R("DB-276", True, "reported not found for wrong tenant")

    # DB-277: missing side renders as "", zero renders as "0"
    async with db.unit_of_work() as uow:
        t277 = uow.tenants.create(slug="rc277", display_name="RC277")
        await uow.flush()
        tid277 = str(t277.id)
        missing_break = Break(key="k277-missing", kind=BreakKind.MISSING, left=Decimal("5.00"), right=None, because="no right side")
        zero_break = Break(key="k277-zero", kind=BreakKind.GENUINE, left=Decimal("5.00"), right=Decimal("0"), because="zero on right")
        await uow.breaks.observe([missing_break, zero_break], tenant_id=tid277, definition="def277", when="2026-01-01T00:00:00Z")
    async with db.unit_of_work() as uow:
        rows277 = await uow.breaks.for_definition(tid277, "def277")
    by_key277 = {r.break_key: r.right_value for r in rows277}
    R("DB-277", by_key277.get("k277-missing") == "" and by_key277.get("k277-zero") == "0",
      f"missing side stored as={by_key277.get('k277-missing')!r}, zero side stored as={by_key277.get('k277-zero')!r}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
