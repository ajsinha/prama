import sys, os, importlib.util
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.classify.plugins import (scan_source, forbidden_imports, check_determinism,
    implementation_hash, PluginRegistry, FORBIDDEN, FORBIDDEN_PRAMA, FORBIDDEN_CALLS,
    FORBIDDEN_DYNAMIC, FORBIDDEN_DYNAMIC_ATTRIBUTES, PROBES)
from prama.classify.validators import SemanticValidator, Judgement, VALID
from prama.core.errors import ValidationError

D = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/dom/plugtest"

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

def load(fname, classname, modname=None):
    path = os.path.join(D, fname)
    mn = modname or ("plugmod_" + fname.replace("/", "_")[:-3])
    spec = importlib.util.spec_from_file_location(mn, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mn] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, classname)()

@block("CLS-109")
def _():
    v = load("v_clean.py", "CleanValidator")
    reg = PluginRegistry()
    prov = reg.admit(v, distribution="acme-validators")
    ok = prov.distribution=="acme-validators" and len(prov.implementation_hash)==32 and prov.module
    R("CLS-109", ok, f"provenance={prov}")

@block("CLS-110")
def _():
    v = load("v_recompile.py", "RecompileValidator")
    reg = PluginRegistry()
    try:
        prov = reg.admit(v)
        R("CLS-110", True, f"admitted: {prov}")
    except ValidationError as e:
        R("CLS-110", False, f"refused: {e}")

@block("CLS-111")
def _():
    detail = []
    ok = True
    for fname, cls in [("v_compilebuiltin.py","CompileBuiltinValidator"),
                        ("v_exec.py","ExecValidator"),("v_eval.py","EvalValidator")]:
        v = load(fname, cls)
        reg = PluginRegistry()
        try:
            reg.admit(v)
            ok = False
            detail.append(f"{cls}: NOT refused")
        except ValidationError as e:
            named = 'arbitrary code execution' in str(e)
            ok &= named
            detail.append(f"{cls}: refused, named_reason={named}")
    R("CLS-111", ok, "; ".join(detail))

@block("CLS-112")
def _():
    v = load("v_dunderimport.py", "DunderImportValidator")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-112", False, "not refused")
    except ValidationError as e:
        R("CLS-112", True, f"{e}")

@block("CLS-113")
def _():
    v = load("v_importlib_attr.py", "ImportlibAttrValidator")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-113", False, "not refused")
    except ValidationError as e:
        R("CLS-113", True, f"{e}")

@block("CLS-114")
def _():
    v = load("v_import_module_bare.py", "ImportModuleBareValidator")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-114", False, "not refused -- evasion open")
    except ValidationError as e:
        R("CLS-114", True, f"refused: {e}")

@block("CLS-115")
def _():
    files = [("v_time_gmtime.py","V"),("v_datetime_now.py","V"),("v_datetime_utcnow.py","V"),
              ("v_time_monotonic.py","V"),("v_time_perfcounter.py","V"),("v_time_timens.py","V"),
              ("v_date_today.py","V")]
    detail=[]
    ok=True
    for fname, cls in files:
        v = load(fname, cls)
        reg = PluginRegistry()
        try:
            reg.admit(v)
            ok=False
            detail.append(f"{fname}: NOT refused")
        except ValidationError as e:
            named = 'clock' in str(e).lower() or 'unreplayable' in str(e).lower()
            ok &= named
            detail.append(f"{fname}: refused({named})")
    R("CLS-115", ok, "; ".join(detail))

@block("CLS-116")
def _():
    v = load("v_datetime_strptime.py", "V")
    reg = PluginRegistry()
    try:
        prov = reg.admit(v)
        R("CLS-116", True, f"admitted: {prov.name}")
    except ValidationError as e:
        R("CLS-116", False, f"refused: {e}")

@block("CLS-117")
def _():
    v = load("v_aliased_clock.py", "V")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-117", False, "not refused")
    except ValidationError as e:
        R("CLS-117", True, f"{e}")

@block("CLS-118")
def _():
    mods = ['socket','urllib.request','requests','httpx','subprocess','os','os.path','pathlib','random','secrets']
    detail=[]
    ok=True
    for mod in mods:
        fname = f"v_ban_{mod.replace('.', '_')}.py"
        path = os.path.join(D, fname)
        found = scan_source(path)
        flagged = any(m==mod or m.startswith(mod+'.') for m,_ in found)
        ok &= flagged
        detail.append(f"{mod}: flagged_by_scan={flagged}")
    R("CLS-118", ok, "; ".join(detail))

@block("CLS-119")
def _():
    mods = ['io','shutil','tempfile','asyncio','platform','getpass','ctypes','multiprocessing','sqlite3','ssl','ftplib','smtplib','importlib']
    detail={}
    for mod in mods:
        fname = f"v_gap_{mod.replace('.', '_')}.py"
        path = os.path.join(D, fname)
        found = scan_source(path)
        flagged = [(m,why) for m,why in found if m==mod or m.startswith(mod+'.')]
        detail[mod] = "flagged" if flagged else "NOT flagged (allowlisted by omission)"
    R("CLS-119", None, f"{detail}")

@block("CLS-120")
def _():
    mods = ['openai','anthropic','prama.llm']
    detail=[]
    ok=True
    for mod in mods:
        fname = f"v_model_{mod.replace('.', '_')}.py"
        path = os.path.join(D, fname)
        found = scan_source(path)
        flagged = [ (m,why) for m,why in found if m==mod or m.startswith(mod+'.') ]
        named = flagged and all('CON-007' in why for m,why in flagged)
        ok &= bool(flagged) and named
        detail.append(f"{mod}: flagged={flagged}")
    R("CLS-120", ok, "; ".join(detail))

@block("CLS-121")
def _():
    v = load("v_core_errors.py", "V")
    reg = PluginRegistry()
    try:
        prov = reg.admit(v)
        R("CLS-121", True, f"admitted: {prov.name}")
    except ValidationError as e:
        R("CLS-121", False, f"refused: {e}")

@block("CLS-122")
def _():
    path = os.path.join(D, "v_llmx.py")
    found = scan_source(path)
    flagged = [f for f in found if 'llmx' in f[0]]
    R("CLS-122", not flagged, f"scan_source finds={found} (prama.llmx must NOT be flagged as FORBIDDEN_PRAMA)")

@block("CLS-123")
def _():
    os.makedirs(os.path.join(D,"sibling_test"), exist_ok=True)
    with open(os.path.join(D,"sibling_test","helpers.py"),"w") as f:
        f.write("import socket\n")
    with open(os.path.join(D,"sibling_test","v_sibling.py"),"w") as f:
        f.write("import helpers\nfrom prama.classify.validators import SemanticValidator, VALID\n"
                "class V(SemanticValidator):\n    name='sib'\n    label='x'\n    def check(self,value):\n        return VALID\n")
    sys.path.insert(0, os.path.join(D,"sibling_test"))
    v = load("sibling_test/v_sibling.py", "V")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-123", False, "not refused -- sibling helper impurity missed")
    except ValidationError as e:
        named = 'helpers.py' in str(e)
        R("CLS-123", named, f"{e}")

@block("CLS-124")
def _():
    pkgdir = os.path.join(D,"subpkg_test")
    os.makedirs(os.path.join(pkgdir,"helpers"), exist_ok=True)
    open(os.path.join(pkgdir,"helpers","__init__.py"),"w").close()
    with open(os.path.join(pkgdir,"helpers","impure.py"),"w") as f:
        f.write("import socket\ndef check(v): return True\n")
    with open(os.path.join(pkgdir,"v_subpkg.py"),"w") as f:
        f.write("from .helpers.impure import check as _c\nfrom prama.classify.validators import SemanticValidator, VALID\n"
                "class V(SemanticValidator):\n    name='subpkg'\n    label='x'\n    def check(self,value):\n        return VALID\n")
    open(os.path.join(pkgdir,"__init__.py"),"w").close()
    # import as part of a package so relative import works
    sys.path.insert(0, D)
    import importlib
    mod = importlib.import_module("subpkg_test.v_subpkg")
    v = mod.V()
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-124", False, "not refused -- sub-package helper impurity missed, evasion still open")
    except ValidationError as e:
        R("CLS-124", True, f"refused: {e}")

@block("CLS-125")
def _():
    cyc = os.path.join(D,"cyc_test")
    os.makedirs(cyc, exist_ok=True)
    with open(os.path.join(cyc,"a.py"),"w") as f:
        f.write("import b\n")
    with open(os.path.join(cyc,"b.py"),"w") as f:
        f.write("import a\n")
    with open(os.path.join(cyc,"v_cyc.py"),"w") as f:
        f.write("import a\nfrom prama.classify.validators import SemanticValidator, VALID\n"
                "class V(SemanticValidator):\n    name='cyc'\n    label='x'\n    def check(self,value):\n        return VALID\n")
    sys.path.insert(0, cyc)
    import time
    v = load("cyc_test/v_cyc.py", "V")
    reg = PluginRegistry()
    t0=time.time()
    try:
        reg.admit(v)
        dt=time.time()-t0
        R("CLS-125", dt<5, f"admitted in {dt:.3f}s (terminated OK)")
    except ValidationError as e:
        dt=time.time()-t0
        R("CLS-125", dt<5, f"refused in {dt:.3f}s (terminated OK): {e}")

@block("CLS-126")
def _():
    import time
    v = load("v_clean.py", "CleanValidator")
    t0=time.time()
    result = forbidden_imports(v)
    dt = time.time()-t0
    R("CLS-126", dt<2.0, f"forbidden_imports took {dt:.3f}s (stdlib/site-packages not walked, bounded)")

@block("CLS-127")
def _():
    with open(os.path.join(D,"v_syntax_error_helper.py"),"w") as f:
        f.write("import socket\ndef broken(:\n")
    with open(os.path.join(D,"v_uses_broken.py"),"w") as f:
        f.write("import v_syntax_error_helper\nfrom prama.classify.validators import SemanticValidator, VALID\n"
                "class V(SemanticValidator):\n    name='brk'\n    label='x'\n    def check(self,value):\n        return VALID\n")
    found = scan_source(os.path.join(D,"v_syntax_error_helper.py"))
    R("CLS-127", None, f"scan_source on unparseable file returns={found} (docstring: 'the loader refuses it on import instead' -- but this helper is never imported by the admit() path when the validator itself doesn't import it at Python import time either; scan just returns [] silently)")

@block("CLS-128")
def _():
    with open(os.path.join(D,"v_nondeterministic.py"),"w") as f:
        f.write(
"""
_counter = [0]
from prama.classify.validators import SemanticValidator, Judgement, VALID
class V(SemanticValidator):
    name = 'nondet'
    label = 'x'
    def check(self, value):
        _counter[0] += 1
        return VALID if _counter[0] % 2 == 0 else Judgement(valid=False, reason='odd')
""")
    v = load("v_nondeterministic.py", "V")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-128", False, "not refused -- non-determinism missed")
    except ValidationError as e:
        R("CLS-128", 'two answers' in str(e), f"{e}")

@block("CLS-129")
def _():
    fpath = os.path.join(D,"v_raises_empty.py")
    with open(fpath,"w") as f:
        f.write(
"from prama.classify.validators import SemanticValidator, VALID\n"
"class V(SemanticValidator):\n"
"    name = 'raisesempty'\n"
"    label = 'x'\n"
"    def check(self, value):\n"
"        return VALID if value[9999] else VALID\n"
        )
    assert open(fpath).read().count("9999")==1, "write did not take effect: " + open(fpath).read()
    v = load("v_raises_empty.py", "V")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-129", False, "not refused -- a check() that raises on some probe should be refused")
    except ValidationError as e:
        R("CLS-129", 'first blank' in str(e) or 'raised on' in str(e), f"{e} -- NOTE: probe '' and ' ' never reach check() because SemanticValidator.judge() already shields blank input (verified by CLS-002/003); the refusal here fires on a later non-blank probe such as '0', which is judge()'s working-as-designed blank guard plus the raise-detection both operating correctly together")

@block("CLS-130")
def _():
    ok = None not in PROBES
    fpath = os.path.join(D,"v_raises_on_none.py")
    with open(fpath,"w") as f:
        f.write(
"from prama.classify.validators import SemanticValidator, VALID\n"
"class V(SemanticValidator):\n"
"    name = 'raisesnone'\n"
"    label = 'x'\n"
"    def check(self, value):\n"
"        return VALID\n"
"    def judge(self, value):\n"
"        return VALID if len(value) >= 0 else VALID\n"
        )
    assert "def check" in open(fpath).read(), "write did not take effect: " + open(fpath).read()
    v = load("v_raises_on_none.py", "V")
    reg = PluginRegistry()
    try:
        reg.admit(v)
        R("CLS-130", False, f"admitted despite overridden judge() raising on None (PROBES contains no None: {ok}) -- confirms the gap")
    except ValidationError as e:
        R("CLS-130", True, f"refused anyway: {e}")
    except Exception as e:
        R("CLS-130", False, f"admit() itself raised unhandled {type(e).__name__}: {e} (worse than a refusal)")

@block("CLS-131")
def _():
    with open(os.path.join(D,"v_two_in_one.py"),"w") as f:
        f.write(
"""
from prama.classify.validators import SemanticValidator, VALID
class A(SemanticValidator):
    name = 'twoinone_a'
    label = 'x'
    def check(self, value):
        return VALID
class B(SemanticValidator):
    name = 'twoinone_b'
    label = 'x'
    def check(self, value):
        return VALID
""")
    a1 = load("v_two_in_one.py", "A")
    b1 = load("v_two_in_one.py", "B")
    h_a1 = implementation_hash(a1)
    h_b1 = implementation_hash(b1)
    with open(os.path.join(D,"v_two_in_one.py"),"w") as f:
        f.write(
"""
from prama.classify.validators import SemanticValidator, VALID, Judgement
class A(SemanticValidator):
    name = 'twoinone_a'
    label = 'x'
    def check(self, value):
        return Judgement(valid=False, reason='changed')
class B(SemanticValidator):
    name = 'twoinone_b'
    label = 'x'
    def check(self, value):
        return VALID
""")
    a2 = load("v_two_in_one.py", "A")
    b2 = load("v_two_in_one.py", "B")
    h_a2 = implementation_hash(a2)
    h_b2 = implementation_hash(b2)
    ok = h_a1!=h_a2 and h_b1==h_b2
    R("CLS-131", ok, f"A_changed:{h_a1}->{h_a2} (differ={h_a1!=h_a2}); B_unchanged:{h_b1}->{h_b2} (same={h_b1==h_b2})")

@block("CLS-132")
def _():
    class Dynamic(SemanticValidator):
        name = 'dyn'
        label = 'x'
        def check(self, value):
            return VALID
    DynType = type('DynBuilt', (SemanticValidator,), {'name':'dynbuilt','label':'x','check': lambda self,v: VALID})
    inst = DynType()
    try:
        implementation_hash(inst)
        R("CLS-132", False, "no exception for dynamically-built class")
    except ValidationError as e:
        R("CLS-132", True, f"{e}")

@block("CLS-133")
def _():
    with open(os.path.join(D,"v_bad_import.py"),"w") as f:
        f.write("import socket\nfrom prama.classify.validators import SemanticValidator, VALID\n"
                "class V(SemanticValidator):\n    name='badimp'\n    label='x'\n    def check(self,v): return VALID\n")
    good1 = load("v_clean.py", "CleanValidator")
    bad = load("v_bad_import.py", "V")
    good2 = load("v_recompile.py", "RecompileValidator")
    reg = PluginRegistry()
    admitted = []
    refused = []
    for v in (good1, bad, good2):
        try:
            reg.admit(v)
            admitted.append(v.name)
        except ValidationError as e:
            refused.append((v.name, str(e)[:60]))
    ok = len(admitted)==2 and len(refused)==1
    R("CLS-133", ok, f"admitted={admitted} refused={refused}")

@block("CLS-134")
def _():
    reg = PluginRegistry()
    reg.admit(load("v_clean.py","CleanValidator"))
    try:
        reg.admit(load("v_bad_import.py","V"))
    except ValidationError:
        pass
    reg.admit(load("v_recompile.py","RecompileValidator"))
    names = reg.names()
    discoverable = 'badimp' not in names
    R("CLS-134", None, f"registry.names()={names}; 'badimp' present={not discoverable} -- PluginRegistry exposes only admitted names; nothing in this object records the refused ones for later discovery")

@block("CLS-135")
def _():
    import prama.classify.plugins as pmod
    doc = pmod.scan_source.__doc__
    ok = 'has never existed' in doc or 'no CLI front end' in doc
    R("CLS-135", ok, f"docstring_honest_about_absence={ok}")

print("=== CLS plugins 109-135 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
