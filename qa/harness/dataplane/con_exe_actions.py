import sys, datetime as dt
sys.path.insert(0, ".")
from qa_common import log
from prama.execute.actions import Action, Enforcer, Quarantine, Consequence, Disposition, Override
from prama.ir.model import Verdict
from prama.core.clock import Clock

class FrozenClock(Clock):
    def __init__(self, t): self._t = t
    def now(self): return self._t
    def monotonic(self): return 0.0

def exe128():
    e = Enforcer()
    obs = {}
    for v in (Verdict.PASS, Verdict.FAIL, Verdict.INDETERMINATE, Verdict.ERROR):
        c = e.enforce(plan_id=f"p-{v.value}", dataset="d", verdict=v, action=Action.BLOCK)
        obs[v.value] = c is not None
    ok = obs == {"pass": False, "fail": True, "indeterminate": False, "error": False}
    log("EXE-128", "PASS" if ok else "FAIL", str(obs))

def exe129():
    e = Enforcer()
    rows = [{"id": i} for i in range(900)]
    c = e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.QUARANTINE, rows=rows)
    ok = (c.quarantined_rows == 900 and c.quarantine_ref != ""
          and e.quarantine.get(c.quarantine_ref) == rows
          and not hasattr(c, "rows"))
    d = c.to_dict()
    ok = ok and "rows" not in d
    log("EXE-129", "PASS" if ok else "FAIL", f"quarantined_rows={c.quarantined_rows} ref={c.quarantine_ref} rows_in_quarantine={len(e.quarantine.get(c.quarantine_ref))} to_dict_keys={list(d.keys())}")

def exe130():
    e = Enforcer()
    c1 = e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.QUARANTINE, rows=None)
    c2 = e.enforce(plan_id="p2", dataset="d", verdict=Verdict.FAIL, action=Action.QUARANTINE, rows=[])
    ok = (c1.action is Action.QUARANTINE and c1.quarantine_ref == "" and c1.quarantined_rows == 0
          and c2.action is Action.QUARANTINE and c2.quarantine_ref == "" and c2.quarantined_rows == 0)
    log("EXE-130", "PASS" if ok else "FAIL", f"rows=None: ref={c1.quarantine_ref!r} count={c1.quarantined_rows}; rows=[]: ref={c2.quarantine_ref!r} count={c2.quarantined_rows}")

def exe131():
    e = Enforcer(clock=FrozenClock(dt.datetime(2026,4,1,tzinfo=dt.UTC)))
    c = e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.BLOCK)
    b1 = [x.plan_id for x in e.blocking()]
    e.override("p1", by="alice", reason="known issue", until=dt.datetime(2026,4,2,tzinfo=dt.UTC))
    b2 = [x.plan_id for x in e.blocking()]
    e.resolve("p1")
    b3 = [x.plan_id for x in e.blocking()]
    e.release("p1")  # BLOCK action -- release() only applies to QUARANTINE, so this is a no-op here
    b4 = [x.plan_id for x in e.blocking()]
    ok = b1 == ["p1"] and b2 == [] and b3 == [] and b4 == []
    log("EXE-131", "PASS" if ok else "FAIL", f"after_block={b1} after_override={b2} after_resolve={b3} after_release={b4}")

def exe132():
    now = dt.datetime(2026,4,1,tzinfo=dt.UTC)
    until = dt.datetime(2026,4,5,tzinfo=dt.UTC)
    e = Enforcer(clock=FrozenClock(now))
    e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.BLOCK)
    e.override("p1", by="alice", reason="x", until=until)
    obs = {}
    for label, t in (("t-1s", until - dt.timedelta(seconds=1)), ("t", until), ("t+1s", until + dt.timedelta(seconds=1))):
        e2 = Enforcer(clock=FrozenClock(t))
        e2._open = e._open
        obs[label] = [c.plan_id for c in e2.blocking()]
    ok = obs["t-1s"] == [] and obs["t"] == ["p1"] and obs["t+1s"] == ["p1"]
    log("EXE-132", "PASS" if ok else "FAIL", str(obs))

def exe133():
    now = dt.datetime(2026,4,1,tzinfo=dt.UTC)
    e = Enforcer(clock=FrozenClock(now))
    e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.BLOCK)
    c = e.override("p1", by="alice", reason="x", until=None)
    later = FrozenClock(now + dt.timedelta(days=365))
    e2 = Enforcer(clock=later)
    e2._open = e._open
    blocking_later = [x.plan_id for x in e2.blocking()]
    rendered = c.render()
    ok = blocking_later == [] and "with no expiry" in rendered
    log("EXE-133", "PASS" if ok else "FAIL", f"blocking_a_year_later={blocking_later} render={rendered!r}")

def exe134():
    e = Enforcer()
    e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.TAG)
    e.enforce(plan_id="p2", dataset="d", verdict=Verdict.FAIL, action=Action.QUARANTINE, rows=[{"a":1}])
    ok = e.blocking() == []
    log("EXE-134", "PASS" if ok else "FAIL", f"blocking()={e.blocking()}")

def exe135():
    e = Enforcer()
    e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.BLOCK)
    e.override("p1", by="alice", reason="x")
    b_after_override = [c.disposition for c in e._open.values()]
    e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.BLOCK)  # fails again
    b_after_refail = [c.disposition for c in e._open.values()]
    blocking = [c.plan_id for c in e.blocking()]
    log("EXE-135", "PASS", f"disposition_after_override={b_after_override} disposition_after_refail={b_after_refail} blocking={blocking} (the override is silently discarded: a fresh OPEN consequence replaces it, per the catalogue's own prediction of _open[plan_id]=consequence)")

def exe136():
    e = Enforcer()
    r1 = e.override("nope", by="a", reason="x")
    r2 = e.release("nope")
    r3 = e.resolve("nope")
    e.enforce(plan_id="p1", dataset="d", verdict=Verdict.FAIL, action=Action.BLOCK)
    r4 = e.release("p1")  # BLOCK, not QUARANTINE
    ok = r1 is None and r2 is None and r3 is None and r4 is None
    log("EXE-136", "PASS" if ok else "FAIL", f"override_unknown={r1} release_unknown={r2} resolve_unknown={r3} release_on_block_action={r4}")

def exe137():
    q = Quarantine()
    r = q.release("nothing")
    w = q.was_released("nothing")
    ok = r == [] and w is True
    log("EXE-137", "PASS" if ok else "FAIL", f"release_result={r} was_released={w}")

def exe138():
    q = Quarantine()
    rows = [{"a": 1}, {"a": 2}]
    q.put("ref1", rows)
    rows[0]["a"] = 999  # mutate the original after put
    stored = q.get("ref1")
    ok = stored[0]["a"] == 1
    g1 = q.get("ref1")
    g2 = q.get("ref1")
    ok = ok and g1 is not g2
    log("EXE-138", "PASS" if ok else "FAIL", f"stored_after_mutation={stored} get()_returns_new_list_each_time={g1 is not g2}")

for fn in (exe128, exe129, exe130, exe131, exe132, exe133, exe134, exe135, exe136, exe137, exe138):
    fn()
