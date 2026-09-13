import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "contract3"
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
                    await svc.declare_attribute(
                        tenant_id=tenant_id, dataset_id=str(entity.id), name=attr_name, is_cde=is_cde, authored_by="alice"
                    )
                await uow.flush()
                return version.slug
        finally:
            await db.stop()

    return asyncio.run(go())


# CLI-170/171/172/173 setup
cfg170, d170, db170, tid170 = new_cfg("cli170")
slug = declare_dataset(db170, tid170, "Positions EOD", [("account_id", True), ("notional", True)])

# CLI-170: contract export writes a document that re-imports
outc = d170 / "exported.json"
code, out, err = c.run_sub(["--config", str(cfg170), "contract", "export", slug, "--out", str(outc)])
file_ok = outc.is_file()
code2, out2, err2 = c.run_sub(["--config", str(cfg170), "contract", "import", str(outc)])
ok = code == 0 and file_ok and code2 == 0
record("CLI-170", "PASS" if ok else "FAIL", f"export_code={code} file_ok={file_ok} reimport_code={code2} reimport_out={out2[:200]!r} err={err[:150]!r} err2={err2[:150]!r}")

# CLI-171: contract export for an undeclared slug
code, out, err = c.run_sub(["--config", str(cfg170), "contract", "export", "no-such-dataset"])
ok = code == 1 and "prama estate export" in err
record("CLI-171", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

# CLI-172: the remedy names a command that produces slugs -- 'estate export' requires --tenant
# explicitly (it does not fall back to tenancy.default_tenant the way most other commands do),
# so it must be passed for this case to reach the actual output being tested at all.
code, out, err = c.run_sub(["--config", str(cfg170), "estate", "export", "--tenant", tid170])
ok = code == 0 and slug in out
record("CLI-172", "PASS" if ok else "FAIL", f"code={code} slug_findable={slug in out} out_head={out[:200]!r} err={err[:200]!r}")

# CLI-173: contract export reads only its own tenant
cfg173, d173, db173, tid173 = new_cfg("cli173")
c.run_sub(["--config", str(cfg173), "tenant", "create", "bank-b"])
code_tb, out_tb, _ = c.run_sub(["--json", "--config", str(cfg173), "tenant", "list"])
tenants = json.loads(out_tb)["tenants"]
tid_a = tid173
tid_b = next(t["id"] for t in tenants if t["slug"] == "bank-b")
slug_a = declare_dataset(db173, tid_a, "shared-name", [("field_a", False)])
slug_b = declare_dataset(db173, tid_b, "shared-name", [("field_b", False)])
code_a, out_a, _ = c.run_sub(["--config", str(cfg173), "contract", "export", slug_a, "--tenant", tid_a])
code_b, out_b, _ = c.run_sub(["--config", str(cfg173), "contract", "export", slug_b, "--tenant", tid_b])
ok = code_a == 0 and code_b == 0 and "field_a" in out_a and "field_b" not in out_a and "field_b" in out_b and "field_a" not in out_b
record("CLI-173", "PASS" if ok else "FAIL", f"slug_a=={slug_a==slug_b} field_a_in_a={'field_a' in out_a} field_b_leaked_into_a={'field_b' in out_a}")

print("done contract batch part2b (export)")
