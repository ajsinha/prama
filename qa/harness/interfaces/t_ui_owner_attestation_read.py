"""Round 4 addition: BUILTIN_ROLES["owner"] gained attestation:read (Batch A, Q-67).

Round 3 could not test UI-118/UI-124/UI-125 with `owner` at all -- owner held
only attestation:sign, so every GET under AttestationRoutes 403'd, and the
round-3 harness substituted `auditor` (which holds attestation:read but not
attestation:sign) to exercise the page logic. That substitution is still a
faithful test of the page logic, but it never confirms the fix itself: whether
the one role the product built specifically to attest can now actually see a
draft before signing it, and its own signed record afterwards.

This script tests with `owner` directly, since ui_common.py's UiEnv.BUILTIN_ROLES
was corrected (this round) to match the product's current grant.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from logger import record
import ui_common as u
import cli_common as c


async def main():
    DB = c.WORKDIR / "ui_owner_attread.db"
    env = u.UiEnv(str(DB))
    await env.start()
    async with env.database.unit_of_work() as uow:
        t2 = uow.tenants.create(slug="rival-bank-attread", display_name="Rival AR")
        await uow.flush()
        tenant_b = str(t2.id)

    await env.create_principal("ownerAR", "ownerARpassword1", ["owner"])
    http_o, _ = await env.signed_in_client("ownerAR", "ownerARpassword1")
    await env.create_principal("ownerB_AR", "ownerBARpassword1", ["owner"], tenant_id=tenant_b)
    http_oB, _ = await env.signed_in_client("ownerB_AR", "ownerBARpassword1", tenant_slug="rival-bank-attread")
    del tenant_b

    # UI-118 (re-tested with owner): the draft is visible before signing.
    r_new = await http_o.get("/attestations/new")
    ok118_draft = r_new.status_code == 200

    # UI-124 (re-tested with owner): the seal-key wording is on the same page.
    text124 = r_new.text.lower()
    mentions_session_secret = (
        "session secret" in text124 or "key management" in text124
        or ("hmac" in text124 and "key" in text124 and ("proves" in text124 or "asymmetric" in text124))
    )
    ok124 = ok118_draft and mentions_session_secret
    record(
        "UI-124",
        "PASS" if ok124 else "FAIL",
        f"as owner: status={r_new.status_code} draft_page_mentions_key_nature={mentions_session_secret}",
    )

    # Sign one, as owner, and confirm owner can read its own signed record --
    # the second half of what UI-118's Expected asks for ("the draft, with
    # every control and its standing", read by the one role built to attest).
    r_sign = await http_o.post("/attestations/new", data={
        "attester_name": "Owner AR", "statement": "attesting as owner", "scope": "the estate",
        "period_start": "2026-01-01", "period_end": "2026-12-31",
    })
    loc = r_sign.headers.get("location", "")
    own_record_readable = False
    att_id = None
    if r_sign.status_code == 303 and "/attestations/" in loc:
        att_id = loc.rsplit("/", 1)[-1]
        r_own = await http_o.get(loc)
        own_record_readable = r_own.status_code == 200
    ok118 = ok118_draft and own_record_readable
    record(
        "UI-118",
        "PASS" if ok118 else "FAIL",
        f"GET /attestations/new as owner (attestation:sign + attestation:read) -> status={r_new.status_code}; "
        f"signed one (sign_status={r_sign.status_code}, location={loc}) and re-read it as owner -> "
        f"own_record_readable={own_record_readable} -- "
        f"{'the Batch A / Q-67 fix holds: owner can now read the draft it is about to sign, and its own signed record afterwards' if ok118 else 'owner still cannot complete view-then-sign end-to-end'}",
    )

    # UI-125 (re-tested with owner): another estate's pack is 404, not masked by a 403.
    if att_id:
        r125 = await http_o.get(f"/attestations/{att_id}/pack")
        ok125_self = r125.status_code == 200
    else:
        ok125_self = False
    # cross-tenant: estate B's owner session requests estate A's pack id
    if att_id:
        r125_cross = await http_oB.get(f"/attestations/{att_id}/pack")
        ok125 = r125_cross.status_code == 404 and ok125_self
    else:
        ok125 = False
        r125_cross = None
    record(
        "UI-125",
        "PASS" if ok125 else "FAIL",
        f"as owner: own-estate pack status={'200' if ok125_self else 'not-200'}; "
        f"other estate's owner requesting this pack id -> status={r125_cross.status_code if r125_cross else None} "
        f"(expected 404, no leak) -- tested with owner (the role the fix targets), not auditor",
    )

    print("done owner-attestation-read verification")


asyncio.run(main())
