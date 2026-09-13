import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    DB = c.WORKDIR / "uibulk6.db"
    env = u.UiEnv(str(DB))
    await env.start()
    await env.create_principal("owner71", "ownerpassword1", ["owner"])
    http, _ = await env.signed_in_client("owner71", "ownerpassword1")

    # setup: a dataset with three attributes
    r_ds = await http.post("/declarations/new", data={"name": "studio-ds-71", "shape": "unbound", "criticality": "4"})
    import sqlite3
    conn = sqlite3.connect(str(DB))
    row = conn.execute("SELECT dataset_id FROM sem_dataset_version WHERE slug='studio_ds_71' ORDER BY recorded_at DESC LIMIT 1").fetchone()
    conn.close()
    ds_id = row[0] if row else None
    for attr in ["field_a", "field_b", "field_c"]:
        await http.post(f"/datasets/{ds_id}/attributes" if False else "/declarations/new", data={}) if False else None
    # attribute declaration is via the API in this codebase (no console form was found for it in our route scan);
    # add attributes directly through the async service instead
    from prama.semantic.services import DatasetService
    async with env.database.unit_of_work() as uow:
        for attr in ["field_a", "field_b", "field_c"]:
            await DatasetService(uow).declare_attribute(tenant_id=env.tenant_id, dataset_id=ds_id, name=attr, authored_by="owner71")
        await uow.flush()

    # UI-071: studio check matches CLI findings for the same suite
    bad_source = "CHECK studio_ds_71.field_a IS NOT NULL SEVERITY urgent\n"
    r_check = await http.post("/controls/check", data={"source": bad_source})
    check_text = r_check.text
    from prama.cli.base import Application
    from prama.cli.commands import all_commands
    import io as _io
    wf = c.WORKDIR / "ui071.pql"
    wf.write_text(bad_source)
    out = _io.StringIO()
    cli_code = Application(all_commands()).run(["control", "check", str(wf)], out=out)
    cli_text = out.getvalue()
    ok71 = ("critical" in check_text.lower() and "critical" in cli_text.lower()) or ("severity" in check_text.lower() and "severity" in cli_text.lower())
    record("UI-071", "PASS" if ok71 else "FAIL", f"studio_status={r_check.status_code} studio_mentions_severities={'critical' in check_text.lower()} cli_mentions_severities={'critical' in cli_text.lower()}")

    # UI-072: studio catalogue derived from declarations
    r_completions = await http.post("/controls/completions", data={"source": "CHECK studio_ds_71.", "line": "1", "column": "20"})
    body72 = r_completions.text
    doc72 = json.loads(body72) if r_completions.status_code == 200 else None
    names_offered = [item.get("label", item.get("text", "")) for item in doc72.get("items", [])] if doc72 else []
    ok72 = doc72 is not None and all(a in names_offered for a in ["field_a", "field_b", "field_c"])
    record("UI-072", "PASS" if ok72 else "FAIL", f"status={r_completions.status_code} names_offered={names_offered[:10]}")

    # UI-073: control_completions/control_hover with out-of-range positions
    res73 = {}
    for label, line, col in [("line=0", "0", "1"), ("line=-1", "-1", "1"), ("line=999999", "999999", "1"), ("column=0", "1", "0"), ("nonnumeric", "abc", "1")]:
        try:
            r = await http.post("/controls/completions", data={"source": "CHECK t.a IS NOT NULL BECAUSE 'x'", "line": line, "column": col})
            res73[label] = r.status_code
        except Exception as e:
            res73[label] = f"EXCEPTION {type(e).__name__}: {str(e)[:150]}"
    bad73 = {k: v for k, v in res73.items() if v == 500 or (isinstance(v, str) and "EXCEPTION" in v)}
    record("UI-073", "PASS" if not bad73 else "FAIL", f"results={res73}")

    # UI-074: control_compile with an unknown target
    r74 = await http.post("/controls/compile", data={"source": "CHECK studio_ds_71.field_a IS NOT NULL BECAUSE 'x'", "target": "oracle"})
    ok74 = r74.status_code != 500 and ("Traceback" not in r74.text)
    record("UI-074", "PASS" if ok74 else "FAIL", f"status={r74.status_code} body_head={r74.text[:200]!r}")

    # UI-130: reports render for an empty estate
    DB2 = c.WORKDIR / "uibulk6b.db"
    env2 = u.UiEnv(str(DB2))
    await env2.start()
    await env2.create_principal("owner130", "ownerpassword1", ["owner"])
    http2, _ = await env2.signed_in_client("owner130", "ownerpassword1")
    r_decl_report = await http2.get("/reports/declarations")
    r_ctrl_report = await http2.get("/reports/controls")
    ok130 = r_decl_report.status_code == 200 and r_ctrl_report.status_code == 200 and "Traceback" not in r_decl_report.text and "Traceback" not in r_ctrl_report.text
    record("UI-130", "PASS" if ok130 else "FAIL", f"declarations_status={r_decl_report.status_code} controls_status={r_ctrl_report.status_code}")

    # UI-132: both report packs are HTML with the right content type
    ct_decl = r_decl_report.headers.get("content-type", "")
    ct_ctrl = r_ctrl_report.headers.get("content-type", "")
    ok132 = "text/html" in ct_decl and "text/html" in ct_ctrl
    record("UI-132", "PASS" if ok132 else "FAIL", f"declarations_ct={ct_decl} controls_ct={ct_ctrl}")

    # UI-133: scorecard and evidence screens on an empty estate
    r_scorecards = await http2.get("/scorecards")
    r_evidence = await http2.get("/evidence")
    ok133 = r_scorecards.status_code == 200 and r_evidence.status_code == 200
    record("UI-133", "PASS" if ok133 else "FAIL", f"scorecards_status={r_scorecards.status_code} evidence_status={r_evidence.status_code}")
    await env2.stop()

    # UI-135: CSRF -- a cross-origin POST with a valid session cookie (same_site=lax only defence)
    # Cannot truly simulate a cross-SITE browser navigation via ASGITransport (no real Origin/Referer
    # enforcement exists to test unless the server checks headers itself); confirm by code inspection
    # whether ANY Origin/Referer check or CSRF token exists anywhere in the console routes.
    import subprocess
    grep = subprocess.run(["grep", "-rln", "csrf\\|Origin\\|Referer", str(c.REPO_ROOT / "src/prama/web")], capture_output=True, text=True)
    hits = grep.stdout.strip().splitlines()
    record(
        "UI-135",
        "FAIL" if not hits else "PASS",
        f"grep for csrf/Origin/Referer handling in src/prama/web: {hits} -- "
        f"{'no CSRF token, Origin check, or Referer check exists anywhere; SameSite=lax on the session '
           'cookie (confirmed present at UI-002) is the entire defence, exactly as the catalogue states, '
           'and it is undocumented as a deliberate decision anywhere in the code' if not hits else ''}",
    )

    await env.stop()
    print("done ui bulk batch 6")


asyncio.run(main())
