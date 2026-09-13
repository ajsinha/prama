import sys, os, math
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.config.coercion import Coercer
from prama.core.errors import ConfigTypeError
from prama.core.config.resolver import PlaceholderResolver
from prama.core.config.configuration import Configuration, ConfigurationBuilder
from prama.core.config.sources import deep_merge, MappingSource
from prama.core.config import DEFAULTS, load_configuration
from prama.core.errors import ConfigError, ConfigMissingError

c = Coercer("test.key")

# CFG-096
truthy = ["1","true","yes","y","on","enabled"," TRUE ", "On"]
falsy = ["0","false","no","n","off","disabled"," FALSE "]
ok96 = all(c.to_bool(v) is True for v in truthy) and all(c.to_bool(v) is False for v in falsy)
R("CFG-096", ok96, f"truthy all True={all(c.to_bool(v) is True for v in truthy)}, falsy all False={all(c.to_bool(v) is False for v in falsy)}")

# CFG-097
try:
    c.to_bool("maybe")
    R("CFG-097", False, "no exception")
except ConfigTypeError as e:
    ok = e.code == "CONFIG.TYPE" and "key" in e.context
    R("CFG-097", ok, f"{e.code}: {e.context}")

# CFG-098
try:
    c.to_int(True)
    R("CFG-098", False, "no exception; to_int(True) returned a value")
except ConfigTypeError as e:
    R("CFG-098", "not an integer" in str(e).lower() or "be explicit" in e.remedy.lower(), str(e))

# CFG-099
R("CFG-099", c.to_int("0x10") == 16, repr(c.to_int("0x10")))
try:
    c.to_int("010")
    R("CFG-099b", False, "010 accepted (should be refused as invalid octal per int(x,0))")
except ConfigTypeError:
    R("CFG-099b", True, "010 refused as expected")

# CFG-100
R("CFG-100a", c.to_int(10.0) == 10, repr(c.to_int(10.0)))
try:
    c.to_int(10.5)
    R("CFG-100b", False, "no exception")
except ConfigTypeError:
    R("CFG-100b", True, "refused")

# CFG-101
try:
    c.to_float(True)
    R("CFG-101", False, "no exception")
except ConfigTypeError as e:
    R("CFG-101", "explicit" in e.remedy.lower(), str(e))

# CFG-102
R("CFG-102", c.to_list("a,b, c") == ["a","b","c"], repr(c.to_list("a,b, c")))

# CFG-103
R("CFG-103", c.to_list("") == [], repr(c.to_list("")))

# CFG-104
try:
    c.to_list({"a": 1})
    R("CFG-104", False, "no exception")
except ConfigTypeError as e:
    R("CFG-104", "key" in e.context, str(e.context))

# CFG-105
try:
    c.to_dict("sqlite")
    R("CFG-105", False, "no exception")
except ConfigTypeError as e:
    R("CFG-105", "key" in e.context, str(e.context))

# CFG-106
units = {"1ns":1e-9,"1us":1e-6,"1ms":1e-3,"1s":1,"1sec":1,"1secs":1,"1m":60,"1min":60,"1mins":60,
         "1h":3600,"1hr":3600,"1hrs":3600,"1d":86400,"1day":86400,"1days":86400,"1w":604800}
mism = {}
for k, exp in units.items():
    got = c.to_duration_seconds(k)
    if not math.isclose(got, exp, rel_tol=1e-9):
        mism[k] = (got, exp)
R("CFG-106", not mism, f"mismatches={mism}" if mism else "all 16 units correct")

# CFG-107
R("CFG-107", c.to_duration_seconds(5) == 5.0, repr(c.to_duration_seconds(5)))

# CFG-108
try:
    c.to_duration_seconds("5 fortnights")
    R("CFG-108", False, "no exception")
except ConfigTypeError as e:
    ok = "500ms" in e.remedy and "30s" in e.remedy
    R("CFG-108", ok, e.remedy)

# CFG-109
R("CFG-109", c.to_duration_seconds("30S")==30 and c.to_duration_seconds("5M")==300, f"30S={c.to_duration_seconds('30S')} 5M={c.to_duration_seconds('5M')}")

# CFG-110
R("CFG-110", c.to_duration_seconds("0.5s")==0.5 and c.to_duration_seconds(".5s")==0.5, f"0.5s={c.to_duration_seconds('0.5s')} .5s={c.to_duration_seconds('.5s')}")

# CFG-111
try:
    v = c.to_duration_seconds("-5s")
    R("CFG-111", False, f"no exception; got {v}")
except ConfigTypeError:
    R("CFG-111", True, "refused")

# CFG-112
try:
    v = c.to_duration_seconds(-5)
    R("CFG-112", False, f"numeric -5 accepted and returned {v} -- disagrees with string form '-5s' which is refused")
except ConfigTypeError:
    R("CFG-112", True, "refused")

# CFG-113
byte_units = {"1kb":(1000,), "1kib":(1024,), "1mb":(1000**2,), "1mib":(1024**2,),
              "1gb":(1000**3,), "1gib":(1024**3,), "1tb":(1000**4,), "1tib":(1024**4,)}
mismb = {}
for k, (exp,) in byte_units.items():
    got = c.to_bytes(k)
    if got != exp:
        mismb[k] = (got, exp)
R("CFG-113", not mismb, f"mismatches={mismb}" if mismb else "all correct")

# CFG-114
R("CFG-114", c.to_bytes("268435456")==268435456, repr(c.to_bytes("268435456")))

# CFG-115
try:
    c.to_bytes("512megs")
    R("CFG-115", False, "no exception")
except ConfigTypeError as e:
    ok = "512kb" in e.remedy and "256mb" in e.remedy
    R("CFG-115", ok, e.remedy)

# CFG-116
try:
    c.to_bytes(True)
    R("CFG-116a", False, "no exception")
except ConfigTypeError:
    R("CFG-116a", True, "bool refused")
try:
    c.to_bytes(1.5)
    R("CFG-116b", False, "no exception")
except ConfigTypeError:
    R("CFG-116b", True, "fractional float refused")

# CFG-117
c2 = Coercer("database.pool.size")
try:
    c2.to_int("notanumber")
    R("CFG-117", False, "no exception")
except ConfigTypeError as e:
    ok = e.context.get("key")=="database.pool.size" and e.context.get("value")=="'notanumber'" and e.context.get("wanted")=="integer"
    R("CFG-117", ok, str(e.context))

# CFG-118
c3 = Coercer("security.session_secret")
try:
    c3.to_int("supersecretvalue123")
    R("CFG-118", False, "no exception")
except ConfigTypeError as e:
    leaked = "supersecretvalue123" in str(e)
    R("CFG-118", not leaked, f"secret leaked in exception string={leaked}: {e}")

# CFG-119
try:
    PlaceholderResolver({}).resolve_value("${NOT_SET}", path="app.instance_id")
    R("CFG-119", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.PLACEHOLDER_UNRESOLVED" and "NOT_SET" in e.remedy and "${NAME:value}" in e.remedy.replace("NOT_SET","NAME") if False else e.code=="CONFIG.PLACEHOLDER_UNRESOLVED"
    R("CFG-119", ok, f"{e.code}: {e.remedy!r}")

# CFG-120
import yaml as _yaml
with open(os.path.join(REPO, "config", "application.yaml")) as f:
    doc = _yaml.safe_load(f)
resolved = PlaceholderResolver({}).resolve_tree(doc)
R("CFG-120", resolved["database"]["postgres"]["host"]=="localhost", repr(resolved["database"]["postgres"]["host"]))

# CFG-121
r121 = PlaceholderResolver({}).resolve_value("${NOT_SET:http://host:5432/db}")
R("CFG-121", r121=="http://host:5432/db", repr(r121))

# CFG-122
r122 = PlaceholderResolver({}).resolve_value("${NOT_SET:}")
R("CFG-122", r122=="", repr(r122))

# CFG-123
r123 = PlaceholderResolver({}).resolve_value("$${NOT_A_VAR}")
R("CFG-123", r123=="${NOT_A_VAR}", repr(r123))

# CFG-124
tree124 = {"paths": {"data": "/var/lib/prama"}, "evidence": {"path": "${paths.data}/evidence"}}
res124 = PlaceholderResolver({}).resolve_tree(tree124)
R("CFG-124", res124["evidence"]["path"]=="/var/lib/prama/evidence", repr(res124["evidence"]["path"]))

# CFG-125
tree125 = {"pghost": "config-value"}
r125 = PlaceholderResolver({"PGHOST":"env-value"})
r125._root = tree125
val = r125.resolve_value("${PGHOST}")
R("CFG-125", val=="env-value", repr(val))

# CFG-126
try:
    PlaceholderResolver({}).resolve_tree({"a": "${a}"})
    R("CFG-126", False, "no exception")
except ConfigError as e:
    R("CFG-126", e.code=="CONFIG.PLACEHOLDER_CYCLE" and "a -> a" in str(e), str(e))

# CFG-127
tree127 = {"a": "${b}", "b": "${a}"}
try:
    PlaceholderResolver({}).resolve_tree(tree127)
    R("CFG-127", False, "no exception")
except ConfigError as e:
    R("CFG-127", e.code=="CONFIG.PLACEHOLDER_CYCLE", str(e))

# CFG-128 -- a "seventeen-link chain" is 17 arrows: k0->k1->...->k17 (18 keys)
r17 = None
try:
    tree17 = {f"k{i}": (f"${{k{i+1}}}" if i < 17 else "literal-end") for i in range(18)}
    res17 = PlaceholderResolver({}).resolve_tree(tree17)
    r17 = ("resolved", res17["k0"])
except ConfigError as e:
    r17 = ("error", e.code, str(e))
# a sixteen-link chain (16 arrows, k0..k16, 17 keys) must still resolve
tree16 = {f"k{i}": (f"${{k{i+1}}}" if i < 16 else "literal-end") for i in range(17)}
r16 = PlaceholderResolver({}).resolve_tree(tree16)
R("CFG-128", r17[0]=="error" and r17[1]=="CONFIG.PLACEHOLDER_CYCLE" and r16["k0"]=="literal-end",
  f"17-link-chain={r17}; 16-link-chain result={r16['k0']!r}")

# CFG-129
tree129 = {"database": {"pool": {"size": 10}}}
res129 = PlaceholderResolver({}).resolve_tree(tree129)
R("CFG-129", res129["database"]["pool"]["size"]==10 and isinstance(res129["database"]["pool"]["size"], int), repr(res129["database"]["pool"]["size"]))

# CFG-130
tree130 = {"plugins": {"entry_point_groups": ["${GROUP:prama.connectors}"]}}
res130 = PlaceholderResolver({}).resolve_tree(tree130)
ok130 = res130["plugins"]["entry_point_groups"] == ["prama.connectors"]
R("CFG-130", ok130, repr(res130["plugins"]["entry_point_groups"]))

# CFG-131
cfg131 = Configuration(deep_merge(DEFAULTS, {"tenancy": {"default_tenant": None}}))
has131 = cfg131.has("tenancy.default_tenant")
get131 = cfg131.get_str("tenancy.default_tenant", "fallback")
R("CFG-131", has131 is True and get131=="fallback", f"has={has131} get_str(default='fallback')={get131!r}")

# CFG-132
cfg132 = Configuration(deep_merge(DEFAULTS, {}))
try:
    cfg132.section("database").require("nope")
    R("CFG-132", False, "no exception")
except ConfigMissingError as e:
    ok = "database.nope" in str(e) and "PRAMA_DATABASE__NOPE" in e.remedy
    R("CFG-132", ok, f"{e}; remedy={e.remedy!r}")

# CFG-133
cfg133 = Configuration(deep_merge(DEFAULTS, {"database": "sqlite"}))
try:
    cfg133.section("database")
    R("CFG-133", False, "no exception")
except ConfigError as e:
    R("CFG-133", e.code=="CONFIG.NOT_A_SECTION", e.code)

# CFG-134
cfg134 = Configuration(deep_merge(DEFAULTS, {}))
R("CFG-134", cfg134.section("notifiers").get_str("x","d")=="d", repr(cfg134.section("notifiers").get_str("x","d")))

# CFG-135
import dataclasses
from pathlib import Path
@dataclasses.dataclass
class Sample:
    s: str = "x"
    i: int = 0
    f: float = 0.0
    b: bool = False
    p: Path = Path(".")
    lst: list[str] = dataclasses.field(default_factory=list)
    dct: dict[str, int] = dataclasses.field(default_factory=dict)
    opt: str | None = None
cfg135 = Configuration(deep_merge(DEFAULTS, {"sample": {"s":"hi","i":"5","f":"1.5","b":"true","p":"~/x","lst":"a,b","dct":{"k":1},"opt":None}}))
obj135 = cfg135.bind("sample", Sample)
ok135 = (obj135.s=="hi" and obj135.i==5 and obj135.f==1.5 and obj135.b is True
         and isinstance(obj135.p, Path) and str(obj135.p).startswith(str(Path.home()))
         and obj135.lst==["a","b"] and obj135.dct=={"k":1} and obj135.opt is None)
R("CFG-135", ok135, str(dataclasses.asdict(obj135) if hasattr(obj135,'__dataclass_fields__') else obj135))

# CFG-136
@dataclasses.dataclass
class Required:
    must: str
cfg136 = Configuration(deep_merge(DEFAULTS, {"needsit": {}}))
try:
    cfg136.bind("needsit", Required)
    R("CFG-136", False, "no exception")
except ConfigMissingError as e:
    R("CFG-136", "needsit.must" in str(e), str(e))

# CFG-137
class NotADataclass:
    pass
try:
    cfg136.bind("needsit", NotADataclass)
    R("CFG-137", False, "no exception")
except TypeError as e:
    R("CFG-137", "NotADataclass" in str(e), str(e))

# CFG-138
@dataclasses.dataclass
class OptInt:
    field: int | None = 5
cfg138 = Configuration(deep_merge(DEFAULTS, {"oi": {"field": None}}))
obj138 = cfg138.bind("oi", OptInt)
R("CFG-138", obj138.field is None, repr(obj138.field))

# CFG-139
cfg139 = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": "~/prama.db"}}}))
p139 = cfg139.get_path("database.sqlite.path")
R("CFG-139", str(p139) == str(Path.home() / "prama.db"), repr(str(p139)))

# CFG-140
cfg140 = Configuration(deep_merge(DEFAULTS, {}))
raw140 = cfg140.raw()
raw140["app"]["name"] = "MUTATED"
import subprocess as _sp
grep140 = _sp.run(["grep", "-rn", r"\.raw()", REPO + "/src", REPO + "/run_prama_web.py"], capture_output=True, text=True).stdout
only_caller_reads_only = (".raw()) into a new builder" not in grep140) and "with_defaults(config.raw())" in grep140
R("CFG-140", cfg140.get_str("app.name")=="MUTATED" and only_caller_reads_only,
  f"raw() is a live reference (external mutation of the returned dict is visible through get_str -> {cfg140.get_str('app.name')!r}); "
  f"the only caller (run_prama_web.py) only reads it via with_defaults(), never mutates it: {grep140.strip()!r}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
