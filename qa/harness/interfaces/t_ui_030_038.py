import sys, os, json, asyncio, re
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


def strip_dynamic(text):
    # remove correlation ids / timestamps / csrf-ish tokens if any so byte comparison is
    # meaningful. Also strip the per-response CSP nonce (UI-045's fix): every response now
    # carries a fresh nonce="..." on each <script>, which legitimately differs response to
    # response and is not itself a distinguishing signal between a real account and a fake one.
    text = re.sub(r"\b[0-9A-Z]{20,30}\b", "<ID>", text)
    text = re.sub(r'nonce="[^"]*"', 'nonce="<NONCE>"', text)
    return text


async def main():
    DB = c.WORKDIR / "ui030.db"
    env = u.UiEnv(str(DB))
    await env.start()
    await env.create_principal("existing30", "existingpassword1", ["owner"])
    await env.create_principal("disabled30", "disabledpassword1", ["owner"])
    # a SECOND real tenant -- round 2 found that a nonexistent tenant slug falls into
    # _sign_in_tenant's documented single-estate fallback (an unresolvable tenant is ignored
    # when there is exactly one estate), turning "right password, wrong tenant" into a 303
    # success instead of the refusal this case is about. A second genuine estate removes the
    # fallback and exercises the actual wrong-tenant check.
    async with env.database.unit_of_work() as uow:
        other_tenant30 = uow.tenants.create(slug="rival-30", display_name="Rival 30")
        await uow.flush()
        other_tenant30_id = str(other_tenant30.id)
    async with env.database.unit_of_work() as uow:
        p = await uow.principals.by_username(env.tenant_id, "disabled30")
        p.status = "disabled"
        await uow.flush()
    # a principal with NO password: create via DAO directly without set_password
    async with env.database.unit_of_work() as uow:
        nopass = uow.principals.create(tenant_id=env.tenant_id, username="nopass30", display_name="nopass30")
        await uow.flush()

    # UI-030: every failure gives byte-identical responses (apart from username, status 401 every time)
    cases = {
        "wrong-password-existing": {"username": "existing30", "password": "wrongpassword1"},
        "wrong-password-disabled": {"username": "disabled30", "password": "wrongpassword1"},
        "no-password-set": {"username": "nopass30", "password": "anything123"},
        "unknown-username": {"username": "totallymadeup30", "password": "anything123"},
        "right-password-wrong-tenant": {"username": "existing30", "password": "existingpassword1", "tenant": "rival-30"},
    }
    bodies = {}
    statuses = {}
    for label, data in cases.items():
        http = env.client()
        r = await http.post("/sign-in", data=data)
        statuses[label] = r.status_code
        body = r.text.replace(data["username"], "<USER>")
        bodies[label] = strip_dynamic(body)
        await http.aclose()
    unique_bodies = set(bodies.values())
    all_401 = all(s == 401 for s in statuses.values())
    ok30 = all_401 and len(unique_bodies) == 1
    record(
        "UI-030",
        "PASS" if ok30 else "FAIL",
        f"statuses={statuses} n_distinct_bodies={len(unique_bodies)} " + (f"bodies_differ_sample={list(bodies.items())[:2]}" if len(unique_bodies) > 1 else ""),
    )

    # UI-031: refusal echoes username, never password
    http31 = env.client()
    r31 = await http31.post("/sign-in", data={"username": "existing30", "password": "s3cr3t-should-not-appear"})
    ok31 = "existing30" in r31.text and "s3cr3t-should-not-appear" not in r31.text
    record("UI-031", "PASS" if ok31 else "FAIL", f"username_present={'existing30' in r31.text} password_leaked={'s3cr3t-should-not-appear' in r31.text}")
    await http31.aclose()

    # UI-032: HTML in username is escaped
    http32 = env.client()
    r32 = await http32.post("/sign-in", data={"username": "<script>alert(1)</script>", "password": "x"})
    ok32 = "<script>alert(1)</script>" not in r32.text and ("&lt;script&gt;" in r32.text or "&lt;script&gt;alert(1)&lt;/script&gt;" in r32.text)
    record("UI-032", "PASS" if ok32 else "FAIL", f"raw_script_tag_present={'<script>alert(1)</script>' in r32.text} escaped_present={'&lt;script&gt;' in r32.text}")
    await http32.aclose()

    # UI-033: session id changes on sign-in
    http33 = env.client()
    r_pre = await http33.get("/sign-in")
    pre_cookie = http33.cookies.get("prama_session")
    # explicit tenant: UI-030's fix above added a second real tenant, so the single-estate
    # fallback that used to resolve an omitted tenant no longer applies here.
    r33 = await http33.post("/sign-in", data={"username": "existing30", "password": "existingpassword1", "tenant": "acme-bank"})
    post_cookie = http33.cookies.get("prama_session")
    ok33 = pre_cookie != post_cookie
    record("UI-033", "PASS" if ok33 else "FAIL", f"pre_cookie_present={pre_cookie is not None} changed={ok33}")
    await http33.aclose()

    # UI-034: next= accepts only a path on this site
    targets = {
        "/estate": True,
        "https://evil.example": False,
        "//evil.example": False,
        "/\\evil.example": False,
        "/%09/evil.example": False,  # tab-prefixed
        "%5C%5Cevil.example": False,
        "/tab\tnewline\nCR\r": None,  # ambiguous, just must not be an absolute external target
    }
    res34 = {}
    for target, _ in targets.items():
        http = env.client()
        if target == "/%09/evil.example":
            # httpx's params= double-percent-encodes the literal '%', so the server would only
            # ever see the LITERAL text '%09' rather than a decoded tab -- round 2's fix embeds
            # the query string directly in the URL (single decode) instead, matching what a
            # real browser sends.
            r = await http.get("/sign-in?next=/%09/evil.example")
        else:
            r = await http.get("/sign-in", params={"next": target})
        m = re.search(r'name="next" value="([^"]*)"', r.text)
        res34[target] = m.group(1) if m else None
        await http.aclose()
    bad34 = {}
    for target, expect_ok in targets.items():
        got = res34[target]
        if target == "/estate":
            if got != "/estate":
                bad34[target] = got
        else:
            if got and (got.startswith("http") or got.startswith("//") or "evil" in (got or "")):
                bad34[target] = got
    record("UI-034", "PASS" if not bad34 else "FAIL", f"results={res34} bad={bad34}")

    # UI-035: double-encoded backslash
    http35 = env.client()
    r35 = await http35.get("/sign-in", params={"next": "%255Cevil.example"})
    m35 = re.search(r'name="next" value="([^"]*)"', r35.text)
    got35 = m35.group(1) if m35 else None
    ok35 = not (got35 and ("evil" in got35 and (got35.startswith("http") or got35.startswith("//"))))
    record("UI-035", "PASS" if ok35 else "FAIL", f"next_value_rendered={got35!r}")
    await http35.aclose()

    # UI-036: next= to another console path round-trips through the unauthenticated redirect
    http36 = env.client()
    r36a = await http36.get("/controls")  # unauthenticated
    ok_redirect_has_next = "next=" in (r36a.headers.get("location") or "")
    location36 = r36a.headers.get("location")
    if location36 and location36.startswith("/sign-in"):
        r36b = await http36.get(location36)
    else:
        r36b = await http36.get("/sign-in")
    r36c = await http36.post("/sign-in", data={"username": "existing30", "password": "existingpassword1", "next": "/controls", "tenant": "acme-bank"})
    landed_on_controls = r36c.headers.get("location") == "/controls"
    record(
        "UI-036",
        "PASS" if (ok_redirect_has_next and landed_on_controls) else "FAIL",
        f"unauth_redirect_location={location36!r} redirect_carries_next={ok_redirect_has_next} "
        f"after_signin_with_explicit_next=/controls_lands_on={r36c.headers.get('location')}",
    )
    await http36.aclose()

    await env.stop()
    print("done ui batch 2b")


asyncio.run(main())
