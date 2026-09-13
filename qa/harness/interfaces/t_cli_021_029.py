import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

from prama.version import PRODUCT_NAME, VERSION, IR_VERSION, SCHEMA_VERSION

# CLI-021
code, out, err = c.run(["version"])
ok = code == 0 and VERSION in out and IR_VERSION in out and SCHEMA_VERSION in out and PRODUCT_NAME in out
record("CLI-021", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-022
code, out, err = c.run(["--json", "version"])
doc = json.loads(out)
ok = (doc["product"], doc["version"], doc["ir_version"], doc["schema_version"]) == (PRODUCT_NAME, VERSION, IR_VERSION, SCHEMA_VERSION) and all(doc.values())
record("CLI-022", "PASS" if ok else "FAIL", f"doc={doc}")

# CLI-023: no config, no db, empty session secret -> exit 0
os.environ.pop("PRAMA_CONFIG", None)
cwd = os.getcwd()
os.chdir(c.WORKDIR)
try:
    code, out, err = c.run(["version"])
finally:
    os.chdir(cwd)
ok = code == 0
record("CLI-023", "PASS" if ok else "FAIL", f"code={code} err={err[:200]!r}")

# CLI-024: config show redacts secrets
cfg24 = c.WORKDIR / "cli024"
cfg24.mkdir(exist_ok=True)
cfg24f = cfg24 / "application.yaml"
cfg24f.write_text(
    "database:\n  dialect: sqlite\n"
    f"  sqlite:\n    path: {cfg24/'x.db'}\n"
    f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
    "security:\n  session_secret: hunter2-plaintext\n"
)
os.environ.pop("PRAMA_ALLOW_RAW_CONFIG", None)
code, out, err = c.run(["--config", str(cfg24f), "config", "show"])
ok = code == 0 and "hunter2-plaintext" not in out and "***" in out
record("CLI-024", "PASS" if ok else "FAIL", f"code={code} leaked={'hunter2-plaintext' in out}")

# CLI-025: --raw without env var
code, out, err = c.run(["--config", str(cfg24f), "config", "show", "--raw"])
ok = code == 0 and "hunter2-plaintext" not in out
record("CLI-025", "PASS" if ok else "FAIL", f"code={code} leaked={'hunter2-plaintext' in out}")

# CLI-026: --raw with env var set -> secrets shown + warning
os.environ["PRAMA_ALLOW_RAW_CONFIG"] = "1"
code, out, err = c.run(["--config", str(cfg24f), "config", "show", "--raw"])
ok = code == 0 and "hunter2-plaintext" in out and "do not paste this anywhere" in err
record("CLI-026", "PASS" if ok else "FAIL", f"code={code} leaked={'hunter2-plaintext' in out} warned={'do not paste' in err}")

# CLI-027: --raw --json -- does the warning survive?
code, out, err = c.run(["--json", "--config", str(cfg24f), "config", "show", "--raw"])
doc = json.loads(out)
flat_str = json.dumps(doc)
has_secret = "hunter2-plaintext" in flat_str
marked = "redacted" in flat_str.lower()
warned = "do not paste this anywhere" in err
ok = has_secret and (marked or warned)
record("CLI-027", "PASS" if ok else "FAIL", f"code={code} has_secret={has_secret} marked_in_json={marked} warned_on_stderr={warned}")
os.environ.pop("PRAMA_ALLOW_RAW_CONFIG", None)

# CLI-028: --provenance names a source for every key
local_cfg = c.WORKDIR / "cli028"
local_cfg.mkdir(exist_ok=True)
local_cfg_f = local_cfg / "application.yaml"
local_cfg_f.write_text(
    "database:\n  dialect: sqlite\n"
    f"  sqlite:\n    path: {local_cfg/'x.db'}\n"
    f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
    "security:\n  session_secret: s\n"
)
code, out, err = c.run(["--config", str(local_cfg_f), "--set", "logging.level=DEBUG", "config", "show", "--provenance"])
lines = [l for l in out.splitlines() if l.strip()]
no_bracket = [l for l in lines if "[" not in l or "]" not in l]
ok = code == 0 and not no_bracket and len(lines) > 5
record("CLI-028", "PASS" if ok else "FAIL", f"code={code} nlines={len(lines)} missing_source={no_bracket[:3]}")

# CLI-029: --provenance --json — is the flag honored or silently discarded?
code, out, err = c.run(["--json", "--config", str(local_cfg_f), "config", "show", "--provenance"])
doc = json.loads(out)
provenance_present = any(
    isinstance(v, dict) and ("source" in v or "provenance" in v) for v in doc.values()
) if isinstance(doc, dict) else False
record(
    "CLI-029",
    "FAIL" if not provenance_present else "PASS",
    f"code={code} json_is_flat_dict={isinstance(doc, dict)} provenance_present_in_json={provenance_present} "
    f"sample_value={list(doc.items())[0] if isinstance(doc, dict) and doc else None} -- "
    f"no refusal was issued either (exit {code}), so --provenance is silently accepted and discarded on the JSON path",
)

print("done version/config batch")
