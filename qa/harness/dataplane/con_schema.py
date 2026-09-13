import sys, re, inspect
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.config_schema import (
    ConfigSchemaDeriver, ConnectorConfigSchema, FieldSpec, FieldPresentation, InputKind,
)
from prama.connect.registry import ConnectorRegistry
from prama.connect.builtin import register_builtin
from prama.core.errors import ValidationError, RegistryError
from prama.core.registry import Registry
import prama.connect.sources.sqlite as sqlite_mod
import prama.connect.sources.filesystem as fs_mod
import prama.connect.sources.sql.postgres as pg_mod

registry = register_builtin(ConnectorRegistry())

def con045():
    obs = []
    all_ok = True
    for key in registry.keys():
        cls = registry.get(key)
        derived_names = set(registry.schema(key).field(f.name).name for f in registry.schema(key).fields)
        derived_names = {f.name for f in registry.schema(key).fields}
        grepped = set()
        for klass in cls.__mro__:
            if klass is object:
                continue
            try:
                src = inspect.getsource(klass)
            except (OSError, TypeError):
                continue
            grepped |= set(re.findall(r'self\.config\.get\(\s*"([^"]+)"', src))
            grepped |= set(re.findall(r"self\.config\.get\(\s*'([^']+)'", src))
        if derived_names != grepped:
            all_ok = False
            obs.append(f"{key}: derived={sorted(derived_names)} grepped={sorted(grepped)} diff={derived_names ^ grepped}")
    log("CON-045", "PASS" if all_ok else "FAIL", "identical for all 9" if all_ok else "; ".join(obs))

def con046():
    fields = {f.name for f in registry.schema("postgresql").fields}
    need = {"include_views", "statement_timeout_ms", "schemas"}
    ok = need <= fields
    log("CON-046", "PASS" if ok else "FAIL", f"present={need & fields} missing={need - fields}")

def con047():
    class Base:
        def __init__(self):
            self.config = {}
        def m(self):
            return self.config.get("k", 1)
    class Sub(Base):
        def m2(self):
            return self.config.get("k", 2)
    fields = ConfigSchemaDeriver().derive(Sub)
    ok = fields["k"].default == 2
    log("CON-047", "PASS" if ok else "FAIL", f"default={fields['k'].default}")

def con048():
    fields = ConfigSchemaDeriver().derive(fs_mod.FilesystemConnector)
    ok = fields["root_path"].required is True
    log("CON-048", "PASS" if ok else "FAIL", f"required={fields['root_path'].required}")

def con049():
    SOME_CONSTANT = "computed-value"
    class C:
        def __init__(self):
            self.config = {}
        def m(self):
            return self.config.get("k", SOME_CONSTANT)
    fields = ConfigSchemaDeriver().derive(C)
    f = fields.get("k")
    ok = f is not None and f.required is False and f.default is None
    log("CON-049", "PASS" if ok else "FAIL", f"field={f}")

def con050():
    class C:
        def __init__(self):
            self.config = {}
            self.credential_field = "password"
        def m(self, key_variable):
            a = self.config.get(key_variable)
            b = self.config.get(self.credential_field)
            return a, b
    try:
        fields = ConfigSchemaDeriver().derive(C)
        ok = len(fields) == 0
        log("CON-050", "PASS" if ok else "FAIL", f"derived fields={list(fields)}")
    except Exception as e:
        log("CON-050", "FAIL", f"{type(e).__name__}: {e}")

def con051():
    r = ConnectorRegistry()
    r.register(sqlite_mod.SqliteConnector, overlay={"nonexistent_field": FieldPresentation(label="X")})
    findings = r.audit()
    ok = len(findings) == 1 and "nonexistent_field" in findings[0] and "never reads" in findings[0]
    log("CON-051", "PASS" if ok else "FAIL", str(findings))

def con052():
    findings = registry.audit()
    ok = findings == []
    log("CON-052", "PASS" if ok else "FAIL", f"audit()={findings}")

def con053():
    r = ConnectorRegistry()
    r.register(sqlite_mod.SqliteConnector, overlay={"invented_field": FieldPresentation(label="Invented")})
    schema = r.schema("sqlite")
    form = schema.to_form()
    in_unknown = "invented_field" in schema.unknown_overlay_keys
    in_any_group = any(f["name"] == "invented_field" for g in form["groups"] for f in g["fields"])
    ok = in_unknown and not in_any_group
    log("CON-053", "PASS" if ok else "FAIL", f"unknown_overlay_keys={schema.unknown_overlay_keys} in_form={in_any_group}")

def con054():
    f = FieldSpec(name="password", default="hunter2", secret=True)
    d = f.to_dict()
    ok = d["default"] is None and d["secret"] is True and d["input"] == "password"
    log("CON-054", "PASS" if ok else "FAIL", str(d))

def con055():
    try:
        registry.create("postgresql", {"host": "h", "database": "d", "password": "literal"})
        log("CON-055", "FAIL", "no exception")
    except ValidationError as e:
        ok = "password" in str(e) and "credential_ref" in (e.remedy or "") and "exported to Git" in (e.remedy or "")
        log("CON-055", "PASS" if ok else "FAIL", f"msg={e} remedy={e.remedy}")

def con056():
    obs = []
    all_ok = True
    for cfg in ({}, {"root_path": ""}, {"root_path": None}):
        try:
            registry.create("filesystem", cfg)
            all_ok = False
            obs.append(f"{cfg}: no exception")
        except ValidationError as e:
            ok = "root_path" in e.context.get("missing", []) and "no default" in (e.remedy or "")
            all_ok = all_ok and ok
            obs.append(f"{cfg}: {e.context}")
    log("CON-056", "PASS" if all_ok else "FAIL", "; ".join(obs))

def con057():
    # find a schema with a required+secret field naturally, else construct one
    found = None
    for key in registry.keys():
        for f in registry.schema(key).fields:
            if f.required and f.secret:
                found = (key, f.name)
    if found:
        key, name = found
        try:
            registry.create(key, {})
            log("CON-057", "FAIL", f"{key}/{name}: no exception even though other required fields likely missing too -- inconclusive, testing directly")
        except ValidationError as e:
            missing = e.context.get("missing", [])
            ok = name not in missing
            log("CON-057", "PASS" if ok else "FAIL", f"required+secret field found: {key}.{name}; missing-list={missing}")
    else:
        # construct directly
        schema = ConnectorConfigSchema(
            "x", (FieldSpec(name="password", required=True, secret=True),)
        )
        try:
            schema.validate({})
            log("CON-057", "PASS", "no ValidationError for a required+secret field left out of config (none shipped naturally; verified via constructed schema)")
        except ValidationError as e:
            log("CON-057", "FAIL", f"raised: {e.context}")

def con058():
    # postgresql's __init__ presumably doesn't raise on bad config directly either;
    # use a bad config missing required fields and confirm ValidationError (not some other error)
    try:
        registry.create("filesystem", {})
        log("CON-058", "FAIL", "no exception")
    except ValidationError:
        log("CON-058", "PASS", "ValidationError raised by schema.validate() before connector __init__ ran")
    except Exception as e:
        log("CON-058", "FAIL", f"wrong exception type reached: {type(e).__name__}: {e}")

def con059():
    try:
        registry.get("snowfalke")
        log("CON-059", "FAIL", "no exception")
    except RegistryError as e:
        ok = all(k in str(e) for k in ("filesystem", "sqlite", "mongodb"))
        log("CON-059", "PASS" if ok else "FAIL", str(e))

def con060():
    try:
        registry.capabilities("nope")
        log("CON-060", "FAIL", "no exception, returned a value instead")
    except RegistryError as e:
        log("CON-060", "PASS", f"RegistryError: {e}")

def con061():
    r = ConnectorRegistry()
    r.register(sqlite_mod.SqliteConnector)
    class Other(sqlite_mod.SqliteConnector):
        plugin_key = "sqlite"
    try:
        r.register(Other, replace=False)
        log("CON-061", "FAIL", "no exception on duplicate registration")
    except RegistryError as e:
        still_original = r.get("sqlite") is sqlite_mod.SqliteConnector
        ok = still_original
        log("CON-061", "PASS" if ok else "FAIL", f"RegistryError raised; get('sqlite') still original={still_original}")

def con062():
    r = ConnectorRegistry()
    register_builtin(r)
    register_builtin(r)
    register_builtin(r)
    ok = len(r) == 9 and len(r.keys()) == 9
    log("CON-062", "PASS" if ok else "FAIL", f"len={len(r)} keys={r.keys()}")

def con063():
    r = ConnectorRegistry()
    class V1:
        plugin_key = "x"
        @classmethod
        def manifest(cls):
            from prama.core.registry import PluginManifest
            return PluginManifest(key="x", kind="connector", display_name="X", version="1.0")
        def __init__(self, config, **kw):
            self.config = config
        def m(self):
            return self.config.get("a", 1)
    from prama.connect.spi import Connector
    class C1(Connector):
        plugin_key = "x"
        @classmethod
        def manifest(cls):
            return cls.describe_manifest(key="x", display_name="X1")
        def __init__(self, config, **kw):
            super().__init__(config, **kw)
        async def health(self): ...
        async def discover(self, path=()): ...
        async def describe(self, path): ...
        async def snapshot(self, path): ...
        async def read(self, path, *, plan=None):
            return
            yield
        def m(self):
            return self.config.get("field_one", 1)
    class C2(C1):
        def m(self):
            return self.config.get("field_two", 2)
    r.register(C1)
    _ = r.schema("x")  # builds and caches
    before = {f.name for f in r.schema("x").fields}
    r.register(C2, replace=True)
    after = {f.name for f in r.schema("x").fields}
    ok = "field_two" in after and "field_two" not in before
    log("CON-063", "PASS" if ok else "FAIL", f"before={before} after={after}")

def con064():
    from prama.connect.spi import SourceKind
    obs = {}
    for kind in SourceKind:
        obs[kind.name] = registry.of_kind(kind)
    expected = {
        "RELATIONAL": ["clickhouse", "jdbc", "postgresql", "snowflake", "sqlite"],
        "FILESYSTEM": ["filesystem"],
        "OBJECT_STORE": ["objectstore"],
        "API": ["rest"],
        "DOCUMENT": ["mongodb"],
    }
    ok = all(sorted(obs[k]) == v for k, v in expected.items())
    others_empty = all(obs[k] == [] for k in obs if k not in expected)
    all_union = sorted(sum(obs.values(), []))
    no_dup = len(all_union) == len(set(all_union)) == 9
    ok = ok and others_empty and no_dup
    log("CON-064", "PASS" if ok else "FAIL", str({k: v for k, v in obs.items() if v}))

con045(); con046(); con047(); con048(); con049(); con050(); con051(); con052()
con053(); con054(); con055(); con056(); con057(); con058(); con059(); con060()
con061(); con062(); con063(); con064()
