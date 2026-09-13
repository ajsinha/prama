import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.integrate.operator import plan, Verb, Plan, MANAGED_BY

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

@block("INT-026")
def _():
    spec = {"tenant":"t1","datasets":[]}
    stored = [{"name":"orphan1","description":"x"}]
    p = plan(spec, stored)
    ok = len(p.steps)==1 and p.steps[0].verb==Verb.ORPHANED
    no_delete = 'delet' not in ' '.join(s.why for s in p.steps).lower() or 'never' in ' '.join(s.why for s in p.steps).lower() or True
    contains_delete_verb = any(s.verb.value=='delete' for s in p.steps)
    R("INT-026", ok and not contains_delete_verb, f"{p.steps}")

@block("INT-027")
def _():
    spec = {"tenant":"t1","datasets":[{"name":"orders","description":"new desc"}]}
    stored = [{"name":"orders","description":"old desc"}]  # no managedBy
    p = plan(spec, stored)
    ok = len(p.steps)==1 and p.steps[0].verb==Verb.CONFLICT and 'description' in p.steps[0].differing
    R("INT-027", ok, f"{p.steps}")

@block("INT-028")
def _():
    spec = {"tenant":"t1","datasets":[{"name":"orders","description":"new desc"}]}
    stored = [{"name":"orders","description":"old desc","managedBy":MANAGED_BY}]
    p = plan(spec, stored)
    ok = len(p.steps)==1 and p.steps[0].verb==Verb.AMEND and 'description' in p.steps[0].differing
    R("INT-028", ok, f"{p.steps}")

@block("INT-029")
def _():
    spec = {"tenant":"t1","datasets":[{"name":"orders","description":"x"}]}
    stored = [{"name":"orders","description":"x","owner":"alice","rhythm":"daily"}]
    p = plan(spec, stored)
    ok = len(p.steps)==1 and p.steps[0].verb==Verb.UNCHANGED
    R("INT-029", ok, f"{p.steps}")

@block("INT-030")
def _():
    spec1 = {"tenant":"t1","datasets":[{"name":"orders","grain":["a","b"]}]}
    stored1 = [{"name":"orders","grain":("a","b"),"managedBy":MANAGED_BY}]
    p1 = plan(spec1, stored1)
    spec2 = {"tenant":"t1","datasets":[{"name":"orders","grain":["a","b"]}]}
    stored2 = [{"name":"orders","grain":["b","a"],"managedBy":MANAGED_BY}]
    p2 = plan(spec2, stored2)
    ok = p1.steps[0].verb==Verb.UNCHANGED and p2.steps[0].verb==Verb.AMEND
    R("INT-030", ok, f"list_vs_tuple={p1.steps[0].verb}; reordered={p2.steps[0].verb}")

@block("INT-031")
def _():
    spec = {"tenant":"t1","datasets":[{"description":"x"}]}
    stored = []
    p = plan(spec, stored)
    ok_flags_problem = p.steps[0].dataset != '' or (p.steps[0].dataset=='' and p.steps[0].verb!=Verb.CREATE)
    R("INT-031", ok_flags_problem, f"steps={p.steps} -- a manifest entry with no name plans CREATE for dataset ''")

@block("INT-032")
def _():
    spec = {"tenant":"t1","datasets":[{"name":"orders","description":"new"}]}
    stored = [{"name":"orders","description":"old"}]
    p = plan(spec, stored)
    conds = p.conditions(generation=3, applied=len(p.writes))
    ready_cond = conds[0]
    ok = ready_cond['status']=='False' and ready_cond['reason']=='NeedsDecision'
    R("INT-032", ok, f"{ready_cond}")

@block("INT-033")
def _():
    spec = {"tenant":"t1","datasets":[{"name":"a","description":"x"},{"name":"b","description":"y"}]}
    stored = []
    p = plan(spec, stored)
    c_none = p.conditions(generation=1, applied=None)
    c_2 = p.conditions(generation=1, applied=2)
    ok = c_none[0]['reason']=='NotApplied' and c_none[0]['status']=='False' and c_2[0]['reason']=='Reconciled' and c_2[0]['status']=='True'
    R("INT-033", ok, f"none={c_none[0]} applied2={c_2[0]}")

@block("INT-034")
def _():
    spec = {"tenant":"t1","datasets":[{"name":f"d{i}","description":"x"} for i in range(40)]}
    stored = []
    p = plan(spec, stored)
    conds = p.conditions(generation=1, applied=12)
    ok = conds[0]['reason']=='PartiallyApplied' and conds[0]['status']=='False' and '12 of 40' in conds[0]['message']
    R("INT-034", ok, f"{conds[0]}")

@block("INT-035")
def _():
    spec = {"tenant":"t1","datasets":[{"name":"c1","description":"x"},{"name":"c2","description":"x"}]}
    stored = [{"name":"c1","description":"old"},{"name":"c2","description":"old"}]
    for i in range(18):
        spec["datasets"].append({"name":f"u{i}"})
        stored.append({"name":f"u{i}"})
    for i in range(3):
        spec2name = f"o{i}"
        stored.append({"name":spec2name})
    p = plan(spec, stored)
    d = p.describe()
    ok = d.index('conflict') < d.index('unchanged')
    named = 'c1' in d and 'c2' in d
    R("INT-035", ok and named, f"{d}")

print("=== INT operator 026-035 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
