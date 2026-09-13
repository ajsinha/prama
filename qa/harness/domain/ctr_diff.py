import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.contract.diff import compare, compare_schema, Diff, DETAIL_LIMIT

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

@block("CTR-041")
def _():
    left = [{'id':1,'name':'a'}]
    right = [{'id':1,'nom':'a'}]
    d = compare(left,right,key=['id'])
    desc = d.describe()
    ok = 'schema differs' in desc and desc.index('schema differs') < desc.index('changed') if 'changed' in desc else True
    R("CTR-041", ok, f"{desc}")

@block("CTR-042")
def _():
    left=[{'id':1,'amt':100}]
    right=[{'id':1,'amt':200}]
    d = compare(left,right,key=['id'])
    rc = d.changed_examples[0]
    ok = rc.changes[0].column=='amt' and rc.changes[0].before==100 and rc.changes[0].after==200
    R("CTR-042", ok, f"{rc.render()}")

@block("CTR-043")
def _():
    left = []
    right = []
    for i in range(100):
        left.append({'id':i,'settlement_date':'2026-01-01','notional':1000})
        right.append({'id':i,'settlement_date':'2026-01-02','notional':1000})
    for i in range(100,10000):
        left.append({'id':i,'settlement_date':'2026-01-01','notional':1000})
        right.append({'id':i,'settlement_date':'2026-01-01','notional':2000})
    d = compare(left,right,key=['id'], limit=100)
    ok = d.columns_that_changed[0]=='notional'
    R("CTR-043", ok, f"columns_that_changed={d.columns_that_changed} changed_by_column={d.changed_by_column}")

@block("CTR-044")
def _():
    left100=[{'id':i,'v':1} for i in range(100)]
    right100=[{'id':i,'v':2} for i in range(100)]
    d100 = compare(left100,right100,key=['id'],limit=100)
    left101=[{'id':i,'v':1} for i in range(101)]
    right101=[{'id':i,'v':2} for i in range(101)]
    d101 = compare(left101,right101,key=['id'],limit=100)
    left_add=[{'id':i} for i in range(1)]
    right_add=[{'id':i} for i in range(102)]
    d_add = compare(left_add,right_add,key=['id'],limit=100)
    ok = not d100.truncated and d101.truncated and d_add.truncated
    R("CTR-044", ok, f"100={d100.truncated} 101={d101.truncated} added101={d_add.truncated}")

@block("CTR-045")
def _():
    left=[{'id':1},{'id':2}]
    right=[{'id':2},{'id':1}]
    d = compare(left,right)
    ok = not d.comparable and d.changed==0 and 'nothing says which row is which' in d.describe()
    R("CTR-045", ok, f"comparable={d.comparable} changed={d.changed} describe={d.describe()}")

@block("CTR-046")
def _():
    import random
    rows = [{'id':i,'v':i*2} for i in range(100)]
    shuffled = list(rows)
    random.shuffle(shuffled)
    d = compare(rows, shuffled)
    ok = d.added==0 and d.removed==0 and d.unchanged==100
    R("CTR-046", ok, f"added={d.added} removed={d.removed} unchanged={d.unchanged}")

@block("CTR-047")
def _():
    left=[{'id':1,'tags':['a','b']}]
    right=[{'id':1,'tags':['a','c']}]
    try:
        d = compare(left,right)
        R("CTR-047", False, f"no exception, result={d}")
    except TypeError as e:
        R("CTR-047", False, f"bare TypeError leaked: {e}")
    except Exception as e:
        R("CTR-047", True, f"{type(e).__name__}: {e}")

@block("CTR-048")
def _():
    left=[{'id':1,'v':'x'}]*3
    right=[{'id':1,'v':'x'}]
    d = compare(left,right)
    ok = d.added==0 and d.removed==0 and d.unchanged==1
    dup_visible = ok  # nothing distinguishes 3-vs-1 in this output
    R("CTR-048", not ok or False, f"added={d.added} removed={d.removed} unchanged={d.unchanged} (3 left rows collapse to 1 in the set, no indication a 2-row loss occurred)")

@block("CTR-049")
def _():
    left=[{'id':1,'v':'a'},{'id':1,'v':'b'}]
    right=[{'id':1,'v':'a'}]
    d = compare(left,right,key=['id'])
    ok = d.duplicate_keys_left==1 and 'wrong pairs' in d.describe()
    R("CTR-049", ok, f"duplicate_keys_left={d.duplicate_keys_left} describe={d.describe()}")

@block("CTR-050")
def _():
    left=[{'x':1}]
    right=[{'x':1}]
    d = compare(left,right,key=['id'])
    ok_refused = False  # check what actually happens
    all_collapse = d.duplicate_keys_left == 0  # since only 1 row, no dup
    R("CTR-050", None, f"duplicate_keys_left={d.duplicate_keys_left} added={d.added} removed={d.removed} changed={d.changed} describe={d.describe()} -- no refusal naming missing column 'id'")

@block("CTR-051")
def _():
    left=[{'id':1,'a':1}]
    right=[{'id':1,'a':1,'b':2}]
    d = compare(left,right,key=['id'])
    ok = d.schema.added==('b',) and d.changed==0
    R("CTR-051", ok, f"schema_added={d.schema.added} changed={d.changed} changed_examples={d.changed_examples}")

@block("CTR-052")
def _():
    left=[{'id':1,'v':1,'loaded_at':'t1'}]
    right=[{'id':1,'v':1,'loaded_at':'t2'}]
    d_keyed = compare(left,right,key=['id'],ignore=['loaded_at'])
    d_keyless = compare(left,right,ignore=['loaded_at'])
    ok = d_keyed.changed==0 and d_keyless.added==0 and d_keyless.removed==0
    R("CTR-052", ok, f"keyed_changed={d_keyed.changed} keyless_added={d_keyless.added} keyless_removed={d_keyless.removed}")

@block("CTR-053")
def _():
    left = {'a':'text','b':''}
    right = {'a':'','b':'number'}
    sd = compare_schema(left, right)
    ok = sd.retyped==()
    R("CTR-053", ok, f"retyped={sd.retyped}")

@block("CTR-054")
def _():
    left=[{'id':1,'v':1},{'id':'x','v':2},{'id':None,'v':3}]
    right=[{'id':1,'v':10},{'id':'x','v':20}]
    try:
        d = compare(left,right,key=['id'])
        R("CTR-054", True, f"no exception; describe={d.describe()}")
    except TypeError as e:
        R("CTR-054", False, f"TypeError: {e}")

print("=== CTR diff 041-054 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
