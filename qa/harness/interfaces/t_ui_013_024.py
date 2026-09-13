import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    # UI-013: single-tenant fallback grants wildcard, only until sign-in
    DB13 = c.WORKDIR / "ui013.db"
    env13 = u.UiEnv(str(DB13), default_tenant_fallback=True)
    await env13.start()
    await env13.create_principal("auditor13", "auditorpassword1", ["auditor"])
    http_nosession = env13.client()
    r_fallback = await http_nosession.get("/estate")
    ok_fallback = r_fallback.status_code == 200
    http_signed, r_signin = await env13.signed_in_client("auditor13", "auditorpassword1")
    r_write_as_auditor = await http_signed.post("/controls/save", data={"pql": "x"})
    ok_bounded = r_write_as_auditor.status_code == 403
    ok13 = ok_fallback and ok_bounded
    record("UI-013", "PASS" if ok13 else "FAIL", f"unauthenticated_fallback_status={r_fallback.status_code} signed_in_auditor_write_status={r_write_as_auditor.status_code}")
    await http_nosession.aclose()
    await http_signed.aclose()
    await env13.stop()

    # UI-014: no default tenant, no session -> every page redirects to sign-in (the hardened setup)
    DB14 = c.WORKDIR / "ui014.db"
    env14 = u.UiEnv(str(DB14), default_tenant_fallback=False)
    await env14.start()
    http14 = env14.client()
    paths_to_check = ["/estate", "/controls", "/incidents", "/proposals", "/scorecards", "/evidence", "/reconciliation"]
    bad14 = {}
    for p in paths_to_check:
        r = await http14.get(p)
        if not (r.status_code == 303 and r.headers.get("location") == "/sign-in"):
            bad14[p] = (r.status_code, r.headers.get("location"))
    record("UI-014", "PASS" if not bad14 else "FAIL", f"checked={len(paths_to_check)} bad={bad14}")
    await http14.aclose()
    await env14.stop()

    # UI-015: a disabled principal's existing session stops working
    DB15 = c.WORKDIR / "ui015.db"
    env15 = u.UiEnv(str(DB15))
    await env15.start()
    pid15 = await env15.create_principal("todisable15", "disablepassword1", ["owner"])
    http15, r15 = await env15.signed_in_client("todisable15", "disablepassword1")
    r15a = await http15.get("/estate")
    async with env15.database.unit_of_work() as uow:
        principal = await uow.principals.get(pid15)
        principal.status = "disabled"
        await uow.flush()
    r15b = await http15.get("/estate")
    ok15 = r15a.status_code == 200 and r15b.status_code == 303 and r15b.headers.get("location") == "/sign-in"
    record("UI-015", "PASS" if ok15 else "FAIL", f"before={r15a.status_code} after_disable={r15b.status_code} loc={r15b.headers.get('location')}")
    await http15.aclose()
    await env15.stop()

    # UI-016: a deleted principal's session stops working
    DB16 = c.WORKDIR / "ui016.db"
    env16 = u.UiEnv(str(DB16))
    await env16.start()
    pid16 = await env16.create_principal("todelete16", "deletepassword1", ["owner"])
    http16, r16 = await env16.signed_in_client("todelete16", "deletepassword1")
    r16a = await http16.get("/estate")
    import sqlite3
    conn = sqlite3.connect(str(DB16))
    conn.execute("DELETE FROM principal WHERE id = ?", (pid16,))
    conn.commit()
    conn.close()
    r16b = await http16.get("/estate")
    ok16 = r16a.status_code == 200 and r16b.status_code == 303 and r16b.headers.get("location") == "/sign-in"
    record("UI-016", "PASS" if ok16 else "FAIL", f"before={r16a.status_code} after_delete={r16b.status_code}")
    await http16.aclose()
    await env16.stop()

    # UI-017: a role removed mid-session is enforced next request
    DB17 = c.WORKDIR / "ui017.db"
    env17 = u.UiEnv(str(DB17))
    await env17.start()
    # catalogue Steps says "reload a page needing declaration:write" -- /controls/save needs
    # control:propose since the UI-005/008/009 scope fix (owner never held that, even before
    # revocation), so it no longer exercises what this case is about; /declarations/new (owner
    # DOES hold declaration:write, via declaration:*) is the route the catalogue actually means.
    pid17 = await env17.create_principal("ownerrole17", "ownerpassword123", ["owner"])
    http17, r17 = await env17.signed_in_client("ownerrole17", "ownerpassword123")
    r17a = await http17.post("/declarations/new", data={"name": "ui017-ds", "shape": "unbound", "criticality": "4"})
    async with env17.database.unit_of_work() as uow:
        principal = await uow.principals.get(pid17)
        for role in list(principal.roles):
            await uow.roles.revoke(pid17, str(role.id))
        await uow.flush()
    r17b = await http17.post("/declarations/new", data={"name": "ui017-ds2", "shape": "unbound", "criticality": "4"})
    ok17 = r17a.status_code in (200, 302, 303, 400, 422) and r17b.status_code in (303, 403)
    record("UI-017", "PASS" if ok17 else "FAIL", f"before_revoke={r17a.status_code} after_revoke={r17b.status_code}")
    await http17.aclose()
    await env17.stop()

    # UI-019: a session with no issued_at is refused
    DB19 = c.WORKDIR / "ui019.db"
    env19 = u.UiEnv(str(DB19))
    await env19.start()
    await env19.create_principal("alice19", "alicepassword19", ["owner"])
    http19, r19 = await env19.signed_in_client("alice19", "alicepassword19")
    # tamper the session: remove issued_at, re-sign with the real key via the app's own signer is hard
    # from outside; instead directly manipulate the session cookie's payload using itsdangerous with the
    # SAME secret (simulating an older build's cookie which never set issued_at).
    import itsdangerous, json as _json, base64
    secret = env19.config.raw()["security"]["session_secret"]
    signer = itsdangerous.TimestampSigner(secret, salt="starlette.sessions")
    raw_cookie = http19.cookies.get("prama_session")
    payload_b64 = raw_cookie.split(".")[0]
    payload_bytes = itsdangerous.base64_decode(payload_b64)
    payload = _json.loads(payload_bytes)
    del payload["issued_at"]
    new_b64 = itsdangerous.base64_encode(_json.dumps(payload).encode())
    new_cookie = signer.sign(new_b64).decode()
    http19.cookies.set("prama_session", new_cookie)
    r19b = await http19.get("/estate")
    ok19 = r19b.status_code == 303 and r19b.headers.get("location") == "/sign-in"
    record("UI-019", "PASS" if ok19 else "FAIL", f"status={r19b.status_code} location={r19b.headers.get('location')}")
    await http19.aclose()
    await env19.stop()

    # UI-024: sign-out is POST-only, GET does not sign out
    DB24 = c.WORKDIR / "ui024.db"
    env24 = u.UiEnv(str(DB24))
    await env24.start()
    await env24.create_principal("alice24", "alicepassword24", ["owner"])
    http24, r24 = await env24.signed_in_client("alice24", "alicepassword24")
    r24_get = await http24.get("/sign-out")
    r24_after = await http24.get("/estate")
    ok24 = r24_get.status_code == 405 and r24_after.status_code == 200
    record("UI-024", "PASS" if ok24 else "FAIL", f"get_signout_status={r24_get.status_code} still_signed_in_after={r24_after.status_code}")
    await http24.aclose()
    await env24.stop()

    print("done ui batch 1b")


asyncio.run(main())
