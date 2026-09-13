import sys, os
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.registry import Registry, RegistryCatalogue, Plugin, PluginManifest, Capability, _entry_points_for
from prama.core.errors import RegistryError
from abc import ABC, abstractmethod

class BasePlugin(Plugin):
    pass

def mk_manifest(key="k", kind="connectors", **kw):
    return PluginManifest(key=key, kind=kind, display_name=key, version="1.0", **kw)

# CFG-246: subclass that does not implement manifest -- ABC uninstantiable
try:
    class NoManifest(BasePlugin):
        pass
    NoManifest()
    R("CFG-246", False, "instantiated despite missing manifest()")
except TypeError as e:
    R("CFG-246", "abstract" in str(e).lower(), str(e))

reg = Registry("connectors", BasePlugin)

# CFG-247
class RaisingManifest(BasePlugin):
    @classmethod
    def manifest(cls):
        raise ValueError("boom")
try:
    reg.register(RaisingManifest)
    R("CFG-247", False, "no exception")
except RegistryError as e:
    ok = "ValueError" in str(e) and "pure classmethod" in e.remedy
    R("CFG-247", ok, f"{e}; remedy={e.remedy}")

# CFG-248
class WrongType(BasePlugin):
    @classmethod
    def manifest(cls):
        return {"key": "x"}
try:
    reg.register(WrongType)
    R("CFG-248", False, "no exception")
except RegistryError as e:
    R("CFG-248", "WrongType" in str(e), str(e))

# CFG-249
class EmptyKey(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="")
try:
    reg.register(EmptyKey)
    R("CFG-249", False, "no exception")
except RegistryError as e:
    R("CFG-249", "stable, unique key" in e.remedy, e.remedy)

# CFG-250
class WrongKind(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="wk", kind="notifiers")
try:
    reg.register(WrongKind)
    R("CFG-250", False, "no exception")
except RegistryError as e:
    ok = "notifiers" in str(e) and "connectors" in str(e)
    R("CFG-250", ok, str(e))

# CFG-251
class Unrelated:
    pass
try:
    reg.register(Unrelated)
    R("CFG-251", False, "no exception")
except RegistryError as e:
    R("CFG-251", "BasePlugin" in e.remedy, e.remedy)

# CFG-252
class GoodOne(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="good1")
reg.register(GoodOne)
try:
    reg.register(GoodOne)
    R("CFG-252", False, "duplicate accepted without replace=True")
except RegistryError:
    try:
        reg.register(GoodOne, replace=True)
        R("CFG-252", True, "refused without replace, accepted with replace=True")
    except RegistryError as e:
        R("CFG-252", False, f"replace=True still refused: {e}")

class GoodTwo(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="good2")
class GoodThree(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="good3")
reg.register(GoodTwo)
reg.register(GoodThree)

# CFG-253
try:
    reg.get("nope")
    R("CFG-253", False, "no exception")
except RegistryError as e:
    keys_in_remedy = all(k in e.remedy for k in ("good1", "good2", "good3"))
    R("CFG-253", keys_in_remedy, e.remedy)

# CFG-254
empty_reg = Registry("scorers", BasePlugin)
try:
    empty_reg.get("x")
    R("CFG-254", False, "no exception")
except RegistryError as e:
    R("CFG-254", "(none)" in e.remedy and "Available: ." not in e.remedy, e.remedy)

# CFG-255
reg.disable(["good1"])
try:
    reg.get("good1")
    R("CFG-255", False, "no exception")
except RegistryError as e:
    ok = "has been disabled" in str(e) and "disabled in code, not in configuration" in e.remedy
    R("CFG-255", ok, str(e))

# CFG-256: plugins.disabled config key wiring
import subprocess
hits = subprocess.run(["grep", "-rn", r"\.disable(", "src/prama", "--include=*.py"], capture_output=True, text=True).stdout
R("CFG-256", bool(hits.strip()), f"no call to Registry.disable(...) found anywhere in src/prama (grep for '.disable(' across *.py): {hits!r}; "
  f"config/application.yaml ships plugins.disabled: [] but nothing reads it")

# CFG-257
R("CFG-257", reg.keys() == sorted(["good2","good3"]) or set(reg.keys())=={"good2","good3"},
  f"keys()={reg.keys()}; 'good1' in reg={'good1' in reg}; len={len(reg)}")
ok257 = set(reg.keys()) == {"good2","good3"} and ("good1" in reg) is False and len(reg) == 2
R("CFG-257", ok257, f"keys()={reg.keys()}, 'good1' in reg={'good1' in reg}, len={len(reg)}")

# CFG-258
try:
    mans = reg.manifests()
    R("CFG-258", all(m.key != "good1" for m in mans) and len(mans)==2, f"manifests keys={[m.key for m in mans]}")
except Exception as e:
    R("CFG-258", False, f"{type(e).__name__}: {e}")

# CFG-259 / CFG-260: broken entry point via a fake group
class FakeBrokenEP:
    name = "broken-ep"
    def load(self):
        raise ImportError("cannot import broken module")
class FakeGoodEP:
    name = "good-ep"
    def load(self):
        return GoodFourth
class GoodFourth(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="good4", kind="backends")

reg2 = Registry("backends", BasePlugin, entry_point_group="prama.backends")
import prama.core.registry as registry_mod
orig_ep_for = registry_mod._entry_points_for
registry_mod._entry_points_for = lambda group: [FakeBrokenEP(), FakeGoodEP()]
import logging, io
logbuf = io.StringIO()
h = logging.StreamHandler(logbuf)
logging.getLogger("prama.core.registry").addHandler(h)
logging.getLogger("prama.core.registry").setLevel(logging.WARNING)
count = reg2.discover()
logging.getLogger("prama.core.registry").removeHandler(h)
registry_mod._entry_points_for = orig_ep_for
logtext = logbuf.getvalue()
R("CFG-259", count == 1 and "broken-ep" in logtext and "prama.backends" in logtext,
  f"loaded={count}, log contains broken-ep and group name: {'broken-ep' in logtext and 'prama.backends' in logtext}; log={logtext.strip()[:200]!r}")

# CFG-260: is the failure visible anywhere OTHER than the log? (health output claim)
has_failure_state = hasattr(reg2, "_failed") or hasattr(reg2, "failures") or hasattr(reg2, "discovery_errors")
R("CFG-260", has_failure_state, f"Registry exposes no failure-tracking attribute for discover() (checked _failed/failures/discovery_errors); only a log.warning is emitted, and grep of src/prama/api shows /health reports only database state -- the docstring's claim 'visible in health output' is not backed by any mechanism")

# CFG-261
reg3 = Registry("scorers", BasePlugin)  # no entry_point_group
n = reg3.discover()
R("CFG-261", n == 0, repr(n))

# CFG-262
class BrokenMetadata:
    def __call__(self, *a, **kw):
        raise OSError("corrupted metadata directory")
import importlib.metadata as im
orig_entry_points = im.entry_points
im.entry_points = BrokenMetadata()
try:
    result262 = _entry_points_for("prama.connectors")
finally:
    im.entry_points = orig_entry_points
R("CFG-262", result262 != [] or False,
  f"_entry_points_for() on a broken metadata call returned {result262!r} -- 'except Exception: return []' silently reports zero plugins found, indistinguishable from an empty install; enumeration failure is not surfaced at all")

# CFG-263
reg4 = Registry("validators", BasePlugin)
class HasCap(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="hascap", kind="validators", capabilities=(Capability("pushdown.sql"),))
class NoCap(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="nocap", kind="validators")
reg4.register(HasCap)
reg4.register(NoCap)
withcap = reg4.with_capability("pushdown.sql")
R("CFG-263", len(withcap)==1 and withcap[0].key=="hascap", f"{[m.key for m in withcap]}")

# CFG-264
c1 = Capability("pushdown.sql", {"b": 2, "a": 1})
c2 = Capability("pushdown.sql", {"a": 1, "b": 2})
R("CFG-264", str(c1) == str(c2) == "pushdown.sql[a=1,b=2]", f"{str(c1)!r} vs {str(c2)!r}")

# CFG-265
m265 = mk_manifest(key="m265", capabilities=(Capability("cap1", {"x": 5}),))
R("CFG-265", m265.attribute("nope", "attr", "DEFAULT")=="DEFAULT" and m265.attribute("cap1","noattr","DEFAULT2")=="DEFAULT2",
  f"{m265.attribute('nope','attr','DEFAULT')!r}, {m265.attribute('cap1','noattr','DEFAULT2')!r}")

# CFG-266
m266 = mk_manifest(key="m266")
R("CFG-266", m266.verification == "code_complete", repr(m266.verification))

# CFG-267
cat = RegistryCatalogue()
cat.create("connectors", BasePlugin)
try:
    cat.create("connectors", BasePlugin)
    R("CFG-267", False, "no exception")
except RegistryError as e:
    R("CFG-267", "of(kind)" in e.remedy or "of(" in e.remedy, e.remedy)

# CFG-268
cat2 = RegistryCatalogue()
cat2.create("connectors", BasePlugin)
cat2.create("backends", BasePlugin)
cat2.create("scorers", BasePlugin)
try:
    cat2.of("nope")
    R("CFG-268", False, "no exception")
except RegistryError as e:
    ok268 = all(k in e.remedy for k in ("connectors","backends","scorers"))
    R("CFG-268", ok268, e.remedy)

# CFG-269
cat3 = RegistryCatalogue()
r1 = cat3.create("connectors", BasePlugin, entry_point_group="prama.connectors")
r2 = cat3.create("backends", BasePlugin, entry_point_group="prama.backends")
r3 = cat3.create("scorers", BasePlugin, entry_point_group="prama.scorers")
counts = cat3.discover_all(groups=["prama.connectors", "prama.backends"])
R("CFG-269", set(counts.keys())=={"connectors","backends"}, f"discover_all touched: {sorted(counts.keys())}")

# CFG-270
catA = RegistryCatalogue()
catB = RegistryCatalogue()
regA = catA.create("connectors", BasePlugin)
class OnlyInA(BasePlugin):
    @classmethod
    def manifest(cls):
        return mk_manifest(key="onlyA")
regA.register(OnlyInA)
try:
    catB.of("connectors")
    R("CFG-270", False, "catalogue B unexpectedly has a 'connectors' registry")
except RegistryError:
    R("CFG-270", True, "catalogue B has no knowledge of catalogue A's registry, as expected")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
