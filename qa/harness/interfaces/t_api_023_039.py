import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(__file__))
import api_common as a
from logger import record
import cli_common as c

DB = c.WORKDIR / "api5.db"


async def main():
    env = a.Env(str(DB))
    await env.start()

    # API-023: no credential -> 401 naming both header forms + prama apikey create
    async with env.client() as anon:
        r = await anon.get("/datasets")
        body = r.json()
        text = json.dumps(body)
        ok = r.status_code == 401 and "Authorization: Bearer" in text and "X-Prama-API-Key" in text and "prama apikey create" in text
        record("API-023", "PASS" if ok else "FAIL", f"status={r.status_code} body={body}")

    # API-024: the remedy works verbatim (already effectively proven by env.api_key working); confirm explicitly
    async with env.client(env.api_key) as http:
        r = await http.get("/datasets")
        ok = r.status_code == 200
        record("API-024", "PASS" if ok else "FAIL", f"status={r.status_code} -- a key issued the way the 401 remedy describes (prama apikey create) authenticates successfully")

    # API-025: unknown, revoked, expired keys indistinguishable
    revoked_key = await a._issue_key(env.database, env.tenant_id, principal="rev1")
    from prama.db.security import ApiKeyIssuer
    issuer = ApiKeyIssuer()
    async with env.database.unit_of_work() as uow:
        rec = await uow.api_keys.by_prefix(issuer.prefix_of(revoked_key))
        rec.revoked_at = __import__("prama.core.clock", fromlist=["utc_now"]).utc_now()
        await uow.flush()

    expiring_issue = issuer.issue(environment="test")
    async with env.database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=env.tenant_id, username="exp1", display_name="exp1")
        await uow.flush()
        uow.api_keys.create(
            tenant_id=env.tenant_id, principal_id=str(person.id), name="expired",
            key_prefix=expiring_issue.prefix, key_hash=expiring_issue.hash, scopes=["*"],
            expires_at=__import__("prama.core.clock", fromlist=["utc_now"]).utc_now(),
        )
        await uow.flush()
    expired_key = expiring_issue.plaintext

    invented_key = "pk_live_" + "z" * 30

    bodies = {}
    for label, key in [("revoked", revoked_key), ("expired", expired_key), ("invented", invented_key)]:
        async with env.client(key) as http:
            r = await http.get("/datasets")
            b = dict(r.json())
            b.pop("correlation_id", None)
            b.pop("instance", None)
            bodies[label] = (r.status_code, b)
    unique_bodies = {json.dumps(v, sort_keys=True) for v in bodies.values()}
    ok = len(unique_bodies) == 1
    record("API-025", "PASS" if ok else "FAIL", f"bodies={bodies}")

    # API-026: key expiring during a session
    issue2 = issuer.issue(environment="test")
    from prama.core.clock import utc_now
    import datetime
    async with env.database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=env.tenant_id, username="soonexp", display_name="soonexp")
        await uow.flush()
        uow.api_keys.create(
            tenant_id=env.tenant_id, principal_id=str(person.id), name="soon",
            key_prefix=issue2.prefix, key_hash=issue2.hash, scopes=["*"],
            expires_at=utc_now() + datetime.timedelta(seconds=2),
        )
        await uow.flush()
    soon_key = issue2.plaintext
    async with env.client(soon_key) as http:
        r1 = await http.get("/datasets")
        time.sleep(2.5)
        r2 = await http.get("/datasets")
    ok = r1.status_code == 200 and r2.status_code == 401
    record("API-026", "PASS" if ok else "FAIL", f"before={r1.status_code} after={r2.status_code}")

    # API-027: expires_at exactly now
    issue3 = issuer.issue(environment="test")
    async with env.database.unit_of_work() as uow:
        person = uow.principals.create(tenant_id=env.tenant_id, username="rightnow", display_name="rightnow")
        await uow.flush()
        uow.api_keys.create(
            tenant_id=env.tenant_id, principal_id=str(person.id), name="rightnow",
            key_prefix=issue3.prefix, key_hash=issue3.hash, scopes=["*"],
            expires_at=utc_now(),
        )
        await uow.flush()
    async with env.client(issue3.plaintext) as http:
        r = await http.get("/datasets")
    ok = r.status_code == 401
    record("API-027", "PASS" if ok else "FAIL", f"status={r.status_code}")

    await env.stop()
    return {}


asyncio.run(main())
print("done api batch 2a")
