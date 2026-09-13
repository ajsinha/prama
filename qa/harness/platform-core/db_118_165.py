import sys, os, asyncio, tempfile, time
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
    tmp = tempfile.mkdtemp(prefix="dbqa-daos-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    # DB-118
    async with db.unit_of_work() as uow:
        missing = await uow.tenants.get(new_ulid())
    R("DB-118", missing is None, repr(missing))

    # DB-119
    try:
        async with db.unit_of_work() as uow:
            await uow.tenants.require(new_ulid())
        R("DB-119", False, "no exception")
    except NotFoundError as e:
        ok = e.code == "ENTITY.NOT_FOUND" and "Tenant" in str(e) and "list" in e.remedy.lower()
        R("DB-119", ok, f"{e.code}: {e}; remedy={e.remedy!r}")

    # DB-120
    async with db.unit_of_work() as uow:
        c = await uow.tenants.count()
    R("DB-120", c == 0, repr(c))

    # setup: two tenants with rows
    async with db.unit_of_work() as uow:
        ta = uow.tenants.create(slug="ta", display_name="TA")
        tb = uow.tenants.create(slug="tb", display_name="TB")
        await uow.flush()
        ta_id, tb_id = str(ta.id), str(tb.id)
        for i in range(10):
            uow.principals.create(tenant_id=ta_id, username=f"a-user{i}", display_name=f"A{i}")
        for i in range(3):
            uow.principals.create(tenant_id=tb_id, username=f"b-user{i}", display_name=f"B{i}")

    # DB-121
    from sqlalchemy import select
    from prama.db.models.platform import Principal
    async with db.unit_of_work() as uow:
        cnt = await uow.principals.count(select(Principal).where(Principal.tenant_id == ta_id))
    R("DB-121", cnt == 10, repr(cnt))

    # DB-122
    async with db.unit_of_work() as uow:
        rows_a = await uow.principals.list_for_tenant(ta_id, limit=100)
        rows_b = await uow.principals.list_for_tenant(tb_id, limit=100)
    R("DB-122", len(rows_a) == 10 and len(rows_b) == 3 and all(r.tenant_id == ta_id for r in rows_a),
      f"tenant A rows={len(rows_a)}, tenant B rows={len(rows_b)}")

    # DB-123: 25 rows paging deterministically -- reuse tenant A's 10 + add 15 more
    async with db.unit_of_work() as uow:
        for i in range(10, 25):
            uow.principals.create(tenant_id=ta_id, username=f"a-user{i}", display_name=f"A{i}")
    async with db.unit_of_work() as uow:
        seen = []
        for offset in (0, 10, 20):
            page = await uow.principals.list_for_tenant(ta_id, limit=10, offset=offset)
            seen.extend([r.id for r in page])
    R("DB-123", len(seen) == 25 and len(set(seen)) == 25, f"total across 3 pages={len(seen)}, unique={len(set(seen))}")

    # DB-124
    async with db.unit_of_work() as uow:
        zero = await uow.principals.list_for_tenant(ta_id, limit=0)
    R("DB-124", zero == [], f"list_for_tenant(limit=0) -> {len(zero)} rows")

    # DB-125
    try:
        async with db.unit_of_work() as uow:
            neg = await uow.principals.list_for_tenant(ta_id, limit=-1)
        R("DB-125", False, f"no refusal for limit=-1; returned {len(neg)} rows: {[r.username for r in neg][:3]}")
    except ValidationError as e:
        R("DB-125", True, f"named refusal: {e.code}: {e}")
    except Exception as e:
        R("DB-125", False, f"engine error escaped rather than a named refusal: {type(e).__name__}: {e}")

    # DB-126 / DB-127
    async with db.unit_of_work() as uow:
        row_a = (await uow.principals.list_for_tenant(ta_id, limit=1))[0]
        cross = await uow.principals.get_for_tenant(tb_id, str(row_a.id))
    R("DB-126", cross is None, repr(cross))
    try:
        async with db.unit_of_work() as uow:
            await uow.principals.require_for_tenant(tb_id, str(row_a.id))
        R("DB-127", False, "no exception")
    except NotFoundError as e:
        R("DB-127", "does not exist in this tenant" in str(e), str(e))

    # DB-128
    async with db.unit_of_work() as uow:
        cnt_a = await uow.principals.count_for_tenant(ta_id)
        cnt_b = await uow.principals.count_for_tenant(tb_id)
    R("DB-128", cnt_a == 25 and cnt_b == 3, f"a={cnt_a}, b={cnt_b}")

    # DB-129
    async with db.unit_of_work() as uow:
        found = await uow.tenants.by_slug("ta")
        notfound = await uow.tenants.by_slug("no-such-slug")
    R("DB-129", found is not None and found.slug == "ta" and notfound is None, f"found={found}, notfound={notfound}")

    # DB-130
    async with db.unit_of_work() as uow:
        tnew = uow.tenants.create(slug="t130", display_name="T130")
        await uow.flush()
        eq = tnew.created_at == tnew.updated_at
        aware = tnew.created_at.tzinfo is not None
    R("DB-130", eq and aware, f"created==updated={eq}, tz-aware={aware}")

    # DB-131
    async with db.unit_of_work() as uow:
        t_susp = uow.tenants.create(slug="t131-susp", display_name="Susp", )
        await uow.flush()
        t_susp.status = "suspended"
        await uow.flush()
        active_list = await uow.tenants.list_active()
    R("DB-131", "t131-susp" not in [t.slug for t in active_list], f"suspended tenant in list_active()={'t131-susp' in [t.slug for t in active_list]}")

    # DB-132
    async with db.unit_of_work() as uow:
        pr = uow.principals.create(tenant_id=ta_id, username="pwtest132", display_name="PW")
        await uow.flush()
        try:
            uow.principals.set_password(pr, "a" * 11)
            eleven_ok = False
        except ValidationError:
            eleven_ok = True
        try:
            uow.principals.set_password(pr, "a" * 12)
            twelve_ok = True
        except ValidationError:
            twelve_ok = False
    R("DB-132", eleven_ok and twelve_ok, f"11-char refused={eleven_ok}, 12-char accepted={twelve_ok}")

    # DB-133
    async with db.unit_of_work() as uow:
        pr2 = uow.principals.create(tenant_id=ta_id, username="pwtest133", display_name="PW2")
        await uow.flush()
        try:
            uow.principals.set_password(pr2, "shortpw123")
            R("DB-133", False, "no exception")
        except ValidationError as e:
            leaked = "shortpw123" in str(e) or "shortpw123" in str(e.context)
            has_username = e.context.get("principal") == "pwtest133"
            R("DB-133", not leaked and has_username, f"context={e.context}, str(e)={e}")

    # DB-134
    async with db.unit_of_work() as uow:
        pr3 = uow.principals.create(tenant_id=ta_id, username="pwtest134", display_name="PW3")
        await uow.flush()
        before_updated = pr3.updated_at
        uow.principals.set_password(pr3, "a-real-password-123")
        after_updated = pr3.updated_at
        cols = {c.name: getattr(pr3, c.name) for c in pr3.__table__.columns}
    plaintext_nowhere = all("a-real-password-123" not in str(v) for v in cols.values())
    R("DB-134", plaintext_nowhere and after_updated > before_updated and cols["password_hash"] != "a-real-password-123",
      f"plaintext absent from all columns={plaintext_nowhere}, updated_at advanced={after_updated > before_updated}")

    # DB-135
    async with db.unit_of_work() as uow:
        pr4 = uow.principals.create(tenant_id=ta_id, username="authtest135", display_name="Auth")
        await uow.flush()
        uow.principals.set_password(pr4, "correct-password-135")
    async with db.unit_of_work() as uow:
        authed = await uow.principals.authenticate(ta_id, "authtest135", "correct-password-135")
    R("DB-135", authed is not None and authed.last_login_at is not None, f"authed={authed}, last_login_at={authed.last_login_at if authed else None}")

    # DB-136
    async with db.unit_of_work() as uow:
        pr5 = uow.principals.create(tenant_id=ta_id, username="disabled136", display_name="Dis")
        await uow.flush()
        uow.principals.set_password(pr5, "correct-password-136")
        pr5.status = "disabled"
        pr6 = uow.principals.create(tenant_id=ta_id, username="nopass136", display_name="NoPass")
    async with db.unit_of_work() as uow:
        r_unknown = await uow.principals.authenticate(ta_id, "no-such-user-136", "whatever")
        r_wrongpw = await uow.principals.authenticate(ta_id, "authtest135", "wrong-password")
        r_disabled = await uow.principals.authenticate(ta_id, "disabled136", "correct-password-136")
        r_nopass = await uow.principals.authenticate(ta_id, "nopass136", "whatever")
    R("DB-136", all(x is None for x in (r_unknown, r_wrongpw, r_disabled, r_nopass)),
      f"unknown={r_unknown}, wrongpw={r_wrongpw}, disabled={r_disabled}, nopass={r_nopass}")

    # DB-138
    import prama.db.dao.platform as platform_mod
    R("DB-138", isinstance(platform_mod._DUMMY_HASH, str) and platform_mod._DUMMY_HASH.startswith("pbkdf2_sha256$"),
      f"_DUMMY_HASH is a module-level constant computed once: {platform_mod._DUMMY_HASH[:30]}...")

    # DB-139
    from prama.db.security import PasswordHasher
    async with db.unit_of_work() as uow:
        pr7 = uow.principals.create(tenant_id=ta_id, username="rehash139", display_name="Rehash")
        await uow.flush()
        weak_hasher = PasswordHasher(iterations=100_000)
        uow.principals.set_password(pr7, "rehash-password-139", hasher=weak_hasher)
        old_stored = pr7.password_hash
    async with db.unit_of_work() as uow:
        authed139 = await uow.principals.authenticate(ta_id, "rehash139", "rehash-password-139")
        new_stored = authed139.password_hash if authed139 else None
    R("DB-139", authed139 is not None and new_stored != old_stored and "210000" in (new_stored or ""),
      f"authenticated={authed139 is not None}; hash changed={new_stored != old_stored}; new hash iterations visible=210000 in new_stored={'210000' in (new_stored or '')}")

    # DB-140
    async with db.unit_of_work() as uow:
        pr8 = uow.principals.create(tenant_id=ta_id, username="locked140", display_name="Locked")
        await uow.flush()
        uow.principals.set_password(pr8, "locked-password-140")
        pr8.status = "locked"
        before_login = pr8.last_login_at
    async with db.unit_of_work() as uow:
        r140 = await uow.principals.authenticate(ta_id, "locked140", "locked-password-140")
    async with db.unit_of_work() as uow:
        pr8_after = await uow.principals.by_username(ta_id, "locked140")
    R("DB-140", r140 is None and pr8_after.last_login_at == before_login, f"authenticate result={r140}; last_login_at unchanged={pr8_after.last_login_at == before_login}")

    # DB-141
    async with db.unit_of_work() as uow:
        alice_a = uow.principals.create(tenant_id=ta_id, username="alice141", display_name="Alice A")
        alice_b = uow.principals.create(tenant_id=tb_id, username="alice141", display_name="Alice B")
        await uow.flush()
        uow.principals.set_password(alice_a, "alice-a-password-1")
        uow.principals.set_password(alice_b, "alice-b-password-2")
    async with db.unit_of_work() as uow:
        cross1 = await uow.principals.authenticate(ta_id, "alice141", "alice-b-password-2")
        cross2 = await uow.principals.authenticate(tb_id, "alice141", "alice-a-password-1")
    R("DB-141", cross1 is None and cross2 is None, f"tenant A with B's password={cross1}; tenant B with A's password={cross2}")

    # DB-142
    async with db.unit_of_work() as uow:
        p142a = uow.principals.create(tenant_id=ta_id, username="okta-a", display_name="OktaA")
        p142b = uow.principals.create(tenant_id=tb_id, username="okta-b", display_name="OktaB")
        await uow.flush()
        p142a.external_idp = "okta"
        p142a.external_id = "collide-123"
        p142b.external_idp = "okta"
        p142b.external_id = "collide-123"
        await uow.flush()
        try:
            got142 = await uow.principals.by_external_id("okta", "collide-123")
            R("DB-142", False,
              f"by_external_id('okta','collide-123') takes no tenant argument and both tenant A and B were able to "
              f"write the SAME (idp, external_id) pair with no unique constraint stopping it (schema has no UNIQUE "
              f"on (external_idp, external_id)); the lookup returned one arbitrary match "
              f"({got142.tenant_id if got142 else None}) -- an SSO sign-in for this idp+external_id pair can "
              f"resolve to the WRONG tenant's principal")
        except Exception as e:
            R("DB-142", False,
              f"WORSE than a wrong-tenant match: by_external_id('okta','collide-123') raised a raw, untranslated "
              f"{type(e).__name__} ({e}) once two tenants collide on the pair -- since by_external_id has no tenant "
              f"argument at all and the schema has no UNIQUE constraint on (external_idp, external_id), the SSO "
              f"sign-in path crashes with an unhandled SQLAlchemy exception rather than signing anyone in or "
              f"refusing cleanly")

    # DB-143
    async with db.unit_of_work() as uow:
        t143 = uow.tenants.create(slug="t143", display_name="T143")
        await uow.flush()
        p143 = uow.principals.create(tenant_id=str(t143.id), username="only143", display_name="Only")
        await uow.flush()
        p143.status = "disabled"
        any143 = await uow.principals.any_for(str(t143.id))
    R("DB-143", any143 is False, repr(any143))

    # DB-144
    async with db.unit_of_work() as uow:
        t144 = uow.tenants.create(slug="t144", display_name="T144")
        await uow.flush()
        p144 = uow.principals.create(tenant_id=str(t144.id), username="rolesof144", display_name="RolesOf")
        await uow.flush()
        for name in ("zeta", "alpha", "mu"):
            role = uow.roles.create(tenant_id=str(t144.id), name=name, permissions=["x"])
            await uow.flush()
            await uow.roles.grant(str(p144.id), str(role.id))
        roles144 = await uow.principals.roles_of(str(p144.id))
        roles_missing = await uow.principals.roles_of(new_ulid())
    R("DB-144", [r.name for r in roles144] == ["alpha", "mu", "zeta"] and roles_missing == [],
      f"roles sorted={[r.name for r in roles144]}, unknown-id result={roles_missing}")

    # DB-146 / DB-147
    async with db.unit_of_work() as uow:
        t146 = uow.tenants.create(slug="t146", display_name="T146")
        await uow.flush()
        p146 = uow.principals.create(tenant_id=str(t146.id), username="grant146", display_name="Grant")
        role146 = uow.roles.create(tenant_id=str(t146.id), name="viewer146", permissions=["read"])
        await uow.flush()
        await uow.roles.grant(str(p146.id), str(role146.id))
        await uow.roles.grant(str(p146.id), str(role146.id))
        roles_after = await uow.principals.roles_of(str(p146.id))
    R("DB-146", len(roles_after) == 1, f"role count after granting twice={len(roles_after)}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
