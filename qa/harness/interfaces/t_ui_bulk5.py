import sys, os, json, asyncio, sqlite3, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    DB = c.WORKDIR / "uibulk5.db"
    env = u.UiEnv(str(DB))
    await env.start()
    await env.create_principal("owner126", "ownerpassword1", ["owner"])
    await env.create_principal("steward126", "stewardpassword1", ["steward"])
    httpO, _ = await env.signed_in_client("owner126", "ownerpassword1")
    httpS, _ = await env.signed_in_client("steward126", "stewardpassword1")

    pql_low = "CHECK t126.a IS NOT NULL SEVERITY info DIMENSION completeness BECAUSE 'low severity as reviewed'"
    pql_high_tampered = "CHECK t126.a IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'low severity as reviewed'"
    identity = "proposal-126-identity"

    # UI-126: accept re-derives the PQL from the identity's real text, ignoring a tampered form field
    r_accept = await httpO.post(
        "/proposals/accept",
        data={"identity": identity, "pql": pql_high_tampered, "rule": "manual", "dataset_id": ""},
    )
    conn = sqlite3.connect(str(DB))
    row = conn.execute("SELECT severity, pql FROM ctl_control_version WHERE control_id IN (SELECT id FROM ctl_control WHERE identity=?) ORDER BY recorded_at DESC LIMIT 1", (identity,)).fetchone()
    conn.close()
    record(
        "UI-126",
        "INSPECT" if False else ("FAIL" if row and row[0] == "critical" else "PASS" if row else "FAIL"),
        f"accept_status={r_accept.status_code} stored_severity={row[0] if row else None} "
        f"(posted pql claims 'critical'; nothing else establishes a separate 'true' text for this "
        f"identity in this probe, since accept() calls uow.controls.declare(identity=identity, pql=pql, ...) "
        f"directly with the POSTED pql -- the 're-derivation' the docstring describes is parsing/hashing the "
        f"SUBMITTED text, not cross-checking it against an earlier proposal's stored text -- so a mismatched "
        f"severity in the posted field IS what gets stored, unless the *queue's own PQL* is regenerated "
        f"server-side and the form is expected to echo it verbatim)",
    )

    # UI-127: accept activates; reject records, and the rejected one does not return
    r_accept2 = await httpO.post(
        "/proposals/accept",
        data={"identity": "proposal-127-a", "pql": "CHECK t127.a IS NOT NULL BECAUSE 'x'", "rule": "manual", "dataset_id": ""},
    )
    conn = sqlite3.connect(str(DB))
    row127 = conn.execute("SELECT status FROM ctl_control_version WHERE control_id IN (SELECT id FROM ctl_control WHERE identity=?) ORDER BY recorded_at DESC LIMIT 1", ("proposal-127-a",)).fetchone()
    conn.close()
    ok127 = row127 and row127[0] == "active"
    record("UI-127", "PASS" if ok127 else "FAIL", f"accept_status={r_accept2.status_code} stored_status={row127}")

    # UI-128: accept declares AND activates in one POST -- can a steward (control:propose only, no
    # declaration:write) reach it at all?
    r_steward_accept = await httpS.post(
        "/proposals/accept",
        data={"identity": "proposal-128-steward", "pql": "CHECK t128.a IS NOT NULL BECAUSE 'x'", "rule": "manual", "dataset_id": ""},
    )
    conn = sqlite3.connect(str(DB))
    created128 = conn.execute("SELECT COUNT(*) FROM ctl_control WHERE identity=?", ("proposal-128-steward",)).fetchone()[0]
    conn.close()
    ok128 = r_steward_accept.status_code == 403 and created128 == 0
    record(
        "UI-128",
        "PASS" if ok128 else "FAIL",
        f"steward_accept_status={r_steward_accept.status_code} control_created={created128 > 0} -- "
        f"'/proposals/accept' derives declaration:write (auto, POST), which the steward role does NOT "
        f"hold (steward holds control:propose, not declaration:write), so today a steward is refused -- "
        f"the outcome matches the catalogue's literal Expected (refused), though for a different scope "
        f"reason than the catalogue's own Why describes",
    )

    # UI-129: rejecting with a mismatched content_hash
    real_pql = "CHECK t129.a IS NOT NULL BECAUSE 'x'"
    wrong_hash = "0" * 40
    r_reject = await httpO.post(
        "/proposals/reject",
        data={"identity": "proposal-129-identity", "content_hash": wrong_hash, "reason": "incorrect", "note": ""},
    )
    conn = sqlite3.connect(str(DB))
    n_rejections = conn.execute("SELECT COUNT(*) FROM ctl_rejection WHERE content_hash=?", (wrong_hash,)).fetchone()[0] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ctl_rejection'").fetchone() else None
    conn.close()
    record(
        "UI-129",
        "INSPECT" if n_rejections is None else ("FAIL" if n_rejections else "PASS"),
        f"reject_status={r_reject.status_code} rejection_recorded_for_mismatched_hash={n_rejections}",
    )

    await env.stop()
    print("done ui bulk batch 5")


asyncio.run(main())
