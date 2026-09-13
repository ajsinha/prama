import sys, os, io, tempfile, sqlite3, logging, json, shutil
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.config import load_configuration, DEFAULTS
from prama.core.config.configuration import Configuration, ConfigurationBuilder
from prama.core.config.sources import deep_merge, MappingSource
from prama.core.errors import ConfigError, SecretMissingError, PramaError

def defaults_only():
    return Configuration(deep_merge({}, DEFAULTS))

# CFG-001: directory with no config/ at all
tmpdir = tempfile.mkdtemp(prefix="cfgqa-")
cwd = os.getcwd()
try:
    os.chdir(tmpdir)
    cfg = load_configuration(use_environment=False, environ={})
    ok = all(cfg.has(k) for k in DEFAULTS)
    R("CFG-001", ok, f"built OK in empty dir; has all top-level DEFAULTS keys={ok}")
except Exception as e:
    R("CFG-001", False, f"raised {type(e).__name__}: {e}")
finally:
    os.chdir(cwd)

# CFG-002
try:
    load_configuration("/tmp/no-such-cfg-qa.yaml")
    R("CFG-002", False, "no exception raised")
except ConfigError as e:
    R("CFG-002", e.code == "CONFIG.FILE_MISSING" and "/tmp/no-such-cfg-qa.yaml" in str(e), f"{e.code}: {e}")
except Exception as e:
    R("CFG-002", False, f"{type(e).__name__}: {e}")

# CFG-003
try:
    load_configuration(environ={"PRAMA_CONFIG": "/tmp/no-such-cfg-qa2.yaml"})
    R("CFG-003", False, "no exception raised")
except ConfigError as e:
    R("CFG-003", e.code == "CONFIG.FILE_MISSING", f"{e.code}: {e}")
except Exception as e:
    R("CFG-003", False, f"{type(e).__name__}: {e}")

d0 = defaults_only()
# CFG-004
R("CFG-004", d0.get_str("app.name") == "Prama", repr(d0.get_str("app.name")))
# CFG-005
R("CFG-005", d0.get_str("app.environment") == "development", repr(d0.get_str("app.environment")))

# CFG-006
b = ConfigurationBuilder().with_defaults(DEFAULTS)
b._environ = {"HOSTNAME": "box-7"}
from prama.core.config.resolver import PlaceholderResolver
resolved = PlaceholderResolver({"HOSTNAME": "box-7"}).resolve_tree(deep_merge({}, DEFAULTS))
v1 = Configuration(resolved).get_str("app.instance_id")
resolved2 = PlaceholderResolver({}).resolve_tree(deep_merge({}, DEFAULTS))
v2 = Configuration(resolved2).get_str("app.instance_id")
R("CFG-006", v1 == "box-7" and v2 == "local", f"HOSTNAME=box-7 -> {v1!r}; unset -> {v2!r}")

# CFG-007 / CFG-008
from prama.core.log import LoggingConfigurator
obs7 = []
for lvl in ["DEBUG", "INFO", "WARNING", "ERROR"]:
    root = logging.getLogger()
    LoggingConfigurator(level=lvl).apply()
    obs7.append((lvl, logging.getLevelName(root.level)))
R("CFG-007", all(a == b2 for a, b2 in obs7), str(obs7))

try:
    LoggingConfigurator(level="VERBOSE").apply()
    R("CFG-008", False, "no exception raised")
except PramaError as e:
    R("CFG-008", bool(e.remedy), f"PramaError {e.code}: remedy={e.remedy!r}")
except Exception as e:
    R("CFG-008", False, f"unnamed {type(e).__name__}: {e}")

# CFG-009
from prama.core.log import JsonFormatter, TextFormatter, ContextFilter, RedactionFilter, log_fields
stream = io.StringIO()
root9 = logging.getLogger("cfg009")
root9.handlers.clear()
h = logging.StreamHandler(stream)
h.setFormatter(JsonFormatter())
h.addFilter(ContextFilter())
h.addFilter(RedactionFilter())
root9.addHandler(h)
root9.setLevel(logging.INFO)
root9.propagate = False
log_fields(root9, logging.INFO, "hello", foo="bar")
line = stream.getvalue().strip()
try:
    obj = json.loads(line)
    ok9 = {"ts","level","logger","message","fields"} <= set(obj.keys()) and "\n" not in line
except Exception as e:
    ok9 = False
    obj = str(e)
R("CFG-009", ok9, f"line={line!r} parsed_keys={list(obj.keys()) if isinstance(obj,dict) else obj}")

# CFG-010
stream2 = io.StringIO()
root10 = logging.getLogger("cfg010")
root10.handlers.clear()
h2 = logging.StreamHandler(stream2)
h2.setFormatter(TextFormatter())
h2.addFilter(ContextFilter())
h2.addFilter(RedactionFilter())
root10.addHandler(h2)
root10.setLevel(logging.INFO)
root10.propagate = False
from prama.core.log import correlation_id
tok = correlation_id.set("cid-123")
root10.info("plain message")
correlation_id.reset(tok)
line2 = stream2.getvalue()
R("CFG-010", "cid=cid-123" in line2 and "{" not in line2, repr(line2))

# CFG-011
R("CFG-011", DEFAULTS["security"]["session_secret"] == "", repr(DEFAULTS["security"]["session_secret"]))

# CFG-012
try:
    d0.require_secret("security.session_secret")
    R("CFG-012", False, "no exception")
except SecretMissingError as e:
    ok = e.code == "CONFIG.SECRET_MISSING" and "config/application.local.yaml" in e.remedy and "PRAMA_SECURITY__SESSION_SECRET" in e.remedy
    R("CFG-012", ok, f"{e.code}: remedy={e.remedy!r}")
except Exception as e:
    R("CFG-012", False, f"{type(e).__name__}: {e}")

# CFG-013
cfg13 = Configuration(deep_merge(DEFAULTS, {"security": {"session_secret": "   "}}))
try:
    cfg13.require_secret("security.session_secret")
    R("CFG-013", False, "no exception; accepted whitespace-only secret")
except SecretMissingError:
    R("CFG-013", True, "refused, as expected")
except Exception as e:
    R("CFG-013", False, f"{type(e).__name__}: {e}")

# CFG-014 -- comment/value mismatch check (documentation case, expected: mismatch found -> corrected)
comment_text = "Off in development only because a developer on http://localhost would"
value = DEFAULTS["security"]["cookies_https_only"]
mismatch = (value is True)  # comment claims "off" but value is True (on)
R("CFG-014", not mismatch, f"comment says 'Off in development' near cookies_https_only={value!r} (True means ON)")

# CFG-015
R("CFG-015", DEFAULTS["tenancy"]["default_tenant"] == "", repr(DEFAULTS["tenancy"]["default_tenant"]))

# CFG-016
R("CFG-016", d0.get_bool("web.enabled") is True, repr(d0.get_bool("web.enabled")))

# CFG-017
R("CFG-017", d0.get_str("web.preview.source", "") == "", repr(d0.get_str("web.preview.source", "")))

# CFG-018: executor_for with unsupported dialect names supported set
from prama.connect.sources.query import executor_for, BUILDERS
import prama.connect.builtin  # noqa: registers builders as side effect, if applicable
try:
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    try:
        executor_for(tf.name, "postgres")
        R("CFG-018", False, "no exception for engine=postgres")
    except Exception as e:
        from prama.core.errors import ValidationError
        ok = isinstance(e, ValidationError) and ("duckdb" in str(e) and "sqlite" in str(e))
        R("CFG-018", ok, f"{type(e).__name__}: {e}; registered BUILDERS={sorted(BUILDERS)}")
finally:
    os.unlink(tf.name)

# CFG-019
R("CFG-019", d0.get_int("web.preview.max_rows") == 1000000, repr(d0.get_int("web.preview.max_rows")))

# CFG-020: max_rows=0 behavior via Preview class directly
from prama.execute.preview import Preview
# use a trivial no-op control against duckdb if available
try:
    import duckdb
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t(a INTEGER)")
    con.execute("INSERT INTO t VALUES (1),(2),(3)")
    def execute(sql):
        cur = con.execute(sql)
        names = [c[0] for c in cur.description or ()]
        return [dict(zip(names, row)) for row in cur.fetchall()]
    p = Preview(execute=execute, engine="duckdb", max_rows=0)
    trial = p.once("CHECK t.a IS NOT NULL BECAUSE \"sanity\"")
    R("CFG-020", False, f"max_rows=0 not refused; trial.verdict={trial.verdict!r} error={trial.error!r} (ran unbounded instead of refusing)")
except ImportError:
    R("CFG-020", None, "BLOCKED: duckdb not installed")
except Exception as e:
    R("CFG-020", None, f"BLOCKED/ERROR while probing: {type(e).__name__}: {e}")

# CFG-021: backtest_days default and negative
R("CFG-021-default", DEFAULTS["web"]["preview"]["backtest_days"] == 30, repr(DEFAULTS["web"]["preview"]["backtest_days"]))
try:
    import prama.web.routes.preview_routes as pr
    import inspect
    src = inspect.getsource(pr)
    has_validation = "backtest_days" in src and ("negative" in src.lower() or "<= 0" in src or "< 0" in src)
    R("CFG-021", has_validation, f"preview_routes.py backtest_days negative-guard present={has_validation}")
except Exception as e:
    R("CFG-021", None, f"BLOCKED: {type(e).__name__}: {e}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
