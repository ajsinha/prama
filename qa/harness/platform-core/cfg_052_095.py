import sys, os, io, tempfile, logging, json, asyncio, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration, ConfigurationBuilder
from prama.core.config.sources import deep_merge, expand_dotted, local_overlay_for, source_for, CliSource, EnvironmentSource
from prama.core.errors import ConfigError

tmp = tempfile.mkdtemp(prefix="cfgqa-src-")

# CFG-052: precedence chain
base_yaml = os.path.join(tmp, "app.yaml")
local_yaml = os.path.join(tmp, "app.local.yaml")
with open(base_yaml, "w") as f: f.write("app:\n  name: file-value\n")
with open(local_yaml, "w") as f: f.write("app:\n  name: overlay-value\n")
b = ConfigurationBuilder().with_defaults({"app": {"name": "default-value"}})
b.with_file(base_yaml)
b.with_environment({"PRAMA_APP__NAME": "env-value"})
b.with_cli(["app.name=cli-value"])
cfg = b.build()
v_all = cfg.get_str("app.name")
# now peel back: no CLI
b2 = ConfigurationBuilder().with_defaults({"app": {"name": "default-value"}})
b2.with_file(base_yaml)
b2.with_environment({"PRAMA_APP__NAME": "env-value"})
v_noC = b2.build().get_str("app.name")
b3 = ConfigurationBuilder().with_defaults({"app": {"name": "default-value"}})
b3.with_file(base_yaml)
v_noCE = b3.build().get_str("app.name")
b4 = ConfigurationBuilder().with_defaults({"app": {"name": "default-value"}})
b4.with_file(base_yaml, overlay=False)
v_noCEO = b4.build().get_str("app.name")  # file only, no overlay -> file-value
b5 = ConfigurationBuilder().with_defaults({"app": {"name": "default-value"}})
v_defaults_only = b5.build().get_str("app.name")
ok52 = (v_all=="cli-value" and v_noC=="env-value" and v_noCE=="overlay-value" and v_noCEO=="file-value" and v_defaults_only=="default-value")
R("CFG-052", ok52, f"cli={v_all!r} env={v_noC!r} overlay={v_noCE!r} file-only={v_noCEO!r} defaults={v_defaults_only!r}")

# CFG-053
b6 = ConfigurationBuilder().with_defaults(DEFAULTS)
b6.with_mapping({"database": {"pool": {"size": 5}}}, name="overlay")
cfg6 = b6.build()
R("CFG-053", cfg6.get_int("database.pool.max_overflow") == 20 and cfg6.get_int("database.pool.size") == 5,
  f"size={cfg6.get_int('database.pool.size')} max_overflow={cfg6.get_int('database.pool.max_overflow')}")

# CFG-054
b7 = ConfigurationBuilder().with_defaults(DEFAULTS)
b7.with_mapping({"plugins": {"entry_point_groups": ["prama.connectors"]}}, name="overlay")
cfg7 = b7.build()
R("CFG-054", cfg7.get_list("plugins.entry_point_groups") == ["prama.connectors"], repr(cfg7.get_list("plugins.entry_point_groups")))

# CFG-055
qadir = os.path.join(tmp, "qa")
os.makedirs(qadir, exist_ok=True)
p1 = os.path.join(qadir, "app.yaml")
p2 = os.path.join(qadir, "app.local.yaml")
with open(p1, "w") as f: f.write("app:\n  name: base\n")
with open(p2, "w") as f: f.write("app:\n  environment: overlaid\n")
from prama.core.config import load_configuration
cfg55 = load_configuration(p1, use_environment=False)
R("CFG-055", cfg55.get_str("app.name")=="base" and cfg55.get_str("app.environment")=="overlaid",
  f"name={cfg55.get_str('app.name')!r} env={cfg55.get_str('app.environment')!r}")

# CFG-056: missing overlay not an error
p3 = os.path.join(tmp, "solo.yaml")
with open(p3, "w") as f: f.write("app:\n  name: solo\n")
try:
    cfg56 = load_configuration(p3, use_environment=False)
    R("CFG-056", cfg56.get_str("app.name")=="solo", "loaded cleanly, no overlay present")
except Exception as e:
    R("CFG-056", False, f"{type(e).__name__}: {e}")

# CFG-057
pp1 = os.path.join(tmp, "app.properties")
pp2 = os.path.join(tmp, "app.local.properties")
with open(pp1, "w") as f: f.write("app.name = base-props\n")
with open(pp2, "w") as f: f.write("app.name = overlay-props\n")
cfg57 = load_configuration(pp1, use_environment=False)
R("CFG-057", cfg57.get_str("app.name")=="overlay-props", repr(cfg57.get_str("app.name")))

# CFG-058
bad_yaml = os.path.join(tmp, "bad.yaml")
with open(bad_yaml, "w") as f: f.write("a: [1, 2\n")
try:
    load_configuration(bad_yaml, use_environment=False)
    R("CFG-058", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.YAML_INVALID" and "detail" in e.context
    R("CFG-058", ok, f"{e.code}: detail present={('detail' in e.context)}")

# CFG-059
list_yaml = os.path.join(tmp, "list.yaml")
with open(list_yaml, "w") as f: f.write("- a\n- b\n")
try:
    load_configuration(list_yaml, use_environment=False)
    R("CFG-059", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.YAML_SHAPE" and "key: value pairs" in e.remedy.lower()
    R("CFG-059", ok, f"{e.code}: {e.remedy!r}")

# CFG-060
empty_local = os.path.join(tmp, "hasoverlay.yaml")
empty_overlay = os.path.join(tmp, "hasoverlay.local.yaml")
with open(empty_local, "w") as f: f.write("app:\n  name: has-overlay\n")
with open(empty_overlay, "w") as f: pass  # zero bytes
cfg60 = load_configuration(empty_local, use_environment=False)
R("CFG-060", cfg60.get_str("app.name")=="has-overlay", repr(cfg60.get_str("app.name")))

# CFG-061
perm_file = os.path.join(tmp, "noperm.yaml")
with open(perm_file, "w") as f: f.write("app:\n  name: x\n")
os.chmod(perm_file, 0o000)
try:
    if os.geteuid() == 0:
        R("CFG-061", None, "BLOCKED: running as root, chmod 000 has no effect")
    else:
        load_configuration(perm_file, use_environment=False)
        R("CFG-061", False, "no exception (running as root?)")
except ConfigError as e:
    ok = e.code == "CONFIG.FILE_UNREADABLE" and ("permission" in e.remedy.lower() and "utf-8" in e.remedy.lower())
    R("CFG-061", ok, f"{e.code}: {e.remedy!r}")
finally:
    os.chmod(perm_file, 0o644)

# CFG-062
latin1_file = os.path.join(tmp, "latin1.yaml")
with open(latin1_file, "wb") as f:
    f.write("app:\n  name: caf\xe9\n".encode("latin-1"))
try:
    load_configuration(latin1_file, use_environment=False)
    R("CFG-062", False, "no exception raised; decode error swallowed silently or default-value used")
except ConfigError as e:
    R("CFG-062", e.code == "CONFIG.FILE_UNREADABLE", f"{e.code}: {e}")
except UnicodeDecodeError as e:
    R("CFG-062", False, f"UnicodeDecodeError escaped uncaught (except OSError does not catch it): {e}")
except Exception as e:
    R("CFG-062", False, f"{type(e).__name__}: {e}")

# CFG-063
try:
    load_configuration(os.path.join(tmp, "app.toml"), use_environment=False)
    R("CFG-063", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.FORMAT_UNSUPPORTED" and ".yaml" in e.remedy and ".properties" in e.remedy
    R("CFG-063", ok, f"{e.code}: {e.remedy!r}")

# CFG-064
bad_props = os.path.join(tmp, "bad.properties")
with open(bad_props, "w") as f:
    f.write("a = 1\nb = 2\ndatabase.pool.size\n")
try:
    load_configuration(bad_props, use_environment=False)
    R("CFG-064", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.PROPERTIES_INVALID" and e.context.get("line") == 3
    R("CFG-064", ok, f"{e.code}: line={e.context.get('line')}")

# CFG-065
comment_props = os.path.join(tmp, "comment.properties")
with open(comment_props, "w") as f:
    f.write("# comment1\n! comment2\napp.name = commented-ok\n")
cfg65 = load_configuration(comment_props, use_environment=False)
R("CFG-065", cfg65.get_str("app.name")=="commented-ok", repr(cfg65.get_str("app.name")))

# CFG-066
dotted_props = os.path.join(tmp, "dotted.properties")
with open(dotted_props, "w") as f:
    f.write("database.pool.size = 20\n")
cfg66 = load_configuration(dotted_props, use_environment=False)
R("CFG-066", cfg66.get_int("database.pool.size")==20 and cfg66.get_str("database.dialect")=="sqlite",
  f"pool.size={cfg66.get_int('database.pool.size')} dialect={cfg66.get_str('database.dialect')}")

# CFG-067
try:
    load_configuration(use_environment=False, overrides=["a=1", "a.b=2"])
    R("CFG-067", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.KEY_CONFLICT"
    R("CFG-067", ok, f"{e.code}: {e}")

# CFG-068
env68 = {"PATH": "/bin", "HOME": "/home/x", "USER": "qa", "PRAMA_APP__NAME": "envname"}
cfg68 = load_configuration(use_environment=True, environ=env68)
has_path = cfg68.has("path")
R("CFG-068", cfg68.get_str("app.name")=="envname" and not has_path, f"app.name={cfg68.get_str('app.name')!r} has('path')={has_path}")

# CFG-069
cfg69 = load_configuration(use_environment=True, environ={"PRAMA_DATABASE__POOL__SIZE": "20"})
R("CFG-069", cfg69.get_int("database.pool.size")==20 and cfg69.get_str("database.pool.size")=="20",
  f"int={cfg69.get_int('database.pool.size')} str={cfg69.get_str('database.pool.size')!r}")

# CFG-070
cfg70 = load_configuration(use_environment=True, environ={"PRAMA_APP__INSTANCE_ID": "box"})
R("CFG-070", cfg70.get_str("app.instance_id")=="box", repr(cfg70.get_str("app.instance_id")))

# CFG-071
try:
    cfg71 = load_configuration(use_environment=True, environ={"PRAMA_": "x"})
    R("CFG-071", True, "no crash; built OK")
except Exception as e:
    R("CFG-071", False, f"{type(e).__name__}: {e}")

# CFG-072
cfg72 = load_configuration(use_environment=True, environ={"PRAMA_DATABASE__DIALECT": "postgres"})
R("CFG-072", cfg72.get_str("database.dialect")=="postgres", repr(cfg72.get_str("database.dialect")))

# CFG-073
try:
    load_configuration(use_environment=False, overrides=["database.dialect"])
    R("CFG-073", False, "no exception")
except ConfigError as e:
    ok = e.code == "CONFIG.CLI_INVALID" and "--set path.to.key=value" in e.remedy
    R("CFG-073", ok, f"{e.code}: {e.remedy!r}")

# CFG-074
cfg74 = load_configuration(use_environment=False, overrides=["tenancy.default_tenant="])
R("CFG-074", cfg74.get_str("tenancy.default_tenant")=="", repr(cfg74.get_str("tenancy.default_tenant")))

# CFG-075
cfg75 = load_configuration(use_environment=False, overrides=["security.session_secret=a=b=c"])
R("CFG-075", cfg75.get_str("security.session_secret")=="a=b=c", repr(cfg75.get_str("security.session_secret")))

# CFG-076
cfg76 = load_configuration(use_environment=False, overrides=[" app.name = Prama "])
R("CFG-076", cfg76.get_str("app.name")=="Prama", repr(cfg76.get_str("app.name")))

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
