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
    # NEW FINDING (this round): owner holds attestation:sign (BUILTIN_ROLES grants it
    # specifically so owner can attest) but NOT attestation:read, which every GET route under
    # AttestationRoutes needs (it has no WRITE_SCOPE override for reads, so GET falls back to
    # the class default "attestation:read"). auditor holds attestation:read but not
    # attestation:sign. No built-in role holds both, so nobody can view a draft, their own
    # signed attestation, or an attestation pack through the console -- not even the role
    # BUILTIN_ROLES built specifically to sign them. Confirmed directly:
    r_owner_probe = await http.get("/attestations/new")
    await env.create_principal("auditor118", "auditorpassword1", ["auditor"])
    http_auditor, _ = await env.signed_in_client("auditor118", "auditorpassword1")

    # UI-118: the attestation form shows the draft before signing. Catalogue precondition is
    # role-agnostic ("an estate with evidence"); tested with auditor (attestation:read) since
    # owner (attestation:sign only) cannot reach this GET route at all -- see the note above.
    r_form = await http_auditor.get("/attestations/new")
    ok118 = r_form.status_code == 200
    record(
        "UI-118",
        "PASS" if ok118 else "FAIL",
        f"status={r_form.status_code} (tested with auditor, who holds attestation:read) -- "
        f"separately, and NOT part of this case's verdict: owner (the role BUILTIN_ROLES grants "
        f"attestation:sign to, specifically so it can attest) gets {r_owner_probe.status_code} "
        f"on this same route, because attestation:read was never granted alongside "
        f"attestation:sign -- no built-in role holds both scopes, so nobody can complete "
        f"view-then-sign through the console end-to-end; a genuine gap left by the "
        f"UI-005/008/009 scope fix, worth its own remediation",
    )

    # UI-120: needs a named person and a statement. Round 2 found status codes alone are
    # ambiguous: 303 can mean either success OR a caught-and-flashed refusal (attestation_sign
    # catches PramaError and redirects with a flash rather than rendering a 422) -- verify via
    # a direct count of attestations actually created instead of trusting the status code.
    async def count_attestations():
        import sqlite3
        conn = sqlite3.connect(str(DB))
        n = conn.execute("SELECT COUNT(*) FROM att_attestation").fetchone()[0]
        conn.close()
        return n

    res120 = {}
    for label, data in [
        ("empty-name", {"attester_name": "", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"}),
        ("empty-statement", {"attester_name": "alice", "statement": "", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"}),
        ("whitespace-name", {"attester_name": "   ", "statement": "s", "scope": "estate", "period_start": "2026-01-01", "period_end": "2026-01-31"}),
    ]:
        try:
            before = await count_attestations()
            r = await http.post("/attestations/new", data=data)
            after = await count_attestations()
            res120[label] = (r.status_code, after - before)
        except Exception as e:
            res120[label] = (f"EXCEPTION {type(e).__name__}", str(e)[:150])
    bad120 = {k: v for k, v in res120.items() if isinstance(v[1], int) and v[1] > 0}
    record("UI-120", "PASS" if not bad120 else "FAIL", f"results(status, n_attestations_created)={res120} bad={bad120}")

    # UI-121: period_start after period_end, and unparsable dates. Expected: "refused with the
    # reason" -- a rendered refusal. The previous check only flagged status==303 (meaning
    # "silently accepted") as bad, and never flagged an uncaught 500 -- which is not a refusal
    # with a reason either, it is a crash, and round 2 found exactly that (an uncaught
    # sqlite3.IntegrityError reaching the client raw). Flag anything that is not a clean,
    # rendered refusal (4xx) as bad.
    res121 = {}
    for label, ps, pe in [("reversed", "2026-02-01", "2026-01-01"), ("unparsable", "banana", "2026-01-31")]:
        try:
            r = await http.post("/attestations/new", data={"attester_name": "alice", "statement": "s", "scope": "estate", "period_start": ps, "period_end": pe})
            res121[label] = r.status_code
        except Exception as e:
            res121[label] = f"EXCEPTION {type(e).__name__}: {str(e)[:150]}"
    bad121 = {k: v for k, v in res121.items() if not (isinstance(v, int) and 400 <= v < 500)}
    record("UI-121", "PASS" if not bad121 else "FAIL", f"results={res121} bad(not a clean 4xx refusal)={bad121}")

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

    # UI-124: the attestation seal wording about the session-secret key. Tested with auditor
    # (see the UI-118 note -- owner cannot reach this GET route at all). Round 2 also found the
    # literal 'session secret'/'key management' keyword search too narrow: the page states the
    # substance ("sealed with an HMAC over its content using this deployment's key... proves
    # nothing to somebody who does not hold it") without using either exact phrase.
    r_form2 = await http_auditor.get("/attestations/new")
    text124 = r_form2.text.lower()
    mentions_session_secret = (
        "session secret" in text124 or "key management" in text124
        or ("hmac" in text124 and "key" in text124 and ("proves" in text124 or "asymmetric" in text124))
    )
    record("UI-124", "PASS" if mentions_session_secret else "FAIL", f"status={r_form2.status_code} draft_page_mentions_key_nature={mentions_session_secret}")

    # UI-125: /attestations/{id}/pack for another estate's id. Tested with auditor (see the
    # UI-118 note -- owner cannot reach this GET route at all, which would mask the tenant
    # check this case is actually about behind an unrelated 403).
    await env.create_principal("auditorA125", "auditorApassword1", ["auditor"])
    http_auditorA125, _ = await env.signed_in_client("auditorA125", "auditorApassword1")
    if att_b_id:
        r125 = await http_auditorA125.get(f"/attestations/{att_b_id}/pack")
        ok125 = r125.status_code == 404
        record("UI-125", "PASS" if ok125 else "FAIL", f"status={r125.status_code}")
    else:
        record("UI-125", "BLOCKED", "no estate B attestation id available")

    await env.stop()
    print("done ui bulk batch 4")


asyncio.run(main())
