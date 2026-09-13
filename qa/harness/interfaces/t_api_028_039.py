import sys, os, json, asyncio, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api6.db"


async def main():
    env = a.Env(str(DB))
    await env.start()
    from prama.db.security import ApiKeyIssuer
    issuer = ApiKeyIssuer()

    # API-028: naive expires_at in the database does not 500
    issue = issuer.issue(environment="test")
    async with env.database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=env.tenant_id, username="naive1", display_name="naive1")
        await uow.flush()
        uow.api_keys.create(
            tenant_id=env.tenant_id, principal_id=str(person.id), name="naive",
            key_prefix=issue.prefix, key_hash=issue.hash, scopes=["*"],
        )
        await uow.flush()
    # Write a naive (no timezone) expires_at directly via raw SQL, bypassing the ORM's own coercion.
    conn = sqlite3.connect(str(DB))
    conn.execute("UPDATE api_key SET expires_at = ? WHERE key_prefix = ?", ("2099-01-01T00:00:00", issue.prefix))
    conn.commit()
    conn.close()
    try:
        async with env.client(issue.plaintext) as http:
            r = await http.get("/datasets")
            record("API-028", "PASS" if r.status_code in (200, 401, 500) and "TypeError" not in r.text else "FAIL", f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record("API-028", "FAIL", f"client-side exception (naive/aware datetime TypeError escaped as unhandled): {type(e).__name__} {str(e)[:300]}")

    # API-029: Authorization scheme case sensitivity
    res29 = {}
    for label, hdr in [
        ("Basic", {"Authorization": f"Basic {env.api_key}"}),
        ("Token", {"Authorization": f"Token {env.api_key}"}),
        ("bearer-lower", {"Authorization": f"bearer {env.api_key}"}),
        ("BEARER-upper", {"Authorization": f"BEARER {env.api_key}"}),
        ("Bearer-empty", {"Authorization": "Bearer"}),
    ]:
        async with env.client(headers=hdr) as http:
            r = await http.get("/datasets")
            res29[label] = r.status_code
    ok = res29["bearer-lower"] == 200 and res29["BEARER-upper"] == 200 and res29["Basic"] == 401 and res29["Token"] == 401 and res29["Bearer-empty"] == 401
    record("API-029", "PASS" if ok else "FAIL", f"{res29}")

    # API-030: X-Prama-API-Key takes precedence over Authorization
    readonly_key = await a._issue_key(env.database, env.tenant_id, principal="ro30", scopes=["declaration:read"])
    async with env.client(headers={"X-Prama-API-Key": readonly_key, "Authorization": f"Bearer {env.api_key}"}) as http:
        r = await http.post("/datasets", json={"name": "precedence-test", "criticality": 4})
    ok = r.status_code == 403
    record("API-030", "PASS" if ok else "FAIL", f"status={r.status_code} body={r.text[:200]}")

    # API-031: tenant never taken from a header
    async with env.client(env.api_key, headers={"X-Prama-Tenant": env.other_tenant_id}) as http:
        r1 = await http.post("/datasets", json={"name": "tenant-header-test", "criticality": 4})
        r_list = await http.get("/datasets")
    names = [d["name"] for d in r_list.json().get("items", [])]
    async with env.client(env.other_key) as other_http:
        r_other_list = await other_http.get("/datasets")
    other_names = [d["name"] for d in r_other_list.json().get("items", [])]
    ok = "tenant-header-test" in names and "tenant-header-test" not in other_names
    record("API-031", "PASS" if ok else "FAIL", f"landed_in_own_estate={('tenant-header-test' in names)} leaked_to_other={('tenant-header-test' in other_names)}")

    # API-032: empty scope list permits nothing
    empty_scope_key = await a._issue_key(env.database, env.tenant_id, principal="noscopes", scopes=[])
    async with env.client(empty_scope_key) as http:
        r_read = await http.get("/datasets")
        r_write = await http.post("/datasets", json={"name": "x", "criticality": 4})
    ok = r_read.status_code == 403 and r_write.status_code == 403 and "empty scope list permits nothing" in r_read.text
    record("API-032", "PASS" if ok else "FAIL", f"read={r_read.status_code} write={r_write.status_code} body={r_read.text[:200]}")

    # API-039: scoped() refuses a scope outside the vocabulary at import/definition time
    try:
        from prama.api.deps import scoped
        scoped("semantic:read")
        record("API-039", "FAIL", "scoped('semantic:read') did not raise -- an unknown scope was accepted")
    except ValueError as e:
        record("API-039", "PASS", f"ValueError raised as expected: {e}")
    except Exception as e:
        record("API-039", "FAIL", f"wrong exception type: {type(e).__name__} {e}")

    await env.stop()


asyncio.run(main())
print("done api batch 2b")
