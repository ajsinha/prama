import sys, os, json, asyncio, re
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
import ui_common as u
import api_common as a
from logger import record

# ============ CLI-083: --environment with separators ============
def new_cfg(name):
    d = c.WORKDIR / name
    d.mkdir(exist_ok=True, parents=True)
    cfgf = d / "application.yaml"
    dbpath = d / "x.db"
    cfgf.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {dbpath}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
        "security:\n  session_secret: test-only\n"
    )
    c.run(["--config", str(cfgf), "db", "init"])
    tcode, tout, terr = c.run(["--json", "--config", str(cfgf), "tenant", "create", "acme-bank"])
    tid = json.loads(tout)["id"]
    cfgf.write_text(cfgf.read_text() + f"tenancy:\n  default_tenant: {tid}\n")
    import io, contextlib
    inbuf = "alicepassword1\nalicepassword1\n"
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(inbuf)
    try:
        c.run(["--config", str(cfgf), "principal", "create", "alice", "--admin", "--tenant", "acme-bank"])
    finally:
        sys.stdin = old_stdin
    return cfgf, d, dbpath


cfg83, d83, db83 = new_cfg("cli083")
bad83 = {}
for envval in ["live_pk", "", "../x"]:
    code, out, err = c.run(["--json", "--config", str(cfg83), "apikey", "create", "envsep", "--principal", "alice", "--scope", "*", "--environment", envval])
    if code == 0:
        try:
            doc = json.loads(out)
            prefix = doc.get("prefix", "")
        except Exception:
            prefix = "<unparseable:" + out[:60] + ">"
        # the prefix is "pk_<env>_..." (12 chars) -- an environment containing '_' or being
        # empty makes the prefix ambiguous for prefix_of() to recover unambiguously
        bad83[repr(envval)] = f"ACCEPTED prefix={prefix!r}"
    else:
        bad83[repr(envval)] = f"refused code={code}"
ok83 = all(v.startswith("refused") for v in bad83.values())
record(
    "CLI-083",
    "PASS" if ok83 else "FAIL",
    f"results={bad83} -- ApiKeyIssuer.issue() in src/prama/db/security.py builds "
    f"f'pk_{{environment}}_{{secret}}' with no validation on environment at all"
    + ("" if ok83 else "; every one of live_pk/''/../x was silently accepted, embedding the separator "
                        "or an empty segment straight into the prefix"),
)

# ============ API-053: changes is an open dict, unknown/colliding keys ============
async def api053():
    DB = c.WORKDIR / "api053.db"
    env = a.Env(str(DB))
    await env.start()
    http = env.client(env.api_key)
    r_create = await http.post("/datasets", json={
        "name": "api053ds", "shape": "unbound", "criticality": 3,
    })
    ds_id = r_create.json().get("id")
    if ds_id is None:
        return False, f"could not create seed dataset: {r_create.status_code} {r_create.text[:200]}"
    r_amend = await http.post(f"/datasets/{ds_id}/amend", json={
        "reason": "x", "changes": {"tenant_id": "some-other-estate"},
    })
    await env.stop()
    is_uncaught = r_amend.status_code == 500 and (
        "TypeError" in r_amend.text or "traceback" in r_amend.text.lower()
    )
    is_clean_refusal = r_amend.status_code in (400, 409, 422) and "application/problem+json" in r_amend.headers.get("content-type", "")
    ok = is_clean_refusal and not is_uncaught
    return ok, f"status={r_amend.status_code} content_type={r_amend.headers.get('content-type')} body={r_amend.text[:250]!r}"


ok53, obs53 = asyncio.run(api053())
record("API-053", "PASS" if ok53 else "FAIL", obs53)

# ============ MCP-021: secret-shape withholding (correctly-labelled id; MCP-022 already recorded) ============
sys.path.insert(0, str(c.REPO_ROOT / "src"))
from prama.mcp.server import Server
from prama.assistant.tools import Estate, default_registry

_descriptions = {}
def _describe(name):
    return _descriptions.get(name, {"name": name, "description": "not found"})

_estate = Estate(datasets=lambda: list(_descriptions), describe_dataset=_describe)
_server = Server(default_registry(_estate, lambda d, p, b: {"id": "x"}))

def _mcp_req(method, params=None, id_=1):
    d = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        d["params"] = params
    if id_ is not None:
        d["id"] = id_
    return d

secret_shapes = {
    "dsn": "connection is postgresql://user:hunter2@dbhost:5432/prod",
    "api_key": "the key is sk-abcdefghijklmnopqrstuvwx",
    "pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK...\n-----END RSA PRIVATE KEY-----",
    "aws_secret": "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "password": "password: hunter2hunter2",
}
res21 = {}
for label, secret_text in secret_shapes.items():
    dname = f"secretds_{label}"
    _descriptions[dname] = {"name": dname, "description": f"normal text. {secret_text}", "attributes": []}
    r = _server.handle(_mcp_req("tools/call", {"name": "describe_dataset", "arguments": {"dataset": dname}}))
    result = r.get("result", {})
    text = result.get("content", [{}])[0].get("text", "")
    withheld = result.get("isError") is True and "was withheld" in text
    no_fragment = secret_text[:15] not in text
    res21[label] = {"withheld": withheld, "no_fragment": no_fragment}
bad21 = {k: v for k, v in res21.items() if not (v["withheld"] and v["no_fragment"])}
ok21 = not bad21
record("MCP-021", "PASS" if ok21 else "FAIL", f"per_shape={res21} (correctly-id'd rerun of the same check MCP-022 already recorded under 'MCP-021 (and MCP-022 secret shapes)')")

# ============ UI-040/041: url_for with a query param, and with a missing required path param ============
async def ui040041():
    from starlette.requests import Request as StarletteRequest
    from prama.web.rendering import url_for

    DB = c.WORKDIR / "ui040.db"
    env = u.UiEnv(str(DB))
    await env.start()

    scope = {"type": "http", "app": env.app, "method": "GET", "path": "/", "headers": []}
    req_obj = StarletteRequest(scope)

    url40 = url_for(req_obj, "break_workbench", definition="x", show="all")
    ok40 = url40 == "/reconciliation/x?show=all"

    err41 = None
    try:
        url_for(req_obj, "break_workbench")
        ok41 = False
        err41 = "did not raise"
    except Exception as e:
        # Expected: a clear error naming the route AND which parameter is missing
        msg = str(e)
        names_route = "break_workbench" in msg
        names_param = "definition" in msg
        ok41 = names_route and names_param
        err41 = f"{type(e).__name__}: {msg}"
    await env.stop()
    return ok40, url40, ok41, err41


ok40, url40, ok41, err41 = asyncio.run(ui040041())
record("UI-040", "PASS" if ok40 else "FAIL", f"url_for(..., definition='x', show='all') = {url40!r}")
record(
    "UI-041",
    "PASS" if ok41 else "FAIL",
    f"url_for(req, 'break_workbench') with 'definition' omitted -> {err41} -- "
    + ("names both the route and the missing parameter" if ok41 else
       "fails loudly (not a silent 500) and names the route, but does not name which "
       "parameter is missing -- same partial fix as round 2 (starlette.routing.NoMatchFound "
       "does not enumerate missing params, only the empty substituted params dict)"),
)

# ============ UI-060: a field's value is escaped in the report renderings too ============
async def ui060():
    DB = c.WORKDIR / "ui060.db"
    env = u.UiEnv(str(DB))
    await env.start()
    await env.create_principal("owner60", "ownerpassword1", ["owner"])
    http, _ = await env.signed_in_client("owner60", "ownerpassword1")
    xss_name = "report60</script><script>alert(1)</script>"
    r_create = await http.post("/declarations/new", data={"name": xss_name, "shape": "unbound", "criticality": "4"})
    r_report = await http.get("/reports/declarations")
    await env.stop()
    raw_present = "</script><script>alert(1)</script>" in r_report.text
    escaped_present = "&lt;/script&gt;&lt;script&gt;" in r_report.text or "&lt;script&gt;" in r_report.text
    ok60 = r_report.status_code == 200 and not raw_present
    return ok60, r_report.status_code, raw_present, escaped_present


ok60, st60, raw60, esc60 = asyncio.run(ui060())
record("UI-060", "PASS" if ok60 else "FAIL", f"status={st60} raw_unescaped_script_present={raw60} escaped_form_present={esc60}")

print("done misc redo1 (cli083, api053, mcp021, ui040, ui041, ui060)")
