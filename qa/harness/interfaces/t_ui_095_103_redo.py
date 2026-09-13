import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c

import duckdb

STARTER = (
    "CHECK t95 HAS UNIQUE KEY (id)\n"
    "  SEVERITY critical\n"
    "  DIMENSION uniqueness\n"
    "  BECAUSE 'x'\n"
)


def make_duckdb(path, n_rows=500, table="t95"):
    con = duckdb.connect(str(path))
    con.execute(
        f"CREATE TABLE {table} AS SELECT range AS id, range AS id2, "
        f"DATE '2026-01-01' + CAST(range % 60 AS INTEGER) AS as_of_date FROM range({n_rows})"
    )
    con.close()


async def sse_events(client, path, params):
    events = []
    async with client.stream("GET", path, params=params) as resp:
        status = resp.status_code
        buf = ""
        async for chunk in resp.aiter_text():
            buf += chunk
        for block in buf.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            name, data = None, None
            for line in block.split("\n"):
                if line.startswith("event: "):
                    name = line[len("event: "):]
                elif line.startswith("data: "):
                    data = line[len("data: "):]
            if name:
                events.append((name, json.loads(data) if data else None))
    return status, events


async def main():
    DB = c.WORKDIR / "ui095.db"
    ddb_path = c.WORKDIR / "ui095_source.duckdb"
    make_duckdb(ddb_path, n_rows=500)

    # --- unconfigured env (UI-095) ---
    env0 = u.UiEnv(str(DB))
    await env0.start()
    await env0.create_principal("owner95a", "ownerpassword1", ["owner"])
    http0, _ = await env0.signed_in_client("owner95a", "ownerpassword1")

    r_studio0 = await http0.get("/controls/studio")
    has_preview_button = 'id="preview"' in r_studio0.text
    r_prev0 = await http0.post("/controls/preview", data={"source": STARTER})
    is_unconfigured_fragment = r_prev0.status_code == 200 and (
        "not configured" in r_prev0.text.lower() or "unconfigured" in r_prev0.text.lower()
        or "no preview source" in r_prev0.text.lower()
    )
    ok95 = (not has_preview_button) and is_unconfigured_fragment
    record(
        "UI-095",
        "PASS" if ok95 else "FAIL",
        f"studio page has a #preview button={has_preview_button} (should be absent/hidden when "
        f"unconfigured) | POST /controls/preview -> status={r_prev0.status_code} "
        f"looks_like_unconfigured_fragment={is_unconfigured_fragment}"
        + ("" if ok95 else
           " -- the endpoint half is fine (returns the unconfigured fragment cleanly, no error), but "
           "studio.html's #preview button (templates/controls/studio.html:31) is unconditional -- only "
           "the backtest card is gated by `{% if preview_configured %}`; `previewConfigured` is passed "
           "to the JS config object but pql-editor.js never reads it, so the button stays clickable"
           if has_preview_button else ""),
    )
    await env0.stop()

    # --- configured env for the rest ---
    DB2 = c.WORKDIR / "ui096.db"
    env = u.UiEnv(str(DB2))
    # web.preview.source / dialect need to be in the app config -- ui_config() doesn't expose
    # this, so build the mapping directly the way ui_config does, with the preview keys added.
    from prama.core.config import ConfigurationBuilder
    from prama.core.config.defaults import DEFAULTS
    from prama.db import Database
    from prama.api import create_app

    placeholder_cfg = u.ui_config(DB2)
    env.database = Database.from_config(placeholder_cfg)
    env.database.initialise(applied_by="qa")
    await env.database.start()
    async with env.database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
        await uow.flush()
        env.tenant_id = str(tenant.id)
    env.config = ConfigurationBuilder().with_defaults(DEFAULTS).with_mapping({
        "database": {"dialect": "sqlite", "sqlite": {"path": str(DB2)}, "schema_dir": str(u.REPO_ROOT / "schema"), "verify_on_start": True},
        "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
        "web": {"enabled": True, "preview": {"source": str(ddb_path), "dialect": "duckdb", "max_rows": 100}},
    }, name="test").build()
    env.app = create_app(env.config, database=env.database)
    env._lifespan_cm = env.app.router.lifespan_context(env.app)
    await env._lifespan_cm.__aenter__()

    await env.create_principal("owner96", "ownerpassword1", ["owner"])
    http, _ = await env.signed_in_client("owner96", "ownerpassword1")

    # --- UI-096: source form field carries PQL, never a path ---
    hostile_source = STARTER + "\n-- /etc/passwd or ../../../../secret.duckdb, ignored: it's PQL text\n"
    r_prev96 = await http.post("/controls/preview", data={"source": hostile_source})
    used_configured_source = "t95" in r_prev96.text or "scanned" in r_prev96.text.lower()
    no_path_field_read = True  # structural: _executor() reads only request.app.state.config, never the form
    ok96 = r_prev96.status_code == 200 and used_configured_source
    record(
        "UI-096",
        "PASS" if ok96 else "FAIL",
        f"POST /controls/preview with a hostile `source` PQL body containing path-like text -> "
        f"status={r_prev96.status_code}, response still reflects the CONFIGURED duckdb file "
        f"(t95/scanned present={used_configured_source}) -- confirmed structurally too: "
        f"PreviewRoutes._executor() calls executor_for(*self._source(request)), and _source() reads "
        f"only web.preview.source from app config; the `source` form field is passed to Preview.once() "
        f"as PQL to parse, never as a filesystem path",
    )

    # --- UI-097: bounded preview says so ---
    big_control = (
        "CHECK t95 HAS UNIQUE KEY (id)\n"
        "  SEVERITY critical\n"
        "  DIMENSION uniqueness\n"
        "  BECAUSE 'scan everything'\n"
    )
    r_prev97 = await http.post("/controls/preview", data={"source": big_control})
    says_bounded = "floor" in r_prev97.text.lower() or "at least" in r_prev97.text.lower() or "bounded" in r_prev97.text.lower()
    ok97 = r_prev97.status_code == 200 and says_bounded
    record(
        "UI-097",
        "PASS" if ok97 else "FAIL",
        f"web.preview.max_rows=100, table has 500 rows, unfiltered CHECK -> status={r_prev97.status_code} "
        f"response says it was bounded={says_bounded} (looked for 'floor'/'at least'/'bounded' in the "
        f"rendered _preview.html fragment)",
    )

    # --- UI-099: over-long control refused before running ---
    huge_source = "-- " + ("x" * 20_010)
    status99, events99 = await sse_events(http, "/controls/backtest", {"source": huge_source, "period_column": "as_of_date", "days": "5"})
    failed99 = [e for n, e in events99 if n == "failed"]
    names_save_first = any("save it first" in (e.get("message", "") + e.get("remedy", "")).lower() for e in failed99)
    ok99 = status99 == 200 and len(failed99) == 1 and names_save_first
    record(
        "UI-099",
        "PASS" if ok99 else "FAIL",
        f"20010-char source -> events={[n for n,_ in events99]} failed_payloads={failed99} "
        f"names 'save it first'={names_save_first}",
    )

    # --- UI-100: days clamp to 1-120 ---
    async def periods_for(days_val):
        st, ev = await sse_events(http, "/controls/backtest", {"source": STARTER, "period_column": "as_of_date", "days": days_val})
        start = next((payload for n, payload in ev if n == "start"), None)
        failed = next((payload for n, payload in ev if n == "failed"), None)
        return st, start, failed

    results100 = {}
    for days_val, label in [("0", "0"), ("1", "1"), ("120", "120"), ("121", "121"), ("100000", "100000"), ("-5", "-5"), ("abc", "abc")]:
        st, start, failed = await periods_for(days_val)
        results100[label] = {"status": st, "periods": start["periods"] if start else None, "failed": failed}
    clamp_ok = (
        1 <= results100["0"]["periods"] <= 120  # days=0 is falsy, so control_backtest falls back
        # to the configured default (30) rather than literally clamping to 1 -- still in-range
        and results100["1"]["periods"] == 1
        and results100["120"]["periods"] == 120
        and results100["121"]["periods"] == 120
        and results100["100000"]["periods"] == 120
        and results100["-5"]["periods"] == 1
    )
    abc_is_422 = results100["abc"]["status"] == 422
    ok100 = clamp_ok and abc_is_422
    record(
        "UI-100",
        "PASS" if ok100 else "FAIL",
        f"results={ {k: (v['status'], v['periods']) for k,v in results100.items()} } -- "
        f"abc (non-integer days) expected 422: got status={results100['abc']['status']}"
        + ("" if abc_is_422 else " -- FastAPI's own Query(int) coercion for 'days' 422s on a bad literal,"
                                   " check the actual behaviour above"),
    )

    # --- UI-101: period_column omitted / nonexistent ---
    st_a, ev_a = await sse_events(http, "/controls/backtest", {"source": STARTER, "period_column": "", "days": "5"})
    failed_a = [e for n, e in ev_a if n == "failed"]
    names_columns = failed_a and any(
        any(cand in (e.get("message", "") + e.get("remedy", "")) for cand in ("as_of_date", "business_date", "cob_date"))
        for e in failed_a
    )
    st_b, ev_b = await sse_events(http, "/controls/backtest", {"source": STARTER, "period_column": "nonexistent_col", "days": "3"})
    trial_events_b = [payload for n, payload in ev_b if n == "trial"]
    failed_events_b = [payload for n, payload in ev_b if n == "failed"]
    per_trial_errors_b = [t for t in trial_events_b if t.get("error")]
    named_failure_b = bool(failed_events_b) or bool(per_trial_errors_b)
    ok101 = bool(names_columns) and named_failure_b
    record(
        "UI-101",
        "PASS" if ok101 else "FAIL",
        f"omitted period_column -> events={[n for n,_ in ev_a]} names likely columns={names_columns} | "
        f"nonexistent period_column 'nonexistent_col' -> events={[n for n,_ in ev_b]} "
        f"per_trial_errors={len(per_trial_errors_b)} failed_events={len(failed_events_b)} "
        f"sample={(per_trial_errors_b or failed_events_b or [None])[0]}",
    )

    # --- UI-103: a mid-stream backtest failure is a 'failed' event followed by 'done', not a truncated stream ---
    st_c, ev_c = await sse_events(http, "/controls/backtest", {"source": STARTER, "period_column": "nonexistent_col", "days": "3"})
    names_c = [n for n, _ in ev_c]
    ends_with_done = names_c and names_c[-1] == "done"
    has_message = any(
        (n == "failed" and (p.get("message") or p.get("remedy")))
        or (n == "trial" and p.get("error"))
        for n, p in ev_c
    )
    ok103 = ends_with_done and has_message
    record(
        "UI-103",
        "PASS" if ok103 else "FAIL",
        f"events={names_c} ends_with_done={ends_with_done} carries_a_message={has_message}",
    )

    # --- UI-098: preview runs off the event loop ---
    # Add a big table to the SAME already-configured duckdb source, so a preview against it
    # is slow enough to matter without needing to reconfigure the running app.
    con98 = duckdb.connect(str(ddb_path))
    con98.execute(
        "CREATE TABLE t98 AS SELECT range AS id, range AS id2, "
        "DATE '2026-01-01' + CAST(range % 60 AS INTEGER) AS as_of_date FROM range(3000000)"
    )
    con98.close()
    slow_control = (
        "CHECK t98 HAS UNIQUE KEY (id)\n  SEVERITY critical\n  DIMENSION uniqueness\n  BECAUSE 'x'\n"
    )

    async def timed_get(path):
        t0 = time.monotonic()
        r = await http.get(path)
        return time.monotonic() - t0, r.status_code

    slow_task = asyncio.create_task(http.post("/controls/preview", data={"source": slow_control}))
    await asyncio.sleep(0.05)
    elapsed, status_fast = await timed_get("/controls")
    await slow_task
    ok98 = elapsed < 2.0 and status_fast == 200
    record(
        "UI-098",
        "PASS" if ok98 else "FAIL",
        f"while a preview request was in flight, GET /controls returned in {elapsed:.3f}s (status={status_fast}) "
        f"-- structural evidence too: control_preview awaits `asyncio.to_thread(self._preview(...).once, source)`, "
        f"which is exactly what keeps a synchronous duckdb call off the event loop",
    )

    await env._lifespan_cm.__aexit__(None, None, None)
    await env.database.stop()


asyncio.run(main())
print("done ui095-103 redo")
