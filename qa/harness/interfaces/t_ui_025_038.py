import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    # UI-025: single-estate install, correct password signs in with no tenant field
    DB25 = c.WORKDIR / "ui025.db"
    env25 = u.UiEnv(str(DB25))
    await env25.start()
    await env25.create_principal("alice25", "alicepassword25", ["owner"])
    http25 = env25.client()
    r25 = await http25.post("/sign-in", data={"username": "alice25", "password": "alicepassword25"})
    ok25 = r25.status_code == 303 and r25.headers.get("location") == "/estate"
    record("UI-025", "PASS" if ok25 else "FAIL", f"status={r25.status_code} location={r25.headers.get('location')}")
    await http25.aclose()
    await env25.stop()

    # UI-026/027: tenant slug and id both resolve, with two estates
    DB26 = c.WORKDIR / "ui026.db"
    env26 = u.UiEnv(str(DB26))
    await env26.start()
    async with env26.database.unit_of_work() as uow:
        t2 = uow.tenants.create(slug="rival-bank-26", display_name="Rival")
        await uow.flush()
    await env26.create_principal("alice26", "alicepassword26", ["owner"])
    http_slug = env26.client()
    r_slug = await http_slug.post("/sign-in", data={"username": "alice26", "password": "alicepassword26", "tenant": "acme-bank"})
    ok26 = r_slug.status_code == 303 and r_slug.headers.get("location") == "/estate"
    record("UI-026", "PASS" if ok26 else "FAIL", f"status={r_slug.status_code} location={r_slug.headers.get('location')}")
    await http_slug.aclose()

    http_id = env26.client()
    r_id = await http_id.post("/sign-in", data={"username": "alice26", "password": "alicepassword26", "tenant": env26.tenant_id})
    ok27 = r_id.status_code == 303 and r_id.headers.get("location") == "/estate"
    record("UI-027", "PASS" if ok27 else "FAIL", f"status={r_id.status_code} location={r_id.headers.get('location')}")
    await http_id.aclose()

    # UI-028: two estates, no default, no tenant field -- refused honestly (not "nobody created")
    http28 = env26.client()
    r28 = await http28.post("/sign-in", data={"username": "alice26", "password": "alicepassword26"})
    body28 = r28.text
    ok28 = r28.status_code == 401 and "Nobody has been created" not in body28 and "nobody has been created" not in body28.lower()
    record("UI-028", "PASS" if ok28 else "FAIL", f"status={r28.status_code} body_sample={body28[:200]!r}")
    await http28.aclose()
    await env26.stop()

    # UI-029: no estates at all
    DB29 = c.WORKDIR / "ui029.db"
    from prama.db import Database
    cfg29 = u.ui_config(DB29)
    db29 = Database.from_config(cfg29)
    db29.initialise(applied_by="qa")
    await db29.start()
    from prama.api import create_app
    app29 = create_app(cfg29, database=db29)
    import httpx
    from httpx import ASGITransport
    async with app29.router.lifespan_context(app29):
        async with httpx.AsyncClient(transport=ASGITransport(app=app29), base_url="http://testserver", follow_redirects=False) as http29:
            r29 = await http29.get("/sign-in")
            body29 = r29.text
            ok29 = r29.status_code == 200 and ("nobody has been created" in body29.lower()) and "prama tenant create" in body29
            record("UI-029", "PASS" if ok29 else "FAIL", f"status={r29.status_code} body_sample={body29[:300]!r}")
    await db29.stop()

    print("done ui batch 2a")


asyncio.run(main())
