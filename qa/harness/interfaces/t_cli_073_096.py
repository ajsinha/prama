import sys, os, json, asyncio, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

import httpx
from httpx import ASGITransport
from prama.api import API_PREFIX, create_app
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS


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
    c.run_sub(["--config", str(cfgf), "db", "init"])
    tcode, tout, terr = c.run_sub(["--json", "--config", str(cfgf), "tenant", "create", "acme-bank"])
    tid = json.loads(tout)["id"]
    cfgf.write_text(cfgf.read_text() + f"tenancy:\n  default_tenant: {tid}\n")
    c.run_sub(["--config", str(cfgf), "principal", "create", "alice", "--admin", "--tenant", "acme-bank"], stdin_input="alicepassword1\n")
    return cfgf, d, dbpath


def api_config(dbpath):
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(dbpath)},
                    "schema_dir": str(c.REPO_ROOT / "schema"),
                },
                "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
            },
            name="test",
        )
        .build()
    )


async def call_api(dbpath, key, method, path, json_body=None):
    cfg = api_config(dbpath)
    app = create_app(cfg)
    transport = ASGITransport(app=app)
    async with (
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver" + API_PREFIX,
            headers={"Authorization": f"Bearer {key}"} if key else {},
        ) as http,
        app.router.lifespan_context(app),
    ):
        resp = await http.request(method, path, json=json_body)
        return resp.status_code, resp.text


def call_api_sync(*a, **kw):
    return asyncio.run(call_api(*a, **kw))


# CLI-073: key printed once, not recoverable
cfg73, d73, db73 = new_cfg("cli073")
code, out, err = c.run_sub(["--config", str(cfg73), "apikey", "create", "ci", "--principal", "alice", "--scope", "declaration:read"])
print("CLI-073 raw create out:", repr(out), "err:", repr(err[:200]))
key = None
for line in out.splitlines():
    ln = line.strip()
    if len(ln) > 20 and " " not in ln:
        key = ln
        break
code_l, out_l, err_l = c.run_sub(["--json", "--config", str(cfg73), "apikey", "list"])
rows = json.loads(out_l)
row_text = json.dumps(rows)
conn = sqlite3.connect(db73)
db_cols = [r[1] for r in conn.execute("PRAGMA table_info(api_key)").fetchall()]
db_row = conn.execute("SELECT * FROM api_key").fetchone()
db_text = str(dict(zip(db_cols, db_row))) if db_row else ""
conn.close()
ok = (
    code == 0 and key is not None and len(key) > 10
    and "key" not in row_text.lower().replace("key_prefix", "").replace("id", "")
    and key not in db_text
)
record(
    "CLI-073",
    "PASS" if ok else "FAIL",
    f"key_found_in_create_output={key is not None} key_absent_from_list_json={key not in row_text if key else '?'} "
    f"key_absent_from_db_row={key not in db_text if key else '?'} list_row={rows}",
)

# CLI-074: no --scope refused
cfg74, d74, db74 = new_cfg("cli074")
code, out, err = c.run_sub(["--config", str(cfg74), "apikey", "create", "ci", "--principal", "alice"])
ok = code == 1 and "scope" in err.lower()
record("CLI-074", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

# CLI-075: invented scope named, good one not
code, out, err = c.run_sub(["--config", str(cfg74), "apikey", "create", "ci", "--principal", "alice", "--scope", "declaration:read", "--scope", "wizard:everything"])
ok = code == 1 and "wizard:everything" in err and "declaration:read" not in err.split("next:")[0]
record("CLI-075", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

# CLI-076: --scope '*' works for a route in each family
cfg76, d76, db76 = new_cfg("cli076")
code, out, err = c.run_sub(["--json", "--config", str(cfg76), "apikey", "create", "ci", "--principal", "alice", "--scope", "*"])
doc = json.loads(out)
key76 = doc["key"]
s1, b1 = call_api_sync(db76, key76, "GET", "/datasets")
s2, b2 = call_api_sync(db76, key76, "GET", "/relationships")
ok = code == 0 and s1 == 200 and s2 == 200
record("CLI-076", "PASS" if ok else "FAIL", f"GET /datasets={s1} GET /relationships={s2}")

# CLI-077: one-level wildcard accepted, honoured for read+write of that family
cfg77, d77, db77 = new_cfg("cli077")
code, out, err = c.run_sub(["--json", "--config", str(cfg77), "apikey", "create", "ci", "--principal", "alice", "--scope", "declaration:*"])
ok_create = code == 0
doc = json.loads(out) if code == 0 else {}
key77 = doc.get("key")
s_read, _ = call_api_sync(db77, key77, "GET", "/datasets") if key77 else (None, None)
s_write, b_write = call_api_sync(db77, key77, "POST", "/datasets", {"name": "x", "domain": "x", "kind": "table", "owner_principal_id": "x"}) if key77 else (None, None)
ok = ok_create and s_read == 200 and s_write in (200, 201, 400, 422)  # 400/422 acceptable (validation), 403 would mean scope not honoured
record(
    "CLI-077",
    "PASS" if ok else "FAIL",
    f"create_accepted={ok_create} GET/datasets={s_read} POST/datasets={s_write} body={b_write[:150] if b_write else ''}",
)

# CLI-078: --principal required and must exist
code, out, err = c.run_sub(["--config", str(cfg74), "apikey", "create", "ci", "--scope", "*"])
ok1 = code == 2 and "principal" in err.lower()
code2, out2, err2 = c.run_sub(["--config", str(cfg74), "apikey", "create", "ci", "--principal", "nobody", "--scope", "*"])
ok2 = code2 == 1 and "principal create" in err2
ok = ok1 and ok2
record("CLI-078", "PASS" if ok else "FAIL", f"missing_flag: code={code} err={err[:150]!r} | unknown_principal: code={code2} err={err2[:250]!r}")

# CLI-079: --expires-in-days 0 means never
code, out, err = c.run_sub(["--config", str(cfg74), "apikey", "create", "ci2", "--principal", "alice", "--scope", "*"])
ok = code == 0 and "expires: never" in out
record("CLI-079", "PASS" if ok else "FAIL", f"code={code} out_line={[l for l in out.splitlines() if 'expires' in l]}")

# CLI-080: negative expiry
code, out, err = c.run_sub(["--json", "--config", str(cfg74), "apikey", "create", "ci3", "--principal", "alice", "--scope", "*", "--expires-in-days", "-1"])
if code == 0:
    doc = json.loads(out)
    key80 = doc["key"]
    s80, _ = call_api_sync(db74, key80, "GET", "/datasets")
    ok = s80 == 401
    obs = f"created (code=0), then API call with it => {s80} (expect 401 if created)"
else:
    ok = True
    obs = f"refused at creation: code={code} err={err[:150]!r}"
record("CLI-080", "PASS" if ok else "FAIL", obs)

# CLI-081: very large expires-in-days
code, out, err = c.run_sub(["--config", str(cfg74), "apikey", "create", "ci4", "--principal", "alice", "--scope", "*", "--expires-in-days", "3650000"])
ok = code in (0, 1) and "Traceback" not in err and "OverflowError" not in err
record("CLI-081", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-082: --environment changes prefix tag
code, out, err = c.run_sub(["--json", "--config", str(cfg74), "apikey", "create", "envtest", "--principal", "alice", "--scope", "*", "--environment", "test"])
doc_t = json.loads(out)
code2, out2, err2 = c.run_sub(["--json", "--config", str(cfg74), "apikey", "create", "envlive", "--principal", "alice", "--scope", "*"])
doc_l = json.loads(out2)
s_t, _ = call_api_sync(db74, doc_t["key"], "GET", "/datasets")
s_l, _ = call_api_sync(db74, doc_l["key"], "GET", "/datasets")
ok = doc_t["prefix"] != doc_l["prefix"] and s_t == 200 and s_l == 200
record("CLI-082", "PASS" if ok else "FAIL", f"prefix_test={doc_t['prefix']} prefix_live={doc_l['prefix']} auth_test={s_t} auth_live={s_l}")

# CLI-083: --environment with separators — must be refused, or sanitised so the prefix stays unambiguous
bad83 = {}
for envval in ["live_pk", "", "../x"]:
    code, out, err = c.run_sub(["--json", "--config", str(cfg74), "apikey", "create", "envsep", "--principal", "alice", "--scope", "*", "--environment", envval])
    if code == 0:
        doc = json.loads(out)
        bad83[repr(envval)] = f"ACCEPTED prefix={doc['prefix']!r}"
    else:
        bad83[repr(envval)] = f"refused: {err.strip().splitlines()[1] if len(err.strip().splitlines())>1 else err[-100:]}"
print("CLI-083 raw:", bad83)

print("done apikey batch part1")
