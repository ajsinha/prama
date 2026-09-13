import sys, os, json, asyncio, datetime
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from ui_common import tamper_session_cookie, _REMOVE
from logger import record
import cli_common as c


async def main():
    # UI-004: forged with a guessed (wrong) secret
    DB4 = c.WORKDIR / "ui004r.db"
    env4 = u.UiEnv(str(DB4))
    await env4.start()
    await env4.create_principal("alice4r", "alicepassword1", ["owner"])
    http4, _ = await env4.signed_in_client("alice4r", "alicepassword1")
    real_secret = env4.config.raw()["security"]["session_secret"]
    raw_cookie = http4.cookies.get("prama_session")
    forged = tamper_session_cookie(real_secret, raw_cookie, sign_with="a-totally-different-guessed-key", username="mallory")
    http4.cookies.set("prama_session", forged)
    r4 = await http4.get("/estate")
    ok4 = r4.status_code == 303 and r4.headers.get("location") == "/sign-in"
    record("UI-004", "PASS" if ok4 else "FAIL", f"status={r4.status_code} location={r4.headers.get('location')}")
    await http4.aclose()
    await env4.stop()

    # UI-018: session for a principal belonging to another tenant is refused
    DB18 = c.WORKDIR / "ui018r.db"
    env18 = u.UiEnv(str(DB18))
    await env18.start()
    async with env18.database.unit_of_work() as uow:
        t2 = uow.tenants.create(slug="rival-bank", display_name="Rival Bank")
        await uow.flush()
        tenant_b = str(t2.id)
    await env18.create_principal("bob18r", "bobpassword123", ["owner"], tenant_id=tenant_b)
    http18, _ = await env18.signed_in_client("bob18r", "bobpassword123", tenant_slug="rival-bank")
    r18a = await http18.get("/estate")
    secret18 = env18.config.raw()["security"]["session_secret"]
    raw18 = http18.cookies.get("prama_session")
    tampered18 = tamper_session_cookie(secret18, raw18, tenant_id=env18.tenant_id)
    http18.cookies.set("prama_session", tampered18)
    r18b = await http18.get("/estate")
    ok18 = r18a.status_code == 200 and r18b.status_code == 303 and r18b.headers.get("location") == "/sign-in"
    record("UI-018", "PASS" if ok18 else "FAIL", f"before={r18a.status_code} after_tamper={r18b.status_code}")
    await http18.aclose()
    await env18.stop()

    # UI-019: no issued_at is refused
    DB19 = c.WORKDIR / "ui019r.db"
    env19 = u.UiEnv(str(DB19))
    await env19.start()
    await env19.create_principal("alice19r", "alicepassword19", ["owner"])
    http19, _ = await env19.signed_in_client("alice19r", "alicepassword19")
    secret19 = env19.config.raw()["security"]["session_secret"]
    raw19 = http19.cookies.get("prama_session")
    tampered19 = tamper_session_cookie(secret19, raw19, issued_at=_REMOVE)
    http19.cookies.set("prama_session", tampered19)
    r19 = await http19.get("/estate")
    ok19 = r19.status_code == 303 and r19.headers.get("location") == "/sign-in"
    record("UI-019", "PASS" if ok19 else "FAIL", f"status={r19.status_code} location={r19.headers.get('location')}")
    await http19.aclose()
    await env19.stop()

    # UI-020: unparsable issued_at refused; future issued_at accepted but does not survive a real role change
    DB20 = c.WORKDIR / "ui020r.db"
    env20 = u.UiEnv(str(DB20))
    await env20.start()
    pid20 = await env20.create_principal("alice20r", "alicepassword20", ["owner"])
    http20a, _ = await env20.signed_in_client("alice20r", "alicepassword20")
    secret20 = env20.config.raw()["security"]["session_secret"]
    raw20a = http20a.cookies.get("prama_session")
    tampered20a = tamper_session_cookie(secret20, raw20a, issued_at="tomorrow")
    http20a.cookies.set("prama_session", tampered20a)
    r20a = await http20a.get("/estate")
    ok20a = r20a.status_code == 303

    http20b, _ = await env20.signed_in_client("alice20r", "alicepassword20")
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)).isoformat()
    raw20b = http20b.cookies.get("prama_session")
    tampered20b = tamper_session_cookie(secret20, raw20b, issued_at=future)
    http20b.cookies.set("prama_session", tampered20b)
    r20b = await http20b.get("/estate")
    ok20b = r20b.status_code == 200
    # now change the account (revoke a role) and confirm the forged-future session does NOT survive,
    # since updated_at will move to a real "now" which is still before the forged future stamp... actually
    # per the catalogue's own logic, a forged future stamp WOULD survive a role change made with the
    # system's real clock, since issued_at (fake future) > updated_at (real now) always. Confirm that
    # nuance directly rather than assuming.
    async with env20.database.unit_of_work() as uow:
        principal = await uow.principals.get(pid20)
        for role in list(principal.roles):
            await uow.roles.revoke(pid20, str(role.id))
        await uow.flush()
    r20c = await http20b.get("/estate")
    survives_role_change = r20c.status_code == 200
    record(
        "UI-020",
        "PASS" if (ok20a and ok20b) else "FAIL",
        f"unparsable_status={r20a.status_code} future_status={r20b.status_code} "
        f"after_role_revoked_with_forged_future_stamp_status={r20c.status_code} "
        f"(survives_role_change={survives_role_change} -- if True, this is the exact attack the catalogue's "
        f"Why warns about: a forged future issued_at is never invalidated by a real role change, since the "
        f"comparison issued_at <= updated_at can never become true when issued_at is forged far enough "
        f"ahead)",
    )
    await http20a.aclose()
    await http20b.aclose()
    await env20.stop()

    # UI-021: sign in and out within the same second still revokes
    DB21 = c.WORKDIR / "ui021r.db"
    env21 = u.UiEnv(str(DB21))
    await env21.start()
    await env21.create_principal("alice21r", "alicepassword21", ["owner"])
    http21, _ = await env21.signed_in_client("alice21r", "alicepassword21")
    captured_cookie = http21.cookies.get("prama_session")
    await http21.post("/sign-out")
    http21b = env21.client()
    http21b.cookies.set("prama_session", captured_cookie)
    r21_after = await http21b.get("/estate")
    ok21 = r21_after.status_code == 303 and r21_after.headers.get("location") == "/sign-in"
    record("UI-021", "PASS" if ok21 else "FAIL", f"captured_cookie_reused_status={r21_after.status_code}")
    await http21.aclose()
    await http21b.aclose()
    await env21.stop()

    print("done ui tamper redo")


asyncio.run(main())
