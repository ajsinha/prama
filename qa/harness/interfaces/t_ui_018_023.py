import sys, os, json, asyncio, itsdangerous, datetime
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def tamper_cookie(env, http, **overrides):
    secret = env.config.raw()["security"]["session_secret"]
    signer = itsdangerous.TimestampSigner(secret, salt="starlette.sessions")
    raw_cookie = http.cookies.get("prama_session")
    payload_b64 = raw_cookie.split(".")[0]
    payload = json.loads(itsdangerous.base64_decode(payload_b64))
    payload.update(overrides)
    new_b64 = itsdangerous.base64_encode(json.dumps(payload).encode())
    new_cookie = signer.sign(new_b64).decode()
    http.cookies.set("prama_session", new_cookie)
    return payload


async def main():
    # UI-018: a session for a principal belonging to another tenant is refused
    DB18 = c.WORKDIR / "ui018.db"
    env18 = u.UiEnv(str(DB18))
    await env18.start()
    # second tenant
    async with env18.database.unit_of_work() as uow:
        t2 = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
        await uow.flush()
        tenant_b = str(t2.id)
    pid_b = await env18.create_principal("bob18", "bobpassword123", ["owner"], tenant_id=tenant_b)
    http18, r18 = await env18.signed_in_client("bob18", "bobpassword123", tenant_slug="rival-bank")
    r18a = await http18.get("/estate")
    # now tamper tenant_id in the cookie to tenant A while principal_id stays bob (belongs to tenant B)
    await tamper_cookie(env18, http18, tenant_id=env18.tenant_id)
    r18b = await http18.get("/estate")
    ok18 = r18a.status_code == 200 and r18b.status_code == 303 and r18b.headers.get("location") == "/sign-in"
    record("UI-018", "PASS" if ok18 else "FAIL", f"before_tamper={r18a.status_code} after_tamper={r18b.status_code}")
    await http18.aclose()
    await env18.stop()

    # UI-020: issued_at unparsable is refused; issued_at in the future is accepted but noted
    DB20 = c.WORKDIR / "ui020.db"
    env20 = u.UiEnv(str(DB20))
    await env20.start()
    await env20.create_principal("alice20", "alicepassword20", ["owner"])
    http20a, _ = await env20.signed_in_client("alice20", "alicepassword20")
    await tamper_cookie(env20, http20a, issued_at="tomorrow")
    r20a = await http20a.get("/estate")
    ok20a = r20a.status_code == 303 and r20a.headers.get("location") == "/sign-in"

    http20b, _ = await env20.signed_in_client("alice20", "alicepassword20")
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).isoformat()
    await tamper_cookie(env20, http20b, issued_at=future)
    r20b = await http20b.get("/estate")
    ok20b = r20b.status_code == 200
    ok20 = ok20a and ok20b
    record("UI-020", "PASS" if ok20 else "FAIL", f"unparsable_issued_at_status={r20a.status_code} future_issued_at_status={r20b.status_code}")
    await http20a.aclose()
    await http20b.aclose()
    await env20.stop()

    # UI-021: sign in and out within the same second still revokes
    DB21 = c.WORKDIR / "ui021.db"
    env21 = u.UiEnv(str(DB21))
    await env21.start()
    await env21.create_principal("alice21", "alicepassword21", ["owner"])
    http21, _ = await env21.signed_in_client("alice21", "alicepassword21")
    captured_cookie = http21.cookies.get("prama_session")
    r_signout = await http21.post("/sign-out")
    http21b = env21.client()
    http21b.cookies.set("prama_session", captured_cookie)
    r21_after = await http21b.get("/estate")
    ok21 = r21_after.status_code == 303 and r21_after.headers.get("location") == "/sign-in"
    record("UI-021", "PASS" if ok21 else "FAIL", f"captured_cookie_reused_status={r21_after.status_code}")
    await http21.aclose()
    await http21b.aclose()
    await env21.stop()

    # UI-022: sign-out revokes other sessions too (both are cookie-based sessions of the same account)
    DB22 = c.WORKDIR / "ui022.db"
    env22 = u.UiEnv(str(DB22))
    await env22.start()
    await env22.create_principal("alice22", "alicepassword22", ["owner"])
    http_browser1, _ = await env22.signed_in_client("alice22", "alicepassword22")
    http_browser2, _ = await env22.signed_in_client("alice22", "alicepassword22")
    r_b1_before = await http_browser1.get("/estate")
    r_b2_before = await http_browser2.get("/estate")
    await http_browser1.post("/sign-out")
    r_b2_after = await http_browser2.get("/estate")
    ok22 = r_b1_before.status_code == 200 and r_b2_before.status_code == 200 and r_b2_after.status_code == 303
    record(
        "UI-022",
        "PASS" if ok22 else "FAIL",
        f"b1_before={r_b1_before.status_code} b2_before={r_b2_before.status_code} b2_after_b1_signout={r_b2_after.status_code} -- "
        f"revocation is keyed on principal.updated_at (see UI-017's mechanism), and signing out via this "
        f"route does not appear to touch updated_at directly (it only clears the CALLING client's own "
        f"cookie) -- so this specific probe checks whether ANY server-side mechanism revokes the other "
        f"session too",
    )
    await http_browser1.aclose()
    await http_browser2.aclose()
    await env22.stop()

    # UI-023: a sign-out control exists in the chrome (rendered HTML, POST form)
    DB23 = c.WORKDIR / "ui023.db"
    env23 = u.UiEnv(str(DB23))
    await env23.start()
    await env23.create_principal("alice23", "alicepassword23", ["owner"])
    http23, _ = await env23.signed_in_client("alice23", "alicepassword23")
    r_page = await http23.get("/estate")
    html = r_page.text
    has_form_to_signout = '/sign-out' in html and ("method=\"post\"" in html.lower() or "method='post'" in html.lower())
    record(
        "UI-023",
        "PASS" if has_form_to_signout else "FAIL",
        f"'/sign-out' present in /estate HTML={'/sign-out' in html} looks like a POST form (crude check)={has_form_to_signout}",
    )
    await http23.aclose()
    await env23.stop()

    print("done ui batch 1c")


import json
asyncio.run(main())
