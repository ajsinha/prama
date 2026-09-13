import sys, os, io, tempfile, logging, json, asyncio, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.config import DEFAULTS, load_configuration
from prama.core.config.configuration import Configuration, ConfigurationBuilder
from prama.core.config.sources import deep_merge
from prama.core.log import SENSITIVE_KEYS, redact_mapping, REDACTED

# CFG-077
b = ConfigurationBuilder().with_defaults(DEFAULTS)
tmp = tempfile.mkdtemp(prefix="cfgqa-prov-")
fileA = os.path.join(tmp, "app.yaml")
with open(fileA, "w") as f: f.write("logging:\n  level: DEBUG\n")
b.with_file(fileA)
b.with_environment({"PRAMA_APP__NAME": "envname"})
b.with_cli(["tenancy.default_tenant=acme"])
cfg = b.build()
provs = {
    "database.pool.size": cfg.provenance("database.pool.size"),
    "logging.level": cfg.provenance("logging.level"),
    "app.name": cfg.provenance("app.name"),
    "tenancy.default_tenant": cfg.provenance("tenancy.default_tenant"),
}
ok = (provs["database.pool.size"] == "built-in defaults"
      and provs["logging.level"] == fileA
      and provs["app.name"] == "environment"
      and provs["tenancy.default_tenant"] == "command line")
R("CFG-077", ok, str(provs))

# CFG-078
b2 = ConfigurationBuilder().with_defaults(DEFAULTS)
fileB = os.path.join(tmp, "app2.yaml")
with open(fileB, "w") as f: f.write("app:\n  name: from-file\n")
b2.with_file(fileB)
b2.with_cli(["app.name=from-cli"])
cfg2 = b2.build()
R("CFG-078", cfg2.get_str("app.name")=="from-cli" and cfg2.provenance("app.name")=="command line",
  f"value={cfg2.get_str('app.name')!r} provenance={cfg2.provenance('app.name')!r}")

# CFG-079
cfg79 = load_configuration(use_environment=True, environ={"PRAMA_DATABASE__POOL__SIZE": "77"})
sect = cfg79.section("database")
R("CFG-079", sect.provenance("pool.size") == "environment", repr(sect.provenance("pool.size")))

# CFG-080
vals = {k: f"secret-{k}" for k in SENSITIVE_KEYS}
red = redact_mapping(vals)
ok80 = all(red[k] == REDACTED for k in SENSITIVE_KEYS)
extra_leak = any(v != REDACTED for k, v in red.items() if k not in SENSITIVE_KEYS)
R("CFG-080", ok80 and not extra_leak, f"masked_count={sum(1 for k in SENSITIVE_KEYS if red[k]==REDACTED)}/{len(SENSITIVE_KEYS)}")

# CFG-081
nested = {"database": {"postgres": {"password": "hunter2", "host": "x"}}}
red81 = redact_mapping(nested)
R("CFG-081", red81["database"]["postgres"]["password"]==REDACTED and red81["database"]["postgres"]["host"]=="x", str(red81))

# CFG-082
listed = {"connections": [{"password": "p1"}, {"password": "p2"}]}
red82 = redact_mapping(listed)
masked_in_list = all(item.get("password") == REDACTED for item in red82["connections"])
R("CFG-082", masked_in_list, f"redact_mapping result for list-of-dicts: {red82} (masked_in_list={masked_in_list})")

# CFG-083
empty_sec = {"session_secret": ""}
red83 = redact_mapping(empty_sec)
R("CFG-083", red83["session_secret"] == "", repr(red83["session_secret"]))

# CFG-084
cfg84 = Configuration(deep_merge(DEFAULTS, {"security": {"session_secret": "topsecret"}}))
flat = cfg84.flatten(redact=True)
R("CFG-084", flat.get("security.session_secret") == "***", repr(flat.get("security.session_secret")))

# CFG-085
flat85 = cfg84.flatten(redact=False)
R("CFG-085", flat85.get("security.session_secret") == "topsecret", repr(flat85.get("security.session_secret")))

# CFG-086
from prama.core.log import RedactionFilter
rec = logging.LogRecord("t", logging.INFO, "f", 1, "password=hunter2", None, None)
RedactionFilter().filter(rec)
R("CFG-086", rec.msg == "password=***", repr(rec.msg))

# CFG-087
rec2 = logging.LogRecord("t", logging.INFO, "f", 1, 'token: "abc" and api_key=\'xyz\'', None, None)
RedactionFilter().filter(rec2)
R("CFG-087", "abc" not in rec2.msg and "xyz" not in rec2.msg, repr(rec2.msg))

# CFG-088
rec3 = logging.LogRecord("t", logging.INFO, "f", 1, "connecting to postgresql://prama:hunter2@host/db", None, None)
RedactionFilter().filter(rec3)
masked88 = "hunter2" not in rec3.msg
R("CFG-088", masked88, repr(rec3.msg))

# CFG-089
from prama.core.log import log_fields
stream89 = io.StringIO()
root89 = logging.getLogger("cfg089")
root89.handlers.clear()
h89 = logging.StreamHandler(stream89)
from prama.core.log import JsonFormatter, ContextFilter
h89.setFormatter(JsonFormatter())
h89.addFilter(ContextFilter())
h89.addFilter(RedactionFilter())
root89.addHandler(h89)
root89.setLevel(logging.INFO)
root89.propagate = False
log_fields(root89, logging.INFO, "x", password="hunter2")
obj89 = json.loads(stream89.getvalue().strip())
R("CFG-089", obj89.get("fields", {}).get("password") == "***", str(obj89.get("fields")))

# CFG-090 / CFG-091
from prama.core.log import correlation_id
async def hop_test():
    results_local = {}
    async def task(name, cid):
        tok = correlation_id.set(cid)
        await asyncio.sleep(0.01)
        results_local[name] = correlation_id.get()
        correlation_id.reset(tok)
    await asyncio.gather(task("A", "cid-A"), task("B", "cid-B"))
    return results_local
res9091 = asyncio.run(hop_test())
R("CFG-090", res9091["A"] == "cid-A", f"task A retained {res9091['A']!r} across its own await")
R("CFG-091", res9091["A"] != res9091["B"] and res9091["B"]=="cid-B", str(res9091))

# CFG-092
from prama.core.log import LoggingConfigurator
root92 = logging.getLogger()
LoggingConfigurator(level="INFO").apply()
LoggingConfigurator(level="INFO").apply()
prama_handlers = [h for h in root92.handlers if getattr(h, "name", None) == "prama"]
R("CFG-092", len(prama_handlers) == 1, f"prama-named handlers on root logger: {len(prama_handlers)}")

# CFG-093
third_party = logging.StreamHandler()
third_party.name = "thirdparty"
root92.addHandler(third_party)
LoggingConfigurator(level="INFO").apply()
survived = third_party in root92.handlers
root92.removeHandler(third_party)
R("CFG-093", survived, f"third-party handler survived apply()={survived}")

# CFG-094
import time as time_mod
stream94 = io.StringIO()
root94 = logging.getLogger("cfg094")
root94.handlers.clear()
h94 = logging.StreamHandler(stream94)
h94.setFormatter(JsonFormatter())
h94.addFilter(ContextFilter())
root94.addHandler(h94)
root94.setLevel(logging.INFO)
root94.propagate = False
import datetime as _dt
before_utc = _dt.datetime.now(_dt.timezone.utc)
root94.info("ts-check")
obj94 = json.loads(stream94.getvalue().strip())
ts = obj94["ts"]
import re
m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$", ts)
tz_offset_hours = -time_mod.timezone / 3600 if not time_mod.daylight else -time_mod.altzone / 3600
utc_now_str = before_utc.strftime("%Y-%m-%dT%H:%M")
ts_prefix = ts[:16]
matches_utc = ts_prefix == utc_now_str or ts_prefix == before_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M")
R("CFG-094", bool(m) and matches_utc, f"ts={ts!r} local_tz_offset_hours={tz_offset_hours} utc_now={utc_now_str!r} matches_utc={matches_utc}")

# CFG-095
stream95 = io.StringIO()
root95 = logging.getLogger("cfg095")
root95.handlers.clear()
h95 = logging.StreamHandler(stream95)
h95.setFormatter(JsonFormatter())
h95.addFilter(ContextFilter())
root95.addHandler(h95)
root95.setLevel(logging.INFO)
root95.propagate = False
try:
    raise ValueError("boom")
except ValueError:
    root95.exception("failed")
line95 = stream95.getvalue().strip()
try:
    obj95 = json.loads(line95)
    ok95 = "exception" in obj95 and "ValueError" in obj95["exception"] and "\n" not in line95
except Exception as e:
    ok95 = False
    obj95 = str(e)
R("CFG-095", ok95, f"parsed_ok={isinstance(obj95, dict)}; has exception field={isinstance(obj95,dict) and 'exception' in obj95}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
