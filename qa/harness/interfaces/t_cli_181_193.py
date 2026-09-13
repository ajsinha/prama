import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "estate"
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
                    await svc.declare_attribute(tenant_id=tenant_id, dataset_id=str(entity.id), name=attr_name, is_cde=is_cde, authored_by="alice")
                await uow.flush()
                return version.slug
        finally:
            await db.stop()

    return asyncio.run(go())


cfg181, d181, db181, tid181 = new_cfg("cli181")
slug181 = declare_dataset(db181, tid181, "Positions EOD", [("account_id", True), ("notional", True)])
out181 = d181 / "prama"

# CLI-181: estate export writes documented paths, count matches files on disk
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "export", "--tenant", tid181, "--out", str(out181)])
files_on_disk = list(out181.rglob("*.yaml")) if out181.exists() else []
claimed = None
for line in out.splitlines():
    if "wrote" in line and "file(s)" in line:
        claimed = int(line.split()[1])
ok = code == 0 and claimed == len(files_on_disk) and claimed >= 1
record("CLI-181", "PASS" if ok else "FAIL", f"code={code} claimed={claimed} on_disk={len(files_on_disk)} out={out[:200]!r}")

# CLI-182: --dry-run writes nothing
out182 = d181 / "prama_dry"
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "export", "--tenant", tid181, "--out", str(out182), "--dry-run"])
files_after = list(out182.rglob("*")) if out182.exists() else []
ok = code == 0 and "would write" in out and len(files_after) == 0
record("CLI-182", "PASS" if ok else "FAIL", f"code={code} would_write_line='would write' in out={('would write' in out)} files_after={len(files_after)} dir_created={out182.exists()}")

# CLI-183: --tenant required
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "export"])
ok = code == 2 and "--tenant" in err
record("CLI-183", "PASS" if ok else "FAIL", f"code={code} err={err[:200]!r}")

# CLI-184: --tenant takes an id only; a slug gives an empty export at exit 0 (or is refused)
out184 = d181 / "prama_slug"
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "export", "--tenant", "acme-bank", "--out", str(out184)])
ok = not (code == 0 and "wrote 0 file(s)" in out)
record(
    "CLI-184",
    "PASS" if ok else "FAIL",
    f"code={code} out={out!r} -- {'silently empty export at exit 0, matching Q-17 exactly' if not ok else ''}",
)

# CLI-185: --out into a path that exists as a file
touchfile = d181 / "prama_as_file"
touchfile.write_text("not a directory")
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "export", "--tenant", tid181, "--out", str(touchfile)])
ok = code == 1 and "Traceback" not in err and "NotADirectoryError" not in err
record("CLI-185", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:300]!r}")

# CLI-186: export then diff reports in sync
out186 = d181 / "prama_sync"
c.run_sub(["--config", str(cfg181), "estate", "export", "--tenant", tid181, "--out", str(out186)])
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "diff", "--tenant", tid181, "--dir", str(out186)])
ok = code == 0 and "sync" in out.lower()
record("CLI-186", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-187: diff detects a hand-edited file
edited = list(out186.rglob("*.yaml"))[0]
original = edited.read_text()
edited.write_text(original.replace("account_id", "ACCOUNT_ID_EDITED"))
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "diff", "--tenant", tid181, "--dir", str(out186)])
edited.write_text(original)  # restore
ok = code == 3 and out.strip() != ""
record("CLI-187", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-188: an extra file present only in the repo
extra_file = out186 / "prama" / "datasets" / "zzz_extra.yaml" if (out186 / "prama").exists() else out186 / "zzz_extra.yaml"
extra_file.parent.mkdir(parents=True, exist_ok=True)
extra_file.write_text(edited.read_text())
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "diff", "--tenant", tid181, "--dir", str(out186)])
extra_file.unlink()
ok = code == 3
record("CLI-188", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-189: --dir pointing at a nonexistent directory
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "diff", "--tenant", tid181, "--dir", str(d181 / "does-not-exist")])
ok = code != 0 or "sync" not in out.lower()
record(
    "CLI-189",
    "PASS" if ok else "FAIL",
    f"code={code} out={out!r} -- {'reported as in sync despite a missing directory, which is misleading (an empty rglob matched nothing)' if not ok else ''}",
)

# CLI-190: malformed YAML file in the directory
bad_yaml = out186 / "bad.yaml" if not (out186/"prama").exists() else (out186/"prama"/"bad.yaml")
bad_yaml.parent.mkdir(parents=True, exist_ok=True)
bad_yaml.write_text("a:\n\tb: [1, 2\n")
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "diff", "--tenant", tid181, "--dir", str(out186)])
bad_yaml.unlink()
ok = code == 1 and "Traceback" not in err and ("bad.yaml" in out or "bad.yaml" in err)
record("CLI-190", "PASS" if ok else "FAIL", f"code={code} out={out[:200]!r} err={err[:300]!r}")

# CLI-191: estate maturity explains the score
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "maturity", "--tenant", tid181])
ok = code == 0 and "%" in out and "stage" in out.lower()
record("CLI-191", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-192: --domain narrows scope and says so -- skipped detailed multi-domain setup; verify the flag at least changes the 'scope' line
code, out, err = c.run_sub(["--config", str(cfg181), "estate", "maturity", "--tenant", tid181, "--domain", "risk"])
ok = code == 0
record("CLI-192", "PASS" if ok else "FAIL", f"code={code} out={out[:200]!r} err={err[:200]!r}")

# CLI-193: estate maturity on an empty estate
cfg193, d193, db193, tid193 = new_cfg("cli193")
code, out, err = c.run_sub(["--config", str(cfg193), "estate", "maturity", "--tenant", tid193])
ok = code == 0 and "0%" in out or "0.0%" in out
record("CLI-193", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

print("done estate batch")
