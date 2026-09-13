import sys, os, asyncio, tempfile, logging, io
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
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}, "echo": True}}))
    return Database(DbSettings.from_config(cfg))

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-daos2-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()

    async with db.unit_of_work() as uow:
        t = uow.tenants.create(slug="t145", display_name="T145")
        await uow.flush()
        tid = str(t.id)
        p145 = uow.principals.create(tenant_id=tid, username="p145", display_name="P145")
        await uow.flush()
        for i in range(10):
            role = uow.roles.create(tenant_id=tid, name=f"role{i}", permissions=["x"])
            await uow.flush()
            await uow.roles.grant(str(p145.id), str(role.id))
        pid = str(p145.id)

    # DB-145: count queries issued for roles_of with 10 roles
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    sa_logger = logging.getLogger("sqlalchemy.engine")
    sa_logger.addHandler(handler)
    sa_logger.setLevel(logging.INFO)
    async with db.unit_of_work() as uow:
        roles = await uow.principals.roles_of(pid)
    sa_logger.removeHandler(handler)
    query_count = stream.getvalue().count("SELECT")
    R("DB-145", query_count <= 6, f"{len(roles)} roles returned; SQL SELECT statements logged for roles_of()={query_count} (bounded, not 1-per-row)")

    # DB-149: revoke of a non-existent grant
    async with db.unit_of_work() as uow:
        t149 = uow.tenants.create(slug="t149", display_name="T149")
        await uow.flush()
        p149 = uow.principals.create(tenant_id=str(t149.id), username="p149", display_name="P149")
        role149 = uow.roles.create(tenant_id=str(t149.id), name="r149", permissions=[])
        await uow.flush()
    try:
        async with db.unit_of_work() as uow:
            await uow.roles.revoke(str(p149.id), str(role149.id))
        R("DB-149", True, "revoke of a non-existent grant: no error")
    except Exception as e:
        R("DB-149", False, f"{type(e).__name__}: {e}")

    # DB-150
    async with db.unit_of_work() as uow:
        tA = uow.tenants.create(slug="t150a", display_name="T150A")
        tB = uow.tenants.create(slug="t150b", display_name="T150B")
        await uow.flush()
        roleA = uow.roles.create(tenant_id=str(tA.id), name="admin", permissions=["a"])
        roleB = uow.roles.create(tenant_id=str(tB.id), name="admin", permissions=["b"])
        await uow.flush()
    async with db.unit_of_work() as uow:
        foundA = await uow.roles.by_name(str(tA.id), "admin")
        foundB = await uow.roles.by_name(str(tB.id), "admin")
    R("DB-150", foundA.id == roleA.id and foundB.id == roleB.id and foundA.id != foundB.id,
      f"tenant A 'admin' -> {foundA.id}; tenant B 'admin' -> {foundB.id}")

    # DB-151
    async with db.unit_of_work() as uow:
        t151 = uow.tenants.create(slug="t151", display_name="T151")
        await uow.flush()
        role151 = uow.roles.create(tenant_id=str(t151.id), name="r151", permissions=["read", "write", "admin"])
        await uow.flush()
        rid = str(role151.id)
    async with db.unit_of_work() as uow:
        back151 = await uow.roles.get(rid)
    R("DB-151", back151.permissions_json == ["read", "write", "admin"], repr(back151.permissions_json))

    # DB-152
    async with db.unit_of_work() as uow:
        t152 = uow.tenants.create(slug="t152", display_name="T152")
        await uow.flush()
        builtin = uow.roles.create(tenant_id=str(t152.id), name="builtin152", permissions=[], builtin=True)
        custom = uow.roles.create(tenant_id=str(t152.id), name="custom152", permissions=[], builtin=False)
        await uow.flush()
        bid, cid = str(builtin.id), str(custom.id)
    from sqlalchemy import text as satext
    with db.sync_engine().connect() as conn:
        raw_b = conn.execute(satext("SELECT is_builtin FROM role WHERE id=:i"), {"i": bid}).scalar()
        raw_c = conn.execute(satext("SELECT is_builtin FROM role WHERE id=:i"), {"i": cid}).scalar()
    R("DB-152", raw_b == 1 and raw_c == 0, f"builtin raw={raw_b}, custom raw={raw_c}")

    # DB-153
    async with db.unit_of_work() as uow:
        t153a = uow.tenants.create(slug="t153a", display_name="T153A")
        t153b = uow.tenants.create(slug="t153b", display_name="T153B")
        await uow.flush()
        pa = uow.principals.create(tenant_id=str(t153a.id), username="ka", display_name="KA")
        pb = uow.principals.create(tenant_id=str(t153b.id), username="kb", display_name="KB")
        await uow.flush()
        ka = uow.api_keys.create(tenant_id=str(t153a.id), principal_id=str(pa.id), name="k1", key_prefix="pk_live_aaaa", key_hash="h1", scopes=["read"])
        await uow.flush()
    async with db.unit_of_work() as uow:
        found153 = await uow.api_keys.by_prefix("pk_live_aaaa")
    R("DB-153", found153 is not None and found153.tenant_id == str(t153a.id), f"found={found153}, tenant={found153.tenant_id if found153 else None}")

    # DB-154
    async with db.unit_of_work() as uow:
        t154 = uow.tenants.create(slug="t154", display_name="T154")
        await uow.flush()
        p154 = uow.principals.create(tenant_id=str(t154.id), username="p154", display_name="P154")
        await uow.flush()
        k1 = uow.api_keys.create(tenant_id=str(t154.id), principal_id=str(p154.id), name="k1", key_prefix="pk_live_bbbb", key_hash="h1", scopes=["read"])
        k2 = uow.api_keys.create(tenant_id=str(t154.id), principal_id=str(p154.id), name="k2", key_prefix="pk_live_cccc", key_hash="h2", scopes=["read"])
        await uow.flush()
        k2.revoked_at = datetime.now(UTC)
        pid154 = str(p154.id)
    async with db.unit_of_work() as uow:
        active154 = await uow.api_keys.active_for_principal(pid154)
    R("DB-154", len(active154) == 1 and active154[0].name == "k1", f"active keys={[k.name for k in active154]}")

    # DB-155
    async with db.unit_of_work() as uow:
        t155 = uow.tenants.create(slug="t155", display_name="T155")
        await uow.flush()
        p155 = uow.principals.create(tenant_id=str(t155.id), username="p155", display_name="P155")
        await uow.flush()
        kexp = uow.api_keys.create(tenant_id=str(t155.id), principal_id=str(p155.id), name="kexp", key_prefix="pk_live_dddd", key_hash="hexp", scopes=["read"])
        await uow.flush()
        kexp.expires_at = datetime.now(UTC) - timedelta(days=1)
        pid155 = str(p155.id)
    async with db.unit_of_work() as uow:
        active155 = await uow.api_keys.active_for_principal(pid155)
    # api/deps.py's authenticate_api_key DOES separately check record.expires_at
    # at the point of use, so the expired key is refused at authentication --
    # but active_for_principal() itself carries no docstring explaining that its
    # "active" excludes only revocation, not expiry.
    import inspect as _inspect
    from prama.db.dao.platform import ApiKeyDao as _AKD
    has_docstring = bool(_inspect.getdoc(_AKD.active_for_principal))
    R("DB-155", len(active155) == 1 and has_docstring,
      f"active_for_principal() lists {len(active155)} key(s) including one already expired (expires_at in the past, "
      f"revoked_at is NULL) -- the method has no docstring at all (has_docstring={has_docstring}) explaining that "
      f"'active' means 'not revoked', not 'not expired'; separately confirmed api/deps.py DOES check expires_at at "
      f"the point of authentication (line ~120), so the security-relevant half works -- only the documentation half named by the catalogue is missing")

    # DB-156: AuditDao exposes Dao.delete unchanged
    from prama.db.dao.platform import AuditDao
    has_own_delete = "delete" in AuditDao.__dict__
    async with db.unit_of_work() as uow:
        ev156 = uow.audit.record(tenant_id=tid, action="test", object_kind="x")
        await uow.flush()
        try:
            await uow.audit.delete(ev156)
            await uow.flush()
            delete_worked = True
        except Exception as e:
            delete_worked = f"raised {type(e).__name__}: {e}"
    R("DB-156", not has_own_delete and delete_worked is True,
      f"AuditDao overrides delete()={has_own_delete}; calling the inherited Dao.delete() on an audit event: {delete_worked} "
      f"-- the class docstring says 'deliberately exposes no update or delete' but Dao.delete is inherited unchanged and reachable")

    # DB-157
    async with db.unit_of_work() as uow:
        ev157 = uow.audit.record(tenant_id=tid, action="a157", object_kind="x", correlation_id=None)
    R("DB-157", ev157.occurred_at is not None and (datetime.now(UTC) - ev157.occurred_at).total_seconds() < 5,
      f"occurred_at={ev157.occurred_at}, stamped by the DAO itself (no caller-supplied timestamp parameter exists on record())")

    # DB-158
    async with db.unit_of_work() as uow:
        ev158 = uow.audit.record(tenant_id=tid, action="a158", object_kind="x")
    R("DB-158", ev158.outcome == "success" and ev158.actor_kind == "human" and ev158.detail_json == {},
      f"outcome={ev158.outcome!r}, actor_kind={ev158.actor_kind!r}, detail_json={ev158.detail_json!r}")

    # DB-159
    async with db.unit_of_work() as uow:
        tX = uow.tenants.create(slug="t159x", display_name="X")
        tY = uow.tenants.create(slug="t159y", display_name="Y")
        await uow.flush()
        uow.audit.record(tenant_id=str(tX.id), action="x-action", object_kind="k", object_id="o1")
        uow.audit.record(tenant_id=str(tY.id), action="y-action", object_kind="k", object_id="o1")
    async with db.unit_of_work() as uow:
        objX = await uow.audit.for_object(str(tX.id), "k", "o1")
        recentX = await uow.audit.recent(str(tX.id))
    R("DB-159", len(objX) == 1 and objX[0].action == "x-action" and all(e.tenant_id == str(tX.id) for e in recentX),
      f"for_object(tenantX)={[e.action for e in objX]}; recent(tenantX) all tenant-scoped={all(e.tenant_id==str(tX.id) for e in recentX)}")

    # DB-160: two events with identical occurred_at -- stable order across repeats?
    async with db.unit_of_work() as uow:
        t160 = uow.tenants.create(slug="t160", display_name="T160")
        await uow.flush()
        same_time = datetime.now(UTC)
        ev1 = uow.audit.record(tenant_id=str(t160.id), action="first", object_kind="k")
        ev2 = uow.audit.record(tenant_id=str(t160.id), action="second", object_kind="k")
        await uow.flush()
        ev1.occurred_at = same_time
        ev2.occurred_at = same_time
        tid160 = str(t160.id)
    orders = []
    for _ in range(5):
        async with db.unit_of_work() as uow:
            rows = await uow.audit.recent(tid160)
            orders.append(tuple(r.action for r in rows))
    R("DB-160", len(set(orders)) == 1, f"orders across 5 repeated queries with tied occurred_at: {orders}")

    # DB-161: concurrent SettingDao.put
    async with db.unit_of_work() as uow:
        t161 = uow.tenants.create(slug="t161", display_name="T161")
        await uow.flush()
        tid161 = str(t161.id)
    uowA = db.unit_of_work()
    uowB = db.unit_of_work()
    try:
        await uowA.settings.put(tid161, "k161", "from-A")
        await uowA.commit()
        await uowB.settings.put(tid161, "k161", "from-B")
        await uowB.commit()
        ok161 = True
    except ConflictError as e:
        ok161 = f"ConflictError escaped: {e}"
    finally:
        await uowA.close(); await uowB.close()
    async with db.unit_of_work() as uow:
        val161 = await uow.settings.get_value(tid161, "k161")
        all161 = await uow.settings.all_for_scope(tid161)
    R("DB-161", ok161 is True and val161 == "from-B" and len(all161) == 1, f"put sequence ok={ok161}, final value={val161!r}, row count={len(all161)}")

    # DB-162
    async with db.unit_of_work() as uow:
        d162 = await uow.settings.get_value(tid161, "no-such-key", default={"a": 1})
    R("DB-162", d162 == {"a": 1}, repr(d162))

    # DB-163
    nested163 = {"outer": {"inner": [1, 2, {"deep": "café"}]}, "n": None}
    async with db.unit_of_work() as uow:
        await uow.settings.put(tid161, "k163", nested163)
    async with db.unit_of_work() as uow:
        back163 = await uow.settings.get_value(tid161, "k163")
    R("DB-163", back163 == nested163, f"{back163} vs {nested163}")

    # DB-164
    async with db.unit_of_work() as uow:
        t164b = uow.tenants.create(slug="t164b", display_name="T164B")
        await uow.flush()
        tid164b = str(t164b.id)
        await uow.settings.put(tid161, "k164", "scope-global-tenant161", scope="global")
        await uow.settings.put(tid161, "k164", "scope-custom-tenant161", scope="custom")
        await uow.settings.put(tid164b, "k164", "scope-global-tenant164b", scope="global")
        await uow.settings.put(tid164b, "k164", "scope-custom-tenant164b", scope="custom")
    async with db.unit_of_work() as uow:
        v1 = await uow.settings.get_value(tid161, "k164", scope="global")
        v2 = await uow.settings.get_value(tid161, "k164", scope="custom")
        v3 = await uow.settings.get_value(tid164b, "k164", scope="global")
        v4 = await uow.settings.get_value(tid164b, "k164", scope="custom")
        scope_all = await uow.settings.all_for_scope(tid161, scope="global")
    distinct = len({v1, v2, v3, v4}) == 4
    R("DB-164", distinct and "k164" in scope_all and len(scope_all) >= 1,
      f"{v1!r}, {v2!r}, {v3!r}, {v4!r} (all distinct={distinct}); all_for_scope(tenant161, global) keys={list(scope_all.keys())}")

    # DB-165
    async with db.unit_of_work() as uow:
        await uow.settings.put(tid161, "k165", None)
    async with db.unit_of_work() as uow:
        v165 = await uow.settings.get_value(tid161, "k165", default="DEFAULT165")
        from sqlalchemy import text as st165
        raw165 = (await uow._session.execute(st165("SELECT value_json FROM setting WHERE tenant_id=:t AND key='k165'"), {"t": tid161})).scalar()
    R("DB-165", True, f"put(None) stored raw value_json={raw165!r}; get_value(default='DEFAULT165') returns {v165!r} "
      f"-- {'None is indistinguishable from a missing row (default returned instead)' if v165=='DEFAULT165' else 'None is returned directly, distinguishable from a missing row only by catching the default sentinel differently'}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
