import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.integrate.controller import Controller, MemoryCluster, ClusterError
from prama.integrate.operator import Verb

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

def resource(name, tenant, datasets, generation=1, deleting=False):
    meta = {"name": name, "generation": generation}
    if deleting:
        meta["deletionTimestamp"] = "2026-01-01T00:00:00Z"
    return {"metadata": meta, "spec": {"tenant": tenant, "datasets": datasets}}

@block("INT-036")
def _():
    cluster = MemoryCluster()
    datasets = [{"name": f"d{i}", "description": "x"} for i in range(6)]
    cluster.fail_on = {"d4"}
    res = resource("est1", "t1", datasets)
    ctrl = Controller(cluster, cluster)
    outcome = ctrl.reconcile(res)
    ok = outcome.applied==4 and outcome.failed_at=="d4" and not outcome.complete
    cond = cluster.statuses["est1"]["conditions"][0]
    ok2 = cond["reason"]=="WriteFailed"
    remaining_not_attempted = len([d for d in cluster.stored.get("t1",[]) ]) == 4
    R("INT-036", ok and ok2 and remaining_not_attempted, f"applied={outcome.applied} failed_at={outcome.failed_at} complete={outcome.complete} cond_reason={cond['reason']} stored_count={len(cluster.stored.get('t1',[]))}")

@block("INT-037")
def _():
    cluster = MemoryCluster()
    cluster.fail_on = {"d0"}
    res = resource("est1", "t1", [{"name":"d0","description":"x"}])
    ctrl = Controller(cluster, cluster)
    ctrl.reconcile(res)
    status = cluster.statuses.get("est1")
    ok = status is not None and "observedGeneration" in status and "applied" in status and "conflicts" in status and "orphaned" in status
    R("INT-037", ok, f"status={status}")

@block("INT-038")
def _():
    cluster = MemoryCluster()
    res = resource("est1", "t1", [{"name":"d0","description":"x"}], generation=7)
    ctrl = Controller(cluster, cluster)
    ctrl.reconcile(res)
    ok = cluster.statuses["est1"]["observedGeneration"]==7
    R("INT-038", ok, f"observedGeneration={cluster.statuses['est1']['observedGeneration']}")

@block("INT-039")
def _():
    cluster = MemoryCluster()
    res = resource("est1", "t1", [{"name":"d0","description":"x"}], deleting=True)
    ctrl = Controller(cluster, cluster)
    outcome = ctrl.reconcile(res)
    ok = outcome.skipped and "est1" not in cluster.statuses and cluster.status_writes==0
    R("INT-039", ok, f"skipped={outcome.skipped!r} status_writes={cluster.status_writes}")

@block("INT-040")
def _():
    cluster = MemoryCluster()
    res = {"metadata":{"name":"est1","generation":1}, "spec":{"datasets":[]}}  # no tenant
    ctrl = Controller(cluster, cluster)
    outcome = ctrl.reconcile(res)
    ok = outcome.skipped and "est1" in cluster.statuses
    R("INT-040", ok, f"skipped={outcome.skipped!r} status_written={'est1' in cluster.statuses}")

@block("INT-041")
def _():
    cluster = MemoryCluster()
    class FailingStatusCluster(MemoryCluster):
        def write_status(self, name, status):
            if name == "est1":
                raise RuntimeError("status write failed")
            super().write_status(name, status)
    cluster2 = FailingStatusCluster(resources=[
        resource("est1","t1",[{"name":"d0","description":"x"}]),
        resource("est2","t1",[{"name":"d1","description":"x"}]),
        resource("est3","t1",[{"name":"d2","description":"x"}]),
    ])
    ctrl = Controller(cluster2, cluster2)
    try:
        outcomes = ctrl.reconcile_all()
        ok = len(outcomes)==3
        R("INT-041", ok, f"reconcile_all completed, {len(outcomes)} outcomes: {[o.name for o in outcomes]}")
    except Exception as e:
        R("INT-041", False, f"reconcile_all ABORTED after first failure: {type(e).__name__}: {e}; est2/est3 never reconciled")

@block("INT-042")
def _():
    cluster = MemoryCluster()
    res = resource("est1", "t1", [{"name":"d0","description":"x","approved":True,"controlState":"passed","suppressed":True}])
    ctrl = Controller(cluster, cluster)
    ctrl.reconcile(res)
    stored = cluster.stored["t1"][0]
    ok = stored.get("approved") is True and stored.get("controlState")=="passed" and stored.get("suppressed") is True
    R("INT-042", not ok, f"stored_declaration={stored} -- the extra keys (approved/controlState/suppressed) pass straight through _payload with no filtering; the claim that 'nothing here can approve or activate' rests entirely on what the DeclarationStore's apply() accepts downstream, not on anything in this module")

@block("INT-043")
def _():
    cluster = MemoryCluster()
    res = resource("est1", "t1", [{"name":"d0","description":"x"},{"name":"d1","description":"y"}])
    ctrl = Controller(cluster, cluster)
    o1 = ctrl.reconcile(res)
    o2 = ctrl.reconcile(res)
    ok = o1.applied==2 and o2.applied==0
    cond2 = cluster.statuses["est1"]["conditions"][0]
    ok2 = cond2["status"]=="True"
    R("INT-043", ok and ok2, f"first_applied={o1.applied} second_applied={o2.applied} second_ready={cond2}")

print("=== INT controller 036-043 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
