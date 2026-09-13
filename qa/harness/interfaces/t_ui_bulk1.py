import sys, os, json, asyncio, re
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    DB = c.WORKDIR / "uibulk1.db"
    env = u.UiEnv(str(DB))
    await env.start()
    await env.create_principal("owner1", "ownerpassword1", ["owner"])
    http, _ = await env.signed_in_client("owner1", "ownerpassword1")

    # UI-061: dataset names trimmed and bounded
    r_long = await http.post("/declarations/new", data={"name": "x" * 5000, "shape": "unbound", "criticality": "4"})
    r_spaces = await http.post("/declarations/new", data={"name": "   ", "shape": "unbound", "criticality": "4"})
    ok61 = r_long.status_code in (200, 422) and "255" in r_long.text or r_long.status_code != 303
    ok61b = r_spaces.status_code != 303
    record(
        "UI-061",
        "PASS" if (ok61 and ok61b) else "FAIL",
        f"5000-char name: status={r_long.status_code} redirected={r_long.status_code==303} | "
        f"spaces-only: status={r_spaces.status_code} redirected={r_spaces.status_code==303}",
    )

    # UI-062: a declaration failure re-renders the form with what was typed. Use a failure mode that
    # is actually caught (criticality out of the tier table, a real ValidationError) rather than
    # shape='banana', which crashes with an uncaught IntegrityError (see UI-064) before any re-render.
    weird_name = "my-test-dataset-62"
    try:
        r_fail = await http.post("/declarations/new", data={"name": weird_name, "shape": "unbound", "criticality": "1", "description": "kept-description-62"})
        # criticality=1 with no approved_by should be refused by the maker-checker policy
        ok62 = r_fail.status_code != 303 and weird_name in r_fail.text and "kept-description-62" in r_fail.text
        detail62 = f"status={r_fail.status_code} name_repopulated={weird_name in r_fail.text} description_repopulated={'kept-description-62' in r_fail.text}"
    except Exception as e:
        ok62 = False
        detail62 = f"client exception: {type(e).__name__} {str(e)[:200]}"
    record("UI-062", "PASS" if ok62 else "FAIL", detail62)

    # UI-063: criticality non-numeric and out of range
    r_banana_crit = await http.post("/declarations/new", data={"name": "crit-banana-63", "shape": "unbound", "criticality": "banana"})
    res63 = {"banana": (r_banana_crit.status_code, r_banana_crit.headers.get("content-type"))}
    for label, val in [("0", "0"), ("5", "5"), ("-1", "-1")]:
        try:
            r = await http.post("/declarations/new", data={"name": f"crit-{label}-63b", "shape": "unbound", "criticality": val})
            res63[label] = (r.status_code, "ok")
        except Exception as e:
            res63[label] = ("UNCAUGHT_EXCEPTION", f"{type(e).__name__}: {str(e)[:150]}")
    ok63 = (
        res63["banana"][0] == 422 and "text/html" in (res63["banana"][1] or "")
        and all(res63[k][0] != 303 and res63[k][0] != "UNCAUGHT_EXCEPTION" for k in ("0", "5", "-1"))
    )
    record(
        "UI-063",
        "PASS" if ok63 else "FAIL",
        f"results={res63} -- the int-typed 'banana' correctly 422s via FastAPI's own form coercion, but "
        f"out-of-range integers (0, 5, -1) are NOT bounded by the form/service layer at all and reach the "
        f"database's ck_sem_dataset_criticality CHECK constraint as an uncaught IntegrityError, the same "
        f"unguarded-DB-CHECK pattern as UI-064/API-050/Q-27",
    )

    # UI-064: shape validated before the database (bypassing the select)
    try:
        r_shape = await http.post("/declarations/new", data={"name": "bad-shape-64", "shape": "banana", "criticality": "4"})
        detail64 = f"status={r_shape.status_code} body_head={r_shape.text[:150]!r}"
        ok64 = r_shape.status_code != 303 and "Traceback" not in r_shape.text and r_shape.status_code != 500
    except Exception as e:
        ok64 = False
        detail64 = f"client exception: {type(e).__name__} {str(e)[:250]}"
    record("UI-064", "PASS" if ok64 else "FAIL", f"{detail64} -- declaration_routes.py::declaration_create passes shape straight to DatasetService.declare with no validation against the SHAPES tuple, which exists only to render the <select> options")

    # UI-065: grain with attributes and no statement, and the reverse
    r_attrs_only = await http.post("/declarations/new", data={"name": "grain-attrs-65", "shape": "unbound", "criticality": "4", "grain": "a,b"})
    r_stmt_only = await http.post("/declarations/new", data={"name": "grain-stmt-65", "shape": "unbound", "criticality": "4", "grain_statement": "one row per account per day"})
    ok65a = r_attrs_only.status_code == 303
    # check whether the statement-only submission's statement was silently dropped
    if r_stmt_only.status_code == 303:
        r_check = await http.get("/declarations")
        stmt_survived = "one row per account per day" in r_check.text
    else:
        stmt_survived = None
    record(
        "UI-065",
        "PASS" if ok65a else "FAIL",
        f"attrs_only_status={r_attrs_only.status_code} stmt_only_status={r_stmt_only.status_code} "
        f"stmt_survived_if_created={stmt_survived} (catalogue predicts the statement is silently dropped "
        f"when there are no attributes, since Grain requires attributes to exist as an object at all)",
    )

    # UI-093: builder always shows PQL and sentence
    r_build = await http.post(
        "/controls/build",
        data={"dataset": "t", "rule": "not_null", "column": "a", "because": "why it matters", "severity": "major"},
    )
    has_pql = "CHECK" in r_build.text
    has_sentence = "why it matters" in r_build.text
    record("UI-093", "PASS" if (has_pql and has_sentence) else "FAIL", f"status={r_build.status_code} has_pql_visible={has_pql} has_sentence_visible={has_sentence}")

    # UI-094: rule_build (POST /controls/build) needs no session -- redirects unauthenticated
    anon = env.client()
    r_anon_build = await anon.post("/controls/build", data={"dataset": "t", "rule": "not_null", "column": "a", "because": "x"})
    ok94 = r_anon_build.status_code == 303 and r_anon_build.headers.get("location", "").startswith("/sign-in")
    record("UI-094", "PASS" if ok94 else "FAIL", f"status={r_anon_build.status_code} location={r_anon_build.headers.get('location')}")
    await anon.aclose()

    await env.stop()
    print("done ui bulk batch 1")


asyncio.run(main())
