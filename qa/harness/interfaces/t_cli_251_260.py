import sys, os, json, subprocess
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "lsp"
WORK.mkdir(exist_ok=True, parents=True)


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
    return cfgf, d, dbpath, tid


def declare_dataset(app_dbpath, tenant_id, name, attributes):
    import asyncio
    from prama.core.config import ConfigurationBuilder
    from prama.core.config.defaults import DEFAULTS
    from prama.db import Database
    from prama.semantic.services import DatasetService

    cfg = (
        ConfigurationBuilder().with_defaults(DEFAULTS)
        .with_mapping({"database": {"dialect": "sqlite", "sqlite": {"path": str(app_dbpath)}, "schema_dir": str(c.REPO_ROOT / "schema")}}, name="t")
        .build()
    )

    async def go():
        db = Database.from_config(cfg)
        await db.start()
        try:
            async with db.unit_of_work() as uow:
                svc = DatasetService(uow)
                entity, version = await svc.declare(tenant_id=tenant_id, name=name, authored_by="alice")
                for attr_name, is_cde in attributes:
                    await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(entity.id), name=attr_name, is_cde=is_cde, authored_by="alice")
                await uow.flush()
                return version.slug
        finally:
            await db.stop()

    return asyncio.run(go())


cfg251, d251, db251, tid251 = new_cfg("cli251")
declare_dataset(db251, tid251, "Positions EOD", [("account_id", True), ("notional", True)])
out251 = d251 / "cat.json"

# CLI-251: lsp catalogue writes a file with timestamp and tenant
code, out, err = c.run_sub(["--config", str(cfg251), "lsp", "catalogue", "--tenant", tid251, "--out", str(out251)])
doc = json.loads(out251.read_text()) if out251.exists() else {}
has_fields = "written_at" in doc and "tenant" in doc and "datasets" in doc
claimed = None
for tok in out.split():
    if tok.rstrip(",").isdigit():
        claimed = int(tok.rstrip(","))
        break
ok = code == 0 and has_fields and len(doc.get("datasets", {})) == 1
record("CLI-251", "PASS" if ok else "FAIL", f"code={code} out={out!r} doc_keys={list(doc.keys())} n_datasets={len(doc.get('datasets', {}))}")

# CLI-252: lsp catalogue on empty estate
cfg252, d252, db252, tid252 = new_cfg("cli252")
out252 = d252 / "cat.json"
code, out, err = c.run_sub(["--config", str(cfg252), "lsp", "catalogue", "--tenant", tid252, "--out", str(out252)])
ok = code == 0 and out252.exists() and "statement about the estate" in out
record("CLI-252", "PASS" if ok else "FAIL", f"code={code} out={out!r} file_written={out252.exists()}")

# CLI-253: --out to an unwritable path, after db work already done
code, out, err = c.run_sub(["--config", str(cfg251), "lsp", "catalogue", "--tenant", tid251, "--out", "/proc/cat.json"])
ok = code == 1 and "Traceback" not in err
record("CLI-253", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:300]!r}")

# CLI-254: lsp catalogue with no tenant refuses
cfg254 = d251 / "nodef.yaml"
cfg254.write_text(f"database:\n  dialect: sqlite\n  sqlite:\n    path: {db251}\n  schema_dir: {c.REPO_ROOT/'schema'}\n")
code, out, err = c.run_sub(["--config", str(cfg254), "lsp", "catalogue"])
ok = code == 1 and "--tenant" in err and "default_tenant" in err
record("CLI-254", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-255: lsp serve banner to stderr never stdout
proc = subprocess.run(["prama", "lsp", "serve"], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.stdout == b"" and b"prama lsp:" in proc.stderr
record("CLI-255", "PASS" if ok else "FAIL", f"returncode={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr[:200]!r}")

# CLI-256: lsp serve --catalogue missing file is a refusal, server does not start
proc = subprocess.run(["prama", "lsp", "serve", "--catalogue", str(WORK / "nope.json")], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.returncode == 1 and b"nope.json" in proc.stderr and proc.stdout == b""
record("CLI-256", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr[:300]!r} stdout={proc.stdout!r}")

# CLI-257: lsp serve --catalogue with unparsable JSON
truncated = WORK / "truncated.json"
truncated.write_text('{"datasets": {"x":')
proc = subprocess.run(["prama", "lsp", "serve", "--catalogue", str(truncated)], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.returncode == 1 and b"not readable as a catalogue" in proc.stderr
record("CLI-257", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr[:300]!r}")

# CLI-258: lsp serve --catalogue with no datasets key
nodskey = WORK / "nodskey.json"
nodskey.write_text('{"written_at": "2026-01-01T00:00:00Z"}')
proc = subprocess.run(["prama", "lsp", "serve", "--catalogue", str(nodskey)], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.returncode == 1 and b"no 'datasets' object" in proc.stderr
record("CLI-258", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr[:300]!r}")

# CLI-259: lsp serve --catalogue where a dataset maps to null
nullds = WORK / "nullds.json"
nullds.write_text('{"datasets": {"trades": null}}')
proc = subprocess.run(["prama", "lsp", "serve", "--catalogue", str(nullds)], input=b"", capture_output=True, timeout=60, env=os.environ)
ok = proc.returncode == 0 and b"1 dataset(s)" in proc.stderr and b"Traceback" not in proc.stderr
record("CLI-259", "PASS" if ok else "FAIL", f"rc={proc.returncode} stderr={proc.stderr[:300]!r}")

# CLI-260: the lsp catalogue remedy works verbatim: run it, start the server with the result
code, out, err = c.run_sub(["--config", str(cfg251), "lsp", "catalogue", "--tenant", tid251], cwd=str(d251))
default_cat = d251 / "prama-catalogue.json"
proc = subprocess.run(["prama", "lsp", "serve", "--catalogue", str(default_cat)], input=b"", capture_output=True, timeout=60, env=os.environ, cwd=str(d251))
ok = code == 0 and default_cat.exists() and proc.returncode == 0 and b"dataset(s)" in proc.stderr
record("CLI-260", "PASS" if ok else "FAIL", f"catalogue_code={code} file_exists={default_cat.exists()} serve_rc={proc.returncode} serve_stderr={proc.stderr[:200]!r}")

print("done lsp batch")
