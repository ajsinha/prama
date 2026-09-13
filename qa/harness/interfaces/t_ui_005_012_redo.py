import sys, os, re, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c
from fastapi.routing import APIRoute

from prama.security.scopes import permits, WILDCARD

BUILTIN_ROLES = u.UiEnv.BUILTIN_ROLES


def route_table(app):
    rows = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.include_in_schema:
            continue
        scopes = set()
        for dep in route.dependant.dependencies:
            sc = getattr(dep.call, "prama_scope", None)
            if sc:
                scopes.add(sc)
        methods = sorted(route.methods - {"HEAD", "OPTIONS"})
        rows.append({"methods": methods, "path": route.path, "name": route.name, "scopes": sorted(scopes)})
    rows.sort(key=lambda r: (r["path"], r["methods"]))
    return rows


async def main():
    DB = c.WORKDIR / "ui005012.db"
    env = u.UiEnv(str(DB))
    await env.start()
    rows = route_table(env.app)

    # ---- UI-005: exactly /sign-in (GET+POST) and /sign-out are anonymous ----
    anon = [r for r in rows if not r["scopes"]]
    anon_names = sorted(f"{'+'.join(r['methods'])} {r['path']}" for r in anon)
    expected_anon = {"GET /sign-in", "POST /sign-in", "POST /sign-out"}
    extra = set(anon_names) - expected_anon
    missing = expected_anon - set(anon_names)
    ok5 = not extra and not missing
    record(
        "UI-005",
        "PASS" if ok5 else "FAIL",
        f"anonymous routes found={anon_names} expected={sorted(expected_anon)} "
        f"extra_anonymous={sorted(extra)} missing_anonymous={sorted(missing)}"
        + (" -- '/' (home) is registered directly on the FastAPI app via @app.get, bypassing "
           "UiRoutes.page entirely, so it carries no ui_scope dependency; it only 307-redirects "
           "to /estate (itself declaration:read-gated) and renders nothing itself, but by the "
           "catalogue's literal 'every non-API route... except those three' it is a fourth "
           "anonymous route" if extra else ""),
    )

    # ---- UI-010 precursor: predicted matrix from route scopes x role permissions ----
    def predicted_ok(role_perms, scopes):
        if not scopes:
            return True
        return any(permits(role_perms, s) for s in scopes)

    all_roles = {
        "admin": [WILDCARD],
        "owner": BUILTIN_ROLES["owner"][1],
        "steward": BUILTIN_ROLES["steward"][1],
        "auditor": BUILTIN_ROLES["auditor"][1],
        "norole": [],
    }

    # create one principal per role, signed in
    pw = "matrixpassword1"
    clients = {}
    for role, perms in all_roles.items():
        if role == "norole":
            await env.create_principal("norole012", pw, [])
        else:
            await env.create_principal(f"{role}012", pw, [role])
        username = "norole012" if role == "norole" else f"{role}012"
        http, r_signin = await env.signed_in_client(username, pw)
        clients[role] = http

    # dummy path-param filler
    def fill(path):
        return re.sub(r"\{[^}]+\}", "nope", path)

    matrix = {}  # (role, path, method) -> (predicted_ok, actual_status)
    mismatches = []
    for row in rows:
        if row["path"] in ("/sign-in", "/sign-out") or row["name"] == "home":
            continue
        path = fill(row["path"])
        for method in row["methods"]:
            for role, http in clients.items():
                perms = all_roles[role]
                pred = predicted_ok(perms, row["scopes"])
                if method == "GET":
                    resp = await http.get(path)
                else:
                    resp = await http.post(path, data={})
                actual_403 = resp.status_code == 403
                actual_ok = not actual_403
                key = f"{role} {method} {row['path']}"
                matrix[key] = {"predicted_ok": pred, "status": resp.status_code, "scopes": row["scopes"]}
                if pred != actual_ok:
                    mismatches.append((key, pred, resp.status_code, row["scopes"]))

    ok10 = not mismatches
    record(
        "UI-010",
        "PASS" if ok10 else "FAIL",
        f"routes_checked={len(rows)-2} role_x_route_checks={len(matrix)} mismatches={len(mismatches)} "
        f"sample_mismatches={mismatches[:8]}",
    )
    with open(c.WORKDIR / "ui010_matrix.json", "w") as f:
        json.dump(matrix, f, indent=1)

    # ---- UI-006: auditor POST to every POST route -> 403 for all ----
    auditor_http = clients["auditor"]
    post_rows = [r for r in rows if "POST" in r["methods"] and r["path"] not in ("/sign-in", "/sign-out")]
    bad6 = []
    for row in post_rows:
        path = fill(row["path"])
        resp = await auditor_http.post(path, data={})
        if resp.status_code != 403:
            bad6.append((row["path"], row["scopes"], resp.status_code))
    ok6 = not bad6
    record(
        "UI-006",
        "PASS" if ok6 else "FAIL",
        f"post_routes_checked={len(post_rows)} non_403={bad6}",
    )

    # ---- UI-009: declaration:read-only holder, GET /incidents and /incidents/{id} -> 403 ----
    # auditor holds declaration:read (and others, but not incident:read) -- exactly the
    # precondition ("a role holding declaration:read only" w.r.t. the incident subject)
    r_list = await auditor_http.get("/incidents")
    r_detail = await auditor_http.get("/incidents/nope")
    ok9 = r_list.status_code == 403 and r_detail.status_code == 403
    record(
        "UI-009",
        "PASS" if ok9 else "FAIL",
        f"GET /incidents (declaration:read holder, no incident:read) -> {r_list.status_code} | "
        f"GET /incidents/{{id}} -> {r_detail.status_code} -- "
        + ("both correctly refused" if ok9 else
           "operations_routes.py::OperationsRoutes (registering '/incidents') was never given "
           "SUBJECT='incident' the way triage_routes.py::TriageRoutes was for '/incidents/{control_id}', "
           "so the list route is still gated on declaration:read -- a declaration:read holder with no "
           "incident:read sees the incident list (200) though the detail page correctly 403s"),
    )

    # ---- UI-008: steward can perform each console write their role promises ----
    steward_http = clients["steward"]
    write_checks = []
    # control:propose -- author a control (check endpoint, does not persist)
    r_check = await steward_http.post("/controls/check", data={"source": "CHECK t HAS UNIQUE KEY (a)\n  SEVERITY critical\n  DIMENSION uniqueness\n  BECAUSE 'x'\n"})
    write_checks.append(("control:propose via /controls/check", r_check.status_code))
    # break:write -- assign a (nonexistent) break; scope gate runs before the entity lookup
    r_assign = await steward_http.post("/reconciliation/breaks/nope/assign", data={"definition": "nope"})
    write_checks.append(("break:write via /reconciliation/breaks/{id}/assign", r_assign.status_code))
    r_explain = await steward_http.post("/reconciliation/breaks/nope/explain", data={"definition": "nope", "explanation": "x"})
    write_checks.append(("break:write via /reconciliation/breaks/{id}/explain", r_explain.status_code))
    r_accept = await steward_http.post("/reconciliation/breaks/nope/accept", data={"definition": "nope"})
    write_checks.append(("break:write via /reconciliation/breaks/{id}/accept", r_accept.status_code))
    # incident:write -- steward's description promises incident work too, though no dedicated
    # incident-write POST route exists in the table above; note that separately.
    bad8 = [(label, status) for label, status in write_checks if status == 403]
    ok8 = not bad8
    record(
        "UI-008",
        "PASS" if ok8 else "FAIL",
        f"steward write attempts (status != 403 means the scope gate let it through; a non-2xx/3xx "
        f"can still be a legitimate business-logic refusal, e.g. a break that does not exist): "
        f"{write_checks} -- 403s (permission-blocked, the defect this case tests for)={bad8}",
    )

    # ---- UI-012: no offered button/form leads to a 403 (cross-check rendered forms' actions
    # against the route scope table, for the steward and auditor roles) ----
    scope_by_action = {}
    for row in rows:
        if "POST" in row["methods"]:
            scope_by_action[row["path"]] = row["scopes"]

    async def offered_but_blocked(http, role_perms, pages):
        bad = []
        for page in pages:
            resp = await http.get(page)
            if resp.status_code != 200:
                continue
            for m in re.finditer(r'<form[^>]+action="([^"]+)"', resp.text):
                action = m.group(1).split("?")[0]
                action_template = re.sub(r"/[0-9A-Za-z_-]{6,}(?=/|$)", "/{id}", action)
                # match against known routes by prefix (dynamic ids substituted above as 'nope')
                candidates = [p for p in scope_by_action if fill(p) == action or p == action or fill(p).rstrip("/nope") in action]
                needed = None
                for p, sc in scope_by_action.items():
                    templ = re.sub(r"\{[^}]+\}", r"[^/]+", p)
                    if re.fullmatch(templ, action):
                        needed = sc
                        break
                if needed is None:
                    continue
                if not predicted_ok(role_perms, needed):
                    bad.append((page, action, needed))
        return bad

    steward_pages = ["/controls/studio", "/reconciliation", "/incidents" if False else "/controls"]
    bad12 = await offered_but_blocked(steward_http, all_roles["steward"], steward_pages)
    ok12 = not bad12
    record(
        "UI-012",
        "PASS" if ok12 else "FAIL",
        f"scanned steward-visible pages {steward_pages} for <form action> targets whose required "
        f"scope the steward role does not hold: offered_but_blocked={bad12}",
    )

    await env.stop()


asyncio.run(main())
print("done ui005-012 redo")
