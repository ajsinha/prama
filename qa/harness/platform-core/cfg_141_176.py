import sys, os, re, subprocess, threading, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

import prama.core.errors as errors_mod
from prama.core.errors import (
    PramaError, ConfigError, ConfigMissingError, ConfigTypeError, SecretMissingError,
    RegistryError, DatabaseError, SchemaDriftError, ConcurrencyError, LeaseLostError,
    BackPressureError, NotFoundError, ConflictError, ValidationError,
    UnauthorisedError, ForbiddenError,
)

# CFG-141
expected_codes = {
    "PramaError": "PRAMA.ERROR", "ConfigError": "CONFIG.INVALID", "ConfigMissingError": "CONFIG.MISSING",
    "ConfigTypeError": "CONFIG.TYPE", "SecretMissingError": "CONFIG.SECRET_MISSING",
    "RegistryError": "REGISTRY.INVALID", "DatabaseError": "DB.ERROR", "SchemaDriftError": "DB.SCHEMA_DRIFT",
    "ConcurrencyError": "CONCURRENCY.INVARIANT", "LeaseLostError": "CONCURRENCY.LEASE_LOST",
    "BackPressureError": "CONCURRENCY.BACKPRESSURE", "NotFoundError": "ENTITY.NOT_FOUND",
    "ConflictError": "ENTITY.CONFLICT", "ValidationError": "INPUT.INVALID",
    "UnauthorisedError": "AUTH.UNAUTHORISED", "ForbiddenError": "AUTH.FORBIDDEN",
}
actual = {name: getattr(errors_mod, name).code for name in expected_codes}
codes_unique = len(set(actual.values())) == len(actual)
R("CFG-141", actual == expected_codes and codes_unique, f"mismatches={{k:v for k,v in actual.items() if expected_codes[k]!=v}}" if actual!=expected_codes else "all match, all unique")

# CFG-142
try:
    PramaError("x")
    R("CFG-142", False, "no TypeError")
except TypeError as e:
    R("CFG-142", True, str(e))

# CFG-143/144/145/153 -- static scan of src/
import glob
src_files = glob.glob(REPO + "/src/prama/**/*.py", recursive=True)
raise_pattern = re.compile(r'(\w*Error)\(\s*(?:f?"[^"]*"|f?\'[^\']*\')', re.S)
empty_remedy = []
code_literals = []
for path in src_files:
    text = open(path, encoding="utf-8").read()
    for m in re.finditer(r'remedy\s*=\s*""', text):
        empty_remedy.append((path, text[:m.start()].count("\n")+1))
    for m in re.finditer(r'code\s*=\s*"([^"]+)"', text):
        code_literals.append((path, m.group(1)))
bad_code_format = [c for p, c in code_literals if not re.match(r'^[A-Z0-9_]+\.[A-Z0-9_]+$', c)]
R("CFG-143", not empty_remedy, f"empty remedy= literals found: {empty_remedy}" if empty_remedy else "no remedy=\"\" literal found in src/")
R("CFG-153", not bad_code_format, f"non-conforming codes: {bad_code_format}" if bad_code_format else f"{len(code_literals)} code= literals, all AREA.CONDITION")

# CFG-144: extract "prama ..." commands quoted specifically inside remedy=... strings
prama_cmds = set()
for path in src_files:
    text = open(path, encoding="utf-8").read()
    for m in re.finditer(r'remedy\s*=', text):
        window = text[m.end(): m.end() + 400]
        for cm in re.finditer(r'`(prama [a-z][a-z0-9 _-]*)`', window):
            prama_cmds.add(cm.group(1).strip())
bad_cmds = []
for cmd in sorted(prama_cmds):
    parts = cmd.split()
    tried = None
    for n in (3, 2):
        candidate = parts[:n] + ["--help"]
        try:
            p = subprocess.run(candidate, capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                tried = candidate
                break
        except Exception:
            pass
    if tried is None:
        bad_cmds.append(cmd)
R("CFG-144", not bad_cmds, f"commands quoted inside remedy=... that fail --help: {bad_cmds}" if bad_cmds else f"{len(prama_cmds)} quoted `prama ...` commands inside remedy=... strings all resolve via --help: {sorted(prama_cmds)}")

# CFG-145: paths quoted specifically inside remedy=... strings
missing_paths = []
found_paths = set()
for path in src_files:
    text = open(path, encoding="utf-8").read()
    for m in re.finditer(r'remedy\s*=', text):
        window = text[m.end(): m.end() + 400]
        for pm in re.finditer(r'([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+\.(?:yaml|yml|sql|json|pem|md))', window):
            found_paths.add(pm.group(1))
for p in found_paths:
    full = os.path.join(REPO, p)
    if not os.path.exists(full) and "local" not in p:
        missing_paths.append(p)
gitignored_local = all(("local" in p) for p in found_paths if not os.path.exists(os.path.join(REPO, p)))
R("CFG-145", not missing_paths, f"paths referenced in remedy=...: {sorted(found_paths)}; missing-and-not-local={missing_paths}; every missing one is git-ignored *.local.*={gitignored_local}")

# CFG-146
e146 = ConfigError("bad thing", remedy="fix it", context={"b": 2, "a": 1})
s146 = str(e146)
R("CFG-146", s146 == "[CONFIG.INVALID] bad thing | Next: fix it | Context: a=1, b=2", repr(s146))

# CFG-147
d147 = e146.to_dict()
R("CFG-147", set(d147.keys()) == {"code","message","remedy","context"}, str(sorted(d147.keys())))

# CFG-148
ctx = {"a": 1}
e148 = ConfigError("x", remedy="y", context=ctx)
ctx["a"] = 999
R("CFG-148", e148.context["a"] == 1, f"e148.context={e148.context}")

# CFG-149
cause = ValueError("root cause")
e149 = ConfigError("x", remedy="y", cause=cause)
R("CFG-149", e149.__cause__ is cause, repr(e149.__cause__))

# CFG-150
checks150 = [
    issubclass(ConfigMissingError, ConfigError), issubclass(ConfigTypeError, ConfigError),
    issubclass(SecretMissingError, ConfigError), issubclass(SchemaDriftError, DatabaseError),
    issubclass(LeaseLostError, ConcurrencyError), issubclass(BackPressureError, ConcurrencyError),
    issubclass(ConfigError, PramaError), issubclass(DatabaseError, PramaError),
    issubclass(ConcurrencyError, PramaError),
]
R("CFG-150", all(checks150), str(checks150))

# CFG-151
R("CFG-151", not issubclass(UnauthorisedError, ForbiddenError) and not issubclass(ForbiddenError, UnauthorisedError),
  f"Unauthorised<-Forbidden={issubclass(UnauthorisedError, ForbiddenError)}, Forbidden<-Unauthorised={issubclass(ForbiddenError, UnauthorisedError)}")

# CFG-152
e152 = ConfigError("x", remedy="y", code="CONFIG.YAML_INVALID")
R("CFG-152", e152.code == "CONFIG.YAML_INVALID", repr(e152.code))

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
