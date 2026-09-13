import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    DB = c.WORKDIR / "uibulk4.db"
    env = u.UiEnv(str(DB))
    await env.start()
    async with env.database.unit_of_work() as uow:
        t2 = uow.tenants.create(slug="rival-bank-att", display_name="Rival")
        await uow.flush()
        tenant_b = str(t2.id)
    await env.create_principal("owner118", "ownerpassword1", ["owner"])
    await env.create_principal("ownerB118", "ownerBpassword1", ["owner"], tenant_id=tenant_b)
    http, _ = await env.signed_in_client("owner118", "ownerpassword1")
    httpB, _ = await env.signed_in_client("ownerB118", "ownerBpassword1", tenant_slug="rival-bank-att")

    # UI-118: the attestation form shows the draft before signing
    r_form = await http.get("/attestations/new")
    ok118 = r_form.status_code == 200
    record("UI-118", "PASS" if ok118 else "FAIL", f"status={r_form.status_code}")

    # UI-120: needs a named person and a statement
    res120 = {}
    for label, data in [
        ("empty-name", {"attester_name": "", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"}),
        ("empty-statement", {"attester_name": "alice", "statement": "", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"}),
        ("whitespace-name", {"attester_name": "   ", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"}),
    ]:
        try:
            r = await http.post("/attestations/new", data=data)
            res120[label] = (r.status_code, "team" in r.text.lower() if r.status_code != 303 else None)
        except Exception as e:
            res120[label] = (f"EXCEPTION {type(e).__name__}", str(e)[:150])
    bad120 = {k: v for k, v in res120.items() if isinstance(v[0], int) and v[0] == 303}
    record("UI-120", "PASS" if not bad120 else "FAIL", f"results={res120}")

    # UI-121: period_start after period_end, and unparsable dates
    res121 = {}
    for label, ps, pe in [("reversed", "2026-02-01", "2026-01-01"), ("unparsable", "banana", "2026-01-31")]:
        try:
            r = await http.post("/attestations/new", data={"attester_name": "alice", "statement": "s", "scope": "estate", "period_start": ps, "period_end": pe})
            res121[label] = r.status_code
        except Exception as e:
            res121[label] = f"EXCEPTION {type(e).__name__}: {str(e)[:150]}"
    bad121 = {k: v for k, v in res121.items() if v == 303}
    record("UI-121", "PASS" if not bad121 else "FAIL", f"results={res121}")

    # first, a real successful attestation in estate B, to use as a supersedes target
    r_b_att = await httpB.post("/attestations/new", data={"attester_name": "bob", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"})
    import sqlite3
    conn = sqlite3.connect(str(DB))
    row = conn.execute("SELECT id FROM att_attestation WHERE tenant_id=? ORDER BY signed_at DESC LIMIT 1", (tenant_b,)).fetchone()
    conn.close()
    att_b_id = row[0] if row else None

    # UI-122: supersedes naming another estate's attestation
    if att_b_id:
        try:
            r122 = await http.post("/attestations/new", data={"attester_name": "alice", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31", "supersedes": att_b_id, "supersedes_because": "test"})
            ok122 = r122.status_code != 303
            detail122 = f"status={r122.status_code}"
        except Exception as e:
            ok122 = False
            detail122 = f"exception: {type(e).__name__} {str(e)[:200]}"
        record("UI-122", "PASS" if ok122 else "FAIL", f"{detail122} -- posting estate B's attestation id as 'supersedes' from estate A's session")
    else:
        record("UI-122", "BLOCKED", "could not create estate B's attestation to use as a target")

    # UI-123: superseding requires a reason
    r_a_att = await http.post("/attestations/new", data={"attester_name": "alice", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"})
    conn = sqlite3.connect(str(DB))
    row_a = conn.execute("SELECT id FROM att_attestation WHERE tenant_id=? ORDER BY signed_at DESC LIMIT 1", (env.tenant_id,)).fetchone()
    conn.close()
    att_a_id = row_a[0] if row_a else None
    if att_a_id:
        r123 = await http.post("/attestations/new", data={"attester_name": "alice", "statement": "s2", "scope": "estate", "period_start": "2026-02-01", "period_end": "2026-02-28", "supersedes": att_a_id, "supersedes_because": ""})
        ok123 = r123.status_code != 303
        record("UI-123", "PASS" if ok123 else "FAIL", f"status={r123.status_code}")
    else:
        record("UI-123", "BLOCKED", "no attestation id available to supersede")

    # UI-124: the attestation seal wording about the session-secret key
    r_form2 = await http.get("/attestations/new")
    mentions_session_secret = "session secret" in r_form2.text.lower() or "key management" in r_form2.text.lower()
    record("UI-124", "PASS" if mentions_session_secret else "FAIL", f"draft_page_mentions_key_nature={mentions_session_secret}")

    # UI-125: /attestations/{id}/pack for another estate's id
    if att_b_id:
        r125 = await http.get(f"/attestations/{att_b_id}/pack")
        ok125 = r125.status_code == 404
        record("UI-125", "PASS" if ok125 else "FAIL", f"status={r125.status_code}")
    else:
        record("UI-125", "BLOCKED", "no estate B attestation id available")

    await env.stop()
    print("done ui bulk batch 4")


asyncio.run(main())
