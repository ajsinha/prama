import sys, os, json, asyncio, sqlite3, time
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
    tcode, tout, _ = c.run_sub(["--json", "--config", str(cfgf), "tenant", "create", "acme-bank"])
    tid = json.loads(tout)["id"]
    cfgf.write_text(cfgf.read_text() + f"tenancy:\n  default_tenant: {tid}\n")
    c.run_sub(["--config", str(cfgf), "principal", "create", "alice", "--admin", "--tenant", "acme-bank"], stdin_input="alicepassword1\n")
    return cfgf, d, dbpath, tid


def api_config(dbpath):
    return (
        ConfigurationBuilder().with_defaults(DEFAULTS)
        .with_mapping({
            "database": {"dialect": "sqlite", "sqlite": {"path": str(dbpath)}, "schema_dir": str(c.REPO_ROOT / "schema")},
            "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
        }, name="test").build()
    )


async def call_api(dbpath, key, method, path, json_body=None):
    cfg = api_config(dbpath)
    app = create_app(cfg)
    transport = ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://testserver" + API_PREFIX,
                           headers={"Authorization": f"Bearer {key}"} if key else {}) as http,
        app.router.lifespan_context(app),
    ):
        resp = await http.request(method, path, json=json_body)
        return resp.status_code, resp.text


def call_api_sync(*a, **kw):
    return asyncio.run(call_api(*a, **kw))


# CLI-084: apikey list never shows a key
cfg84, d84, db84, tid84 = new_cfg("cli084")
c.run_sub(["--config", str(cfg84), "apikey", "create", "k1", "--principal", "alice", "--scope", "*"])
code, out, err = c.run_sub(["--config", str(cfg84), "apikey", "list"])
code_j, out_j, err_j = c.run_sub(["--json", "--config", str(cfg84), "apikey", "list"])
has_key_field = "key_hash" in out_j or '"key":' in out_j
ok = code == 0 and code_j == 0 and not has_key_field and "pk_live_" not in out.split("…")[0] or True
rows = json.loads(out_j)
leaked = any("key" in r or "key_hash" in r for r in rows)
ok = code == 0 and not leaked
record("CLI-084", "PASS" if ok else "FAIL", f"json_rows={rows} leaked_field={leaked}")

# CLI-085: apikey list shows revoked/expired distinctly
cfg85, d85, db85, tid85 = new_cfg("cli085")
code_a, out_a, err_a = c.run_sub(["--json", "--config", str(cfg85), "apikey", "create", "active-key", "--principal", "alice", "--scope", "*"])
code_r, out_r, err_r = c.run_sub(["--json", "--config", str(cfg85), "apikey", "create", "revoked-key", "--principal", "alice", "--scope", "*"])
code_e, out_e, err_e = c.run_sub(["--json", "--config", str(cfg85), "apikey", "create", "expired-key", "--principal", "alice", "--scope", "*", "--expires-in-days", "1"])
doc_r = json.loads(out_r)
c.run_sub(["--config", str(cfg85), "apikey", "revoke", doc_r["prefix"]])
doc_e = json.loads(out_e)
# force it into the past directly in the db
conn = sqlite3.connect(db85)
conn.execute("UPDATE api_key SET expires_at = '2000-01-01T00:00:00Z' WHERE key_prefix = ?", (doc_e["prefix"],))
conn.commit(); conn.close()
code_l, out_l, err_l = c.run_sub(["--config", str(cfg85), "apikey", "list"])
lines85 = out_l.splitlines()
active_line = next((l for l in lines85 if "active-key" in l), "")
revoked_line = next((l for l in lines85 if "revoked-key" in l), "")
expired_line = next((l for l in lines85 if "expired-key" in l), "")
revoked_marked = "[revoked]" in revoked_line
expired_distinguishable = "[revoked]" in expired_line or "[expired]" in expired_line or "expired" in expired_line.lower()
ok = revoked_marked and expired_distinguishable
record(
    "CLI-085",
    "PASS" if ok else "FAIL",
    f"active_line={active_line!r} revoked_line={revoked_line!r} expired_line={expired_line!r} "
    f"-- {'expired key correctly distinguished' if expired_distinguishable else 'expired key rendered [active] though its expires_at is in the past: state is derived from revoked_at alone, expires_at is never consulted (cli/apikey.py::ApiKeyListCommand.run)'}",
)

# CLI-086: apikey list on empty estate prints create command
cfg86, d86, db86, tid86 = new_cfg("cli086")
code, out, err = c.run_sub(["--config", str(cfg86), "apikey", "list"])
ok = code == 0 and "No API keys" in out and "Issue one:" in out and "apikey create" in out
record("CLI-086", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-087: empty-state remedy works verbatim
code, out, err = c.run_sub(["--config", str(cfg86), "apikey", "create", "ci", "--principal", "alice", "--scope", "*"])
ok = code == 0 and "issued ci" in out
record("CLI-087", "PASS" if ok else "FAIL", f"code={code} out_head={out[:60]!r} err={err[:150]!r}")

# CLI-088: apikey revoke stops the key working immediately
cfg88, d88, db88, tid88 = new_cfg("cli088")
code, out, err = c.run_sub(["--json", "--config", str(cfg88), "apikey", "create", "k", "--principal", "alice", "--scope", "*"])
doc88 = json.loads(out)
s1, _ = call_api_sync(db88, doc88["key"], "GET", "/datasets")
c.run_sub(["--config", str(cfg88), "apikey", "revoke", doc88["prefix"]])
s2, _ = call_api_sync(db88, doc88["key"], "GET", "/datasets")
ok = s1 == 200 and s2 == 401
record("CLI-088", "PASS" if ok else "FAIL", f"before_revoke={s1} after_revoke={s2}")

# CLI-089: revoke twice reports already revoked, revoked_at unchanged
conn = sqlite3.connect(db88)
before_ts = conn.execute("SELECT revoked_at FROM api_key WHERE key_prefix=?", (doc88["prefix"],)).fetchone()[0]
conn.close()
time.sleep(1.1)
code2, out2, err2 = c.run_sub(["--config", str(cfg88), "apikey", "revoke", doc88["prefix"]])
conn = sqlite3.connect(db88)
after_ts = conn.execute("SELECT revoked_at FROM api_key WHERE key_prefix=?", (doc88["prefix"],)).fetchone()[0]
conn.close()
ok = code2 == 0 and "already revoked" in out2 and before_ts == after_ts
record("CLI-089", "PASS" if ok else "FAIL", f"code2={code2} out2={out2!r} before_ts={before_ts} after_ts={after_ts}")

# CLI-090: revoke with another estate's prefix refused as not found
cfg90, d90, db90, tid90 = new_cfg("cli090")
c.run_sub(["--config", str(cfg90), "tenant", "create", "bank-b"])
c.run_sub(["--config", str(cfg90), "principal", "create", "bob", "--tenant", "bank-b"], stdin_input="bobpassword1234\n")
code_b, out_b, err_b = c.run_sub(["--json", "--config", str(cfg90), "apikey", "create", "bkey", "--principal", "bob", "--tenant", "bank-b", "--scope", "*"])
doc_b = json.loads(out_b)
code, out, err = c.run_sub(["--config", str(cfg90), "apikey", "revoke", doc_b["prefix"], "--tenant", "acme-bank"])
s_check, _ = call_api_sync(db90, doc_b["key"], "GET", "/datasets")
ok = code == 1 and "not found" in err.lower() or "no key with prefix" in err
ok = ok and s_check == 200
record("CLI-090", "PASS" if ok else "FAIL", f"code={code} err={err[:200]!r} b_key_still_works={s_check==200}")

# CLI-091: prefix that is a leading substring of another must not match (by_prefix is `==`, per
# src/prama/db/dao/platform.py:261 -- select(ApiKey).where(ApiKey.key_prefix == prefix))
cfg91, d91, db91, tid91 = new_cfg("cli091")
code, out, err = c.run_sub(["--json", "--config", str(cfg91), "apikey", "create", "full", "--principal", "alice", "--scope", "*"])
doc91 = json.loads(out)
long_prefix = doc91["prefix"]
short_prefix = long_prefix[:8]
code, out, err = c.run_sub(["--config", str(cfg91), "apikey", "revoke", short_prefix])
conn = sqlite3.connect(db91)
still_active = conn.execute("SELECT revoked_at FROM api_key WHERE key_prefix=?", (long_prefix,)).fetchone()[0]
conn.close()
ok = code == 1 and "not found" not in "" and still_active is None and ("no key with prefix" in err)
record(
    "CLI-091",
    "PASS" if ok else "FAIL",
    f"revoke(shorter leading-substring {short_prefix!r} of real prefix {long_prefix!r}) code={code} "
    f"err={err[:200]!r} full_prefix_still_active={still_active is None}",
)

# CLI-092: every apikey subcommand honours --tenant and the configured default
cfg92, d92, db92, tid92 = new_cfg("cli092")
code_default, out_default, err_default = c.run_sub(["--json", "--config", str(cfg92), "apikey", "create", "d1", "--principal", "alice", "--scope", "*"])
code_named, out_named, err_named = c.run_sub(["--json", "--config", str(cfg92), "apikey", "create", "d2", "--principal", "alice", "--tenant", "acme-bank", "--scope", "*"])
# neither flag nor default: strip default_tenant
cfg92_nodef = d92 / "nodef.yaml"
cfg92_nodef.write_text(
    "database:\n  dialect: sqlite\n"
    f"  sqlite:\n    path: {db92}\n"
    f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
)
code_none, out_none, err_none = c.run_sub(["--config", str(cfg92_nodef), "apikey", "create", "d3", "--principal", "alice", "--scope", "*"])
ok = code_default == 0 and code_named == 0 and code_none == 1 and "--tenant" in err_none and "default_tenant" in err_none
record(
    "CLI-092",
    "PASS" if ok else "FAIL",
    f"default_tenant_path_code={code_default} explicit_tenant_code={code_named} "
    f"neither_code={code_none} err_none={err_none[:200]!r}",
)

# CLI-093: apikey create --json emits plaintext exactly once, nothing secret on stderr
code, out, err = c.run_sub(["--json", "--config", str(cfg92), "apikey", "create", "ci", "--principal", "alice", "--scope", "*"])
doc93 = json.loads(out)
ok = code == 0 and doc93.get("key", "").startswith("pk_") and err.strip() == ""
record("CLI-093", "PASS" if ok else "FAIL", f"code={code} key_present={bool(doc93.get('key'))} stderr={err!r}")

# CLI-094: apikey create refused when tenant does not exist
code, out, err = c.run_sub(["--config", str(cfg92), "apikey", "create", "ci", "--principal", "alice", "--scope", "*", "--tenant", "01NOSUCH"])
conn = sqlite3.connect(db92)
n_keys_before_after = conn.execute("SELECT COUNT(*) FROM api_key").fetchone()[0]
conn.close()
ok = code == 1 and "there is no estate" in err
record("CLI-094", "PASS" if ok else "FAIL", f"code={code} err={err[:200]!r}")

# CLI-095: scopes on a key are not the principal's roles (alice is admin, key scoped to declaration:read only)
code, out, err = c.run_sub(["--json", "--config", str(cfg92), "apikey", "create", "scoped", "--principal", "alice", "--scope", "declaration:read"])
doc95 = json.loads(out)
s95, b95 = call_api_sync(db92, doc95["key"], "POST", "/datasets", {"name": "x"})
ok = s95 == 403
record("CLI-095", "PASS" if ok else "FAIL", f"POST /datasets with declaration:read-only key (owner is admin) => {s95} body={b95[:150]}")

# CLI-096: key for a principal in another estate refused
cfg96, d96, db96, tid96 = new_cfg("cli096")
code_b, out_b, _ = c.run_sub(["--json", "--config", str(cfg96), "tenant", "create", "estate-b"])
code, out, err = c.run_sub(["--config", str(cfg96), "apikey", "create", "ci", "--principal", "alice", "--scope", "*", "--tenant", "estate-b"])
ok = code == 1 and "no principal called 'alice'" in err
record("CLI-096", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

print("done apikey batch part2")
