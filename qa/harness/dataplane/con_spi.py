import asyncio, dataclasses, datetime as dt
from prama.connect.spi import (
    Connector, ConnectorError, HealthReport, HealthState, DiscoveredObject,
    ObjectSchema, ColumnSchema, SnapshotKind, Snapshot, SamplingStrategy,
    SamplePlan, ReadPolicy, ReadResult, Verification, SourceKind,
)
from prama.connect.capability import PushdownFeature
from prama.connect.registry import ConnectorRegistry
from prama.connect.builtin import register_builtin

results = []
def log(id_, res, obs):
    results.append((id_, res, obs))
    print(f"{id_}: {res} :: {obs}")

# CON-001
try:
    class Bare(Connector):
        pass
    try:
        Bare({})
        log("CON-001", "FAIL", "instantiation succeeded, no TypeError")
    except TypeError as e:
        names = ["health","discover","describe","snapshot","read"]
        missing_all = all(n in str(e) for n in names)
        log("CON-001", "PASS" if missing_all else "FAIL", str(e))
except Exception as e:
    log("CON-001", "FAIL", f"unexpected {type(e).__name__}: {e}")

# Minimal concrete connector for CON-002..005
class Minimal(Connector):
    @classmethod
    def manifest(cls):
        return cls.describe_manifest(key="minimal", display_name="Minimal")
    async def health(self): return HealthReport(state=HealthState.HEALTHY)
    async def discover(self, path=()): return []
    async def describe(self, path): return ObjectSchema(path=path, columns=())
    async def snapshot(self, path):
        return Snapshot(kind=SnapshotKind.WALL_CLOCK, identifier="x", captured_at=dt.datetime.now(dt.UTC))
    async def read(self, path, *, plan=None):
        return
        yield

class Recording(Minimal):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = []
    async def open(self):
        self.calls.append("open")
    async def close(self):
        self.calls.append("close")

async def con002():
    c = Minimal({})
    r1 = await c.open()
    r2 = await c.close()
    ok = r1 is None and r2 is None
    log("CON-002", "PASS" if ok else "FAIL", f"open()->{r1!r} close()->{r2!r}")

async def con003():
    c = Recording({})
    async with c as ctx:
        pass
    ok = c.calls == ["open", "close"] and ctx is c
    log("CON-003", "PASS" if ok else "FAIL", f"calls={c.calls} ctx_is_c={ctx is c}")

async def con004():
    c = Recording({})
    raised = False
    try:
        async with c:
            raise RuntimeError("boom")
    except RuntimeError:
        raised = True
    ok = raised and c.calls == ["open", "close"]
    log("CON-004", "PASS" if ok else "FAIL", f"raised={raised} calls={c.calls}")

async def con005():
    c = Minimal({})
    await c.close()
    await c.close()
    log("CON-005", "PASS", "second close() raised nothing")

async def con006():
    # Use each shipped connector kind, unopened, call describe/read/snapshot
    from prama.connect.sources.sqlite import SqliteConnector
    from prama.connect.sources.filesystem import FilesystemConnector
    from prama.connect.sources.rest import RestConnector
    from prama.connect.sources.mongo import MongoConnector
    kinds = {
        "sqlite": SqliteConnector({"database_path": "/nonexistent.db"}),
        "filesystem": FilesystemConnector({"root_path": "/nonexistent"}),
        "rest": RestConnector({"base_url": "http://localhost:1"}),
        "mongodb": MongoConnector({"uri": "mongodb://localhost:1", "database": "d"}),
    }
    obs = []
    all_ok = True
    for name, c in kinds.items():
        for method, args in [("describe", ((),)), ("snapshot", ((),))]:
            try:
                await getattr(c, method)(*args)
                obs.append(f"{name}.{method}: no error")
                all_ok = False
            except ConnectorError as e:
                code = getattr(e, "code", None)
                ok = code == "CONNECT.NOT_OPEN"
                obs.append(f"{name}.{method}: code={code}")
                all_ok = all_ok and ok
            except Exception as e:
                obs.append(f"{name}.{method}: {type(e).__name__}: {e}")
                all_ok = False
        # read is an async generator; must consume to trigger body
        try:
            gen = c.read(())
            await gen.__anext__()
            obs.append(f"{name}.read: no error")
            all_ok = False
        except ConnectorError as e:
            code = getattr(e, "code", None)
            ok = code == "CONNECT.NOT_OPEN"
            obs.append(f"{name}.read: code={code}")
            all_ok = all_ok and ok
        except StopAsyncIteration:
            obs.append(f"{name}.read: StopAsyncIteration (empty, no error)")
            all_ok = False
        except Exception as e:
            obs.append(f"{name}.read: {type(e).__name__}: {e}")
            all_ok = False
    log("CON-006", "PASS" if all_ok else "FAIL", "; ".join(obs))

async def con007():
    c = Minimal({})
    try:
        await c.run_metric_query("SELECT 1")
        log("CON-007", "FAIL", "no exception raised")
    except ConnectorError as e:
        ok = "Minimal" in str(e) and e.remedy and "can_run_controls" in e.remedy
        log("CON-007", "PASS" if ok else "FAIL", f"msg={e} remedy={getattr(e,'remedy',None)}")

def con008():
    c = Minimal({})
    ok = c.can_run_controls is False
    log("CON-008", "PASS" if ok else "FAIL", f"can_run_controls={c.can_run_controls}")

def con009():
    r = register_builtin(ConnectorRegistry())
    obs = []
    all_ok = True
    empty_keys = []
    for key in r.keys():
        cls = r.get(key)
        inst = cls.__new__(cls)  # avoid __init__ requirements
        caps = r.capabilities(key).to_capabilities()
        can_run = cls.can_run_controls.fget(inst) if isinstance(cls.can_run_controls, property) else None
        if len(caps) == 0:
            empty_keys.append(key)
            if can_run:
                all_ok = False
                obs.append(f"{key}: empty matrix but can_run_controls True")
    ok = all_ok and set(empty_keys) == {"rest", "mongodb"}
    log("CON-009", "PASS" if ok else "FAIL", f"empty_keys={sorted(empty_keys)} (expected rest+mongodb)")

async def con010():
    c = Minimal({})
    try:
        await c.execute_plan(object())
        log("CON-010", "FAIL", "no exception")
    except ConnectorError as e:
        code = getattr(e, "code", None)
        ok = code == "CONNECT.NO_PUSHDOWN" and code != "CONNECT.ERROR" and e.remedy and "Arrow" in e.remedy
        log("CON-010", "PASS" if ok else "FAIL", f"code={code} remedy={e.remedy}")

def con011():
    from prama.connect.sources.sqlite import SqliteConnector
    c = SqliteConnector({"database_path": "/nonexistent.db"})
    a = c.supports("pushdown.sql")
    b = c.supports("pushdown.regex")
    cc = c.supports("")
    ok = (a, b, cc) == (True, False, False)
    log("CON-011", "PASS" if ok else "FAIL", f"sql={a} regex={b} empty={cc}")

def con012():
    c = Minimal({})  # declares nothing
    try:
        c.require_predicate_support(SamplePlan(predicate="d = '2026-04-01'"))
        log("CON-012", "FAIL", "no exception")
    except ConnectorError as e:
        code = getattr(e, "code", None)
        ctx = getattr(e, "context", {})
        ok = code == "CONNECT.NO_PREDICATE" and ctx.get("predicate") == "d = '2026-04-01'" and "segment" in (e.remedy or "")
        log("CON-012", "PASS" if ok else "FAIL", f"code={code} ctx={ctx} remedy={e.remedy}")

def con013():
    c = Minimal({})
    r = c.require_predicate_support(SamplePlan())
    ok = r is None
    log("CON-013", "PASS" if ok else "FAIL", f"returned {r!r}")

def con015():
    a = SamplePlan().is_complete
    b = SamplePlan(predicate="x").is_complete
    cc = SamplePlan(strategy=SamplingStrategy.HEAD).is_complete
    ok = (a, b, cc) == (True, False, False)
    log("CON-015", "PASS" if ok else "FAIL", f"{a},{b},{cc}")

def con016():
    reps = {s: s.is_representative for s in SamplingStrategy}
    ok = all(v == (s is not SamplingStrategy.HEAD) for s, v in reps.items())
    log("CON-016", "PASS" if ok else "FAIL", str({s.name: v for s, v in reps.items()}))

def con017():
    obs = {}
    obs["full"] = SamplePlan(strategy=SamplingStrategy.FULL).describe()
    obs["full_pred"] = SamplePlan(strategy=SamplingStrategy.FULL, predicate="d='2026-04-01'").describe()
    obs["systematic"] = SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, fraction=0.015).describe()
    obs["reservoir"] = SamplePlan(strategy=SamplingStrategy.RESERVOIR, rows=1000).describe()
    obs["stratified"] = SamplePlan(strategy=SamplingStrategy.STRATIFIED).describe()
    expected = {
        "full": "full scan",
        "full_pred": "full scan where d='2026-04-01'",
        "systematic": "systematic sample at 1.5%",
        "reservoir": "reservoir sample of 1,000 rows",
        "stratified": "stratified",
    }
    ok = obs == expected
    log("CON-017", "PASS" if ok else "FAIL", str(obs))

def con018():
    exact = {k: k.is_exact for k in SnapshotKind}
    falses = [k.name for k, v in exact.items() if not v]
    ok = set(falses) == {"WALL_CLOCK", "OBJECT_LISTING"}
    log("CON-018", "PASS" if ok else "FAIL", f"false_for={sorted(falses)}")

def con019():
    obs = []
    all_ok = True
    for kind in SnapshotKind:
        for detail in ({}, {"a": 1}):
            snap = Snapshot(kind=kind, identifier="id1", captured_at=dt.datetime.now(dt.UTC), detail=detail)
            d = snap.to_dict()
            has_keys = all(k in d for k in ("kind", "id", "captured_at", "exact"))
            detail_ok = ("detail" in d) == bool(detail)
            if not (has_keys and detail_ok):
                all_ok = False
                obs.append(f"{kind}/{detail}: keys={list(d.keys())}")
    log("CON-019", "PASS" if all_ok else "FAIL", "all present as expected" if all_ok else "; ".join(obs))

def con020():
    obs = []
    all_ok = True
    expected_usable = {HealthState.HEALTHY, HealthState.DEGRADED}
    for state in HealthState:
        r = HealthReport(state=state)
        usable = r.is_usable
        access = r.needs_access_request
        reconfig = r.needs_reconfiguration
        exp_usable = state in expected_usable
        exp_access = state is HealthState.UNAUTHORISED
        exp_reconfig = state is HealthState.MISCONFIGURED
        if (usable, access, reconfig) != (exp_usable, exp_access, exp_reconfig):
            all_ok = False
            obs.append(f"{state}: got ({usable},{access},{reconfig}) exp ({exp_usable},{exp_access},{exp_reconfig})")
    # healthy + missing_permissions
    r2 = HealthReport(state=HealthState.HEALTHY, missing_permissions=("READ",))
    if not r2.needs_access_request:
        all_ok = False
        obs.append(f"HEALTHY+missing_permissions.needs_access_request={r2.needs_access_request}")
    log("CON-020", "PASS" if all_ok else "FAIL", "matches" if all_ok else "; ".join(obs))

def con021():
    p0 = ReadPolicy()
    r0 = p0.permits_path(("risk", "positions"))
    p1 = ReadPolicy(allowed_paths=("risk.*",))
    r1 = p1.permits_path(("risk", "positions"))
    r2 = p1.permits_path(("risk",))
    r3 = p1.permits_path(("riskier", "positions"))
    r4 = p1.permits_path(())
    obs = f"empty_policy={r0} risk.positions={r1} risk={r2} riskier.positions={r3} empty_path={r4}"
    # catalogue predicts riskier.positions -> True (the defect)
    ok = (r0, r1, r2, r3, r4) == (True, True, True, True, True)
    log("CON-021", "PASS" if ok else "FAIL", obs)

def con022():
    p0 = ReadPolicy()
    r0 = p0.permits_now(3)
    p1 = ReadPolicy(permitted_hours=(0, 1, 2))
    r1 = p1.permits_now(2)
    r2 = p1.permits_now(3)
    r3 = p1.permits_now(24)
    r4 = p1.permits_now(-1)
    obs = f"no_policy={r0} in_range={r1} out_range={r2} hour24={r3} hour_neg1={r4}"
    ok = (r0, r1, r2, r3, r4) == (True, True, False, False, False)
    log("CON-022", "PASS" if ok else "FAIL", obs)

def con023():
    m = Connector.describe_manifest(key="x", display_name="X")
    ok = m.verification == "code_complete" and "CODE COMPLETE" in m.description and "no live source has answered it" in m.description
    log("CON-023", "PASS" if ok else "FAIL", f"verification={m.verification} description={m.description!r}")

def con024():
    d = DiscoveredObject(path=())
    ok = d.qualified_name == "" and d.leaf == ""
    log("CON-024", "PASS" if ok else "FAIL", f"qualified_name={d.qualified_name!r} leaf={d.leaf!r}")

async def main():
    con008(); await con007()
    con009()
    await con010()
    con011(); con012(); con013()
    con015(); con016(); con017(); con018(); con019(); con020(); con021(); con022(); con023(); con024()
    await con002(); await con003(); await con004(); await con005(); await con006()

asyncio.run(main())
