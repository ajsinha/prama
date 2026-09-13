import sys, os, asyncio, tempfile, time, statistics
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from datetime import datetime, UTC
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, text as satext
from prama.db.types import UtcDateTime

# CFG-163
engine = create_engine("sqlite:///:memory:")
metadata = MetaData()
tbl = Table("t163", metadata, Column("id", Integer, primary_key=True), Column("ts", UtcDateTime))
metadata.create_all(engine)
lengths = {}
with engine.begin() as conn:
    for label, us in [("us0", 0), ("us999999", 999999)]:
        dt = datetime(2026, 1, 1, 0, 0, 0, us, tzinfo=UTC)
        conn.execute(tbl.insert().values(id=hash(label) % 100000, ts=dt))
        raw = conn.execute(satext(f"SELECT ts FROM t163 WHERE id={hash(label) % 100000}")).scalar()
        lengths[label] = (raw, len(raw))
lens = {k: v[1] for k, v in lengths.items()}
R("CFG-163", len(set(lens.values())) == 1 and all(27 <= ln <= 28 for ln in lens.values()),
  f"lengths={lens} (fixed-width, within the catalogue's accepted 27-28 range and well inside VARCHAR(32)); values={ {k: v[0] for k, v in lengths.items()} }")

# CFG-164
import random
tbl2 = Table("t164", metadata, Column("id", Integer, primary_key=True), Column("ts", UtcDateTime))
metadata.create_all(engine)
instants = [datetime(2026, m, 1, tzinfo=UTC) for m in range(1, 13)]
shuffled = instants[:]
random.shuffle(shuffled)
with engine.begin() as conn:
    for i, dt in enumerate(shuffled):
        conn.execute(tbl2.insert().values(id=i, ts=dt))
    rows = conn.execute(satext("SELECT ts FROM t164 ORDER BY ts")).fetchall()
sorted_strings = [r[0] for r in rows]
expected_sorted = sorted(i.isoformat(timespec="microseconds").replace("+00:00", "Z") for i in instants)
R("CFG-164", sorted_strings == expected_sorted, f"ORDER BY ts result matches chronological order={sorted_strings == expected_sorted}")

# DB-034: comment-only schema change is DIGEST drift, informational
from prama.db import Database
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
import shutil

async def db034():
    tmp = tempfile.mkdtemp(prefix="dbqa-034-")
    dbpath = os.path.join(tmp, "d.db")
    schema_dir = os.path.join(tmp, "schema")
    shutil.copytree(os.path.join(REPO, "schema"), schema_dir)
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": dbpath}, "schema_dir": schema_dir}}))
    settings = DbSettings.from_config(cfg)
    db = Database(settings)
    db.initialise(applied_by="qa")
    # append a comment to the copy
    with open(os.path.join(schema_dir, "sqlite.sql"), "a") as f:
        f.write("\n-- a harmless trailing comment\n")
    report = db.verify()
    from prama.db.schema.verifier import DriftKind
    digest_drifts = [d for d in report.drifts if d.kind == DriftKind.DIGEST]
    return report.ok, digest_drifts

ok034, digest_drifts034 = asyncio.run(db034())
R("DB-034", ok034 and bool(digest_drifts034), f"report.ok={ok034} (must stay True -- DIGEST is not in BLOCKING); digest drifts found={[d.detail[:60] for d in digest_drifts034]}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")

# --- DB-084, 137, 147, 148, 214 ---
from prama.core.errors import ConflictError, ValidationError

def make_db2(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

async def more():
    tmp = tempfile.mkdtemp(prefix="dbqa-catchup-")
    p = os.path.join(tmp, "d.db")
    db = make_db2(p)
    db.initialise(applied_by="qa")
    await db.start()

    # DB-084: translated error does not leak driver parameters (password hash in the row)
    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="cu", display_name="CU")
        await uow.flush()
        tid = str(t.id)
        pr = uow.principals.create(tenant_id=tid, username="alice084", display_name="Alice")
        await uow.flush()
        uow.principals.set_password(pr, "a-secret-password-084")
        secret_hash = pr.password_hash
    try:
        async with db.unit_of_work() as uow:
            uow.principals.create(tenant_id=tid, username="alice084", display_name="Alice2")  # duplicate username -> IntegrityError
        r_db084 = ("FAIL", "no exception")
    except ConflictError as e:
        detail = e.context.get("detail", "")
        leaked = secret_hash in detail or secret_hash in str(e)
        r_db084 = ("FAIL" if leaked else "PASS", f"detail={detail!r}; password hash leaked into translated error={leaked}")

    # DB-137: timing side channel -- unknown vs known username
    async with db.unit_of_work() as uow:
        pr137 = uow.principals.create(tenant_id=tid, username="known137", display_name="Known")
        await uow.flush()
        uow.principals.set_password(pr137, "correct-password-137")
    known_times = []
    unknown_times = []
    for _ in range(100):
        async with db.unit_of_work() as uow:
            t0 = time.perf_counter()
            await uow.principals.authenticate(tid, "known137", "wrong-password-attempt")
            known_times.append(time.perf_counter() - t0)
        async with db.unit_of_work() as uow:
            t0 = time.perf_counter()
            await uow.principals.authenticate(tid, "no-such-user-137", "wrong-password-attempt")
            unknown_times.append(time.perf_counter() - t0)
    med_known = statistics.median(known_times)
    med_unknown = statistics.median(unknown_times)
    ratio = max(med_known, med_unknown) / max(min(med_known, med_unknown), 1e-9)
    r_db137 = ("PASS" if ratio < 3.0 else "FAIL",
               f"median known-username auth={med_known*1000:.3f}ms, median unknown-username auth={med_unknown*1000:.3f}ms, ratio={ratio:.2f}x "
               f"(no order-of-magnitude difference={ratio < 3.0})")

    # DB-147/148: concurrent grants -- one row, no ConflictError, same outcome as re-grant
    async with db.unit_of_work() as uow:
        p147 = uow.principals.create(tenant_id=tid, username="p147", display_name="P147")
        role147 = uow.roles.create(tenant_id=tid, name="role147", permissions=["read"])
        await uow.flush()
        pid147, rid147 = str(p147.id), str(role147.id)
    uowA = db.unit_of_work()
    uowB = db.unit_of_work()
    async def do_grant(uow):
        try:
            await uow.roles.grant(pid147, rid147, granted_by="qa")
            await uow.commit()
            return "ok"
        except ConflictError:
            return "ConflictError"
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        finally:
            await uow.close()
    gA, gB = await asyncio.gather(do_grant(uowA), do_grant(uowB))
    async with db.unit_of_work() as uow:
        roles_after147 = await uow.principals.roles_of(pid147)
    r_db147 = ("PASS" if len(roles_after147) == 1 and "ConflictError" not in (gA, gB) and not any(x.startswith(("IntegrityError","OperationalError")) for x in (gA,gB)) else "FAIL",
               f"gA={gA}, gB={gB}, roles after both grants={[r.name for r in roles_after147]}")

    # DB-148: grant, re-grant works (already proven on sqlite via DB-146); postgres side blocked (async engine unusable, see DB-066/070/072/279)
    r_db148 = ("FAIL",
               "sqlite side proven via DB-146/147 (grant then re-grant is idempotent, one row). PostgreSQL side cannot be "
               "exercised: constructing the async engine for dialect=postgres raises DB.ENGINE_CREATE_FAILED "
               "('Pool class QueuePool cannot be used with asyncio engine'), the same confirmed defect blocking DB-066/070/072/279.")

    # DB-214: PQL that parses but cannot be lowered -> empty plan_id, control still stored
    pql214 = "CHECK t.a IS VALID 'totally_unregistered_validator_xyz' SEVERITY minor DIMENSION validity BECAUSE 'x'"
    async with db.unit_of_work() as uow:
        e214, v214 = await uow.controls.declare(tenant_id=tid, identity="id-214", pql=pql214)
    async with db.unit_of_work() as uow:
        stored214 = await uow.controls.current(str(e214.id), tenant_id=tid)
    r_db214 = ("PASS" if stored214 is not None and stored214.plan_id == "" else "FAIL",
               f"control stored={stored214 is not None}, plan_id={(stored214.plan_id if stored214 else None)!r}")

    await db.stop()
    return r_db084, r_db137, r_db147, r_db148, r_db214

r084, r137, r147, r148, r214 = asyncio.run(more())
print(f"DB-084: {r084[0]} :: {r084[1]}")
print(f"DB-137: {r137[0]} :: {r137[1]}")
print(f"DB-147: {r147[0]} :: {r147[1]}")
print(f"DB-148: {r148[0]} :: {r148[1]}")
print(f"DB-214: {r214[0]} :: {r214[1]}")
