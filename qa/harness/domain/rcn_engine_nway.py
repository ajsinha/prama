import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from datetime import date
from decimal import Decimal
from prama.recon.engine import Reconciliation, Definition, Side
from prama.recon.match import MatchKey
from prama.recon.normalise import AmountSpec, RateSource
from prama.recon.classify import BreakKind
from prama.semantic.relationships import Tolerance
from prama.recon.nway import reconcile_n_way, RollForward, check_roll_forward, opening_from, SidePosition

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

D0 = date(2026,3,2)

def basic_defn(**kw):
    return Definition(name="t", left=Side(name="L", amount_column="amt", spec=AmountSpec(currency_column='ccy')),
                       right=Side(name="R", amount_column="amt", spec=AmountSpec(currency_column='ccy')),
                       key=MatchKey(left=('k',),right=('k',)), tolerance=Tolerance(absolute=0.01), target_currency='USD', **kw)

@block("RCN-092")
def _():
    rs = RateSource()
    rs.add('EUR','USD', D0, '1.1')
    defn = basic_defn()
    recon = Reconciliation(defn, rates=rs)
    run = recon.run([{'k':1,'amt':100,'ccy':'EUR'}],[{'k':1,'amt':110,'ccy':'USD'}], business_date=D0)
    ok = len(run.rates_used)>=1
    R("RCN-092", ok, f"rates_used={run.rates_used}")

@block("RCN-093")
def _():
    rs = RateSource(); rs.add('EUR','USD',D0,'1.1')
    defn = basic_defn()
    left = [{'k':i,'amt':100,'ccy':'EUR'} for i in range(50)]
    right = [{'k':i,'amt':110,'ccy':'USD'} for i in range(48)]
    recon = Reconciliation(defn, rates=rs)
    run1 = recon.run(left,right, business_date=D0)
    run2 = recon.run(left,right, business_date=D0)
    ok = run1.to_dict()==run2.to_dict()
    R("RCN-093", ok, f"identical={ok}")

@block("RCN-094")
def _():
    rs = RateSource(); rs.add('EUR','USD',D0,'1.1'); rs.add('GBP','USD',D0,'1.3')
    defn = basic_defn()
    left = [{'k':1,'amt':100,'ccy':'EUR'},{'k':1,'amt':100,'ccy':'GBP'}]
    right = [{'k':1,'amt':240,'ccy':'USD'}]
    recon = Reconciliation(defn, rates=rs)
    run = recon.run(left,right,business_date=D0)
    b = run.population.breaks[0] if run.population.breaks else None
    expected_total = Decimal('100')*Decimal('1.1') + Decimal('100')*Decimal('1.3')
    ok = b is None or (b.left==expected_total)
    R("RCN-094", ok, f"break={b} expected_left_total={expected_total}")

@block("RCN-095")
def _():
    defn = basic_defn()
    recon = Reconciliation(defn)
    left = [{'k':1,'amt':100,'ccy':'USD'}]
    right = [{'k':1,'amt':100,'ccy':'USD'},{'k':1,'ccy':'USD'}]  # second row has no amt
    run = recon.run(left,right,business_date=D0)
    b = run.population.breaks[0] if run.population.breaks else None
    ok = b is not None and b.right is None and b.kind==BreakKind.GENUINE
    R("RCN-095", ok, f"break={b}")

@block("RCN-096")
def _():
    defn = Definition(name="t", left=Side(name="L", amount_column="amt", spec=AmountSpec(currency_column='ccy')),
                       right=Side(name="R", amount_column="amt", spec=AmountSpec(currency='USD')),
                       key=MatchKey(left=('k',),right=('k',)), tolerance=Tolerance(absolute=0.01), target_currency='')
    rs = RateSource(); rs.add('EUR','USD',D0,'1.1')
    recon = Reconciliation(defn, rates=rs)
    run = recon.run([{'k':1,'amt':100,'ccy':'EUR'}],[{'k':1,'amt':110}],business_date=D0)
    ok = run.completed
    R("RCN-096", ok, f"completed={run.completed} refusal={run.refusal} breaks={run.population.breaks}")

@block("RCN-097")
def _():
    defn0 = basic_defn(date_window=0)
    defn1 = basic_defn(date_window=1)
    left=[{'k':1,'d':'2026-03-02','amt':100,'ccy':'USD'}]
    right=[{'k':1,'d':'2026-03-03','amt':100,'ccy':'USD'}]
    key01 = MatchKey(left=('k','d'),right=('k','d'))
    defn0b = Definition(name="t0", left=defn0.left, right=defn0.right, key=key01, tolerance=defn0.tolerance, target_currency='USD', date_window=0)
    defn1b = Definition(name="t1", left=defn1.left, right=defn1.right, key=key01, tolerance=defn1.tolerance, target_currency='USD', date_window=1)
    run0 = Reconciliation(defn0b).run(left,right,business_date=D0)
    run1 = Reconciliation(defn1b).run(left,right,business_date=D0)
    ok = len(run0.population.breaks)==2 and len(run1.population.breaks)==0
    R("RCN-097", ok, f"window0_breaks={len(run0.population.breaks)} window1_breaks={len(run1.population.breaks)} window1_pairs={len(run1.match.pairs)}")

@block("RCN-098")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'FO':{'K1':Decimal('100')}, 'SL':{'K1':Decimal('105')}, 'GL':{'K1':Decimal('100')}}
    res = reconcile_n_way(sides, tol)
    d = res.disagreements[0] if res.disagreements else None
    ok = d is not None and d.odd_side=='SL' and d.consensus==Decimal('100')
    R("RCN-098", ok, f"disagreement={d}")

@block("RCN-099")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'A':{'K1':Decimal('100')},'B':{'K1':Decimal('200')},'C':{'K1':Decimal('300')}}
    res = reconcile_n_way(sides, tol)
    d = res.disagreements[0]
    ok = d.odd_side=='' and d.consensus is None and d.all_disagree
    R("RCN-099", ok, f"{d}; describe={d.describe()}")

@block("RCN-100")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'A':{'K1':Decimal('100')},'B':{'K1':Decimal('100')},'C':{'K1':Decimal('200')},'D':{'K1':Decimal('200')}}
    res = reconcile_n_way(sides, tol)
    d = res.disagreements[0]
    ok = d.all_disagree and d.odd_side==''
    R("RCN-100", ok, f"{d}")

@block("RCN-101")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'A':{'K1':Decimal('100')},'B':{'K1':Decimal('200')}}
    res = reconcile_n_way(sides, tol)
    d = res.disagreements[0] if res.disagreements else None
    ok = d is not None and d.odd_side=='' and 'majority' in d.describe().lower()
    R("RCN-101", ok, f"{d}; describe={d.describe() if d else None} (docstring says 'three or more'; two sides given, no guard)")

@block("RCN-102")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'A':{f'K{i}':Decimal('100') for i in range(4000)}}
    res = reconcile_n_way(sides, tol)
    ok = len(res.disagreements)>0
    R("RCN-102", not ok, f"disagreements={len(res.disagreements)} summary={res.describe()} (single side is vacuously self-agreeing everywhere; Expected a refusal)")

@block("RCN-103")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'A':{'K1':Decimal('100')},'B':{},'C':{'K1':Decimal('100')}}
    res = reconcile_n_way(sides, tol)
    d = res.disagreements[0]
    ok = d.missing_from==('B',) and 'missing from' in d.describe()
    R("RCN-103", ok, f"{d.describe()}")

@block("RCN-104")
def _():
    tol = Tolerance(absolute=0.01)
    sides = {'A':{'K1':Decimal('100')},'B':{},'C':{'K1':Decimal('200')}}
    res = reconcile_n_way(sides, tol)
    d = res.disagreements[0]
    desc = d.describe()
    both_facts = 'missing' in desc and ('200' in desc or 'disagree' in desc)
    R("RCN-104", both_facts, f"{desc} (missing_from={d.missing_from}, but value disagreement between A and C never computed since continue skips it)")

@block("RCN-105")
def _():
    tol = Tolerance(absolute=0.01)
    a = {}; b = {}; c = {}
    for i in range(500):
        if i < 400:
            a[f'K{i}'] = Decimal('999')   # A is odd
            b[f'K{i}'] = Decimal('100')
            c[f'K{i}'] = Decimal('100')
        else:
            a[f'K{i}'] = Decimal('100')
            b[f'K{i}'] = Decimal('100')
            c[f'K{i}'] = Decimal('100')
    sides = {'A':a, 'B':b, 'C':c}
    res = reconcile_n_way(sides, tol)
    odd = res.by_odd_side
    desc = res.describe()
    ok = odd.get('A')==400 and 'points at that system' in desc
    R("RCN-105", ok, f"by_odd_side={odd} describe={desc}")

@block("RCN-106")
def _():
    tol = Tolerance(absolute=0.01)
    a={}; b={}; c={}
    for i in range(200):
        a[f'K{i}']=Decimal('100'); b[f'K{i}']=Decimal('200'); c[f'K{i}']=Decimal('100')
    for i in range(200,400):
        a[f'K{i}']=Decimal('100'); b[f'K{i}']=Decimal('100'); c[f'K{i}']=Decimal('200')
    sides = {'A':a,'B':b,'C':c}
    res1 = reconcile_n_way(sides, tol)
    res2 = reconcile_n_way(sides, tol)
    d1 = res1.describe(); d2 = res2.describe()
    R("RCN-106", d1==d2, f"run1={d1[-60:]} run2={d2[-60:]}")

@block("RCN-107")
def _():
    tol = Tolerance(absolute=0.01)
    e = RollForward(key='K1', opening=Decimal('1000'), movements=Decimal('50'), closing=Decimal('1100'))
    out = check_roll_forward([e], tol)
    ok = len(out)==1 and out[0].kind==BreakKind.GENUINE and 'restat' in out[0].because
    R("RCN-107", ok, f"{out}")

@block("RCN-108")
def _():
    tol = Tolerance(absolute=0.01)
    e = RollForward(key='K1', opening=Decimal('1000'), movements=Decimal('100'), closing=Decimal('1100'))
    out = check_roll_forward([e], tol)
    ok = len(out)==0
    R("RCN-108", ok, f"{out}")

@block("RCN-109")
def _():
    tol = Tolerance(relative=0.001)
    e = RollForward(key='K1', opening=Decimal('-50'), movements=Decimal('50'), closing=Decimal('5'))
    out = check_roll_forward([e], tol)
    ok = len(out)==1
    R("RCN-109", ok, f"out={out} (expected 0.1% tolerance meaningfully applied; expected=0, magnitude substituted to 1 when expected==0, so allowance=0.001 not 0.001*something-meaningful)")

@block("RCN-110")
def _():
    # Yesterday's real closing was 1000. Today the source system RESTATED its own
    # opening to 1050 (self-consistent with a restated closing of 1100 and a 50
    # movement) -- masking the restatement. Carrying forward yesterday's real
    # closing (1000) as today's opening should instead reveal the break.
    e_from_source = RollForward(key='K1', opening=Decimal('1050'), movements=Decimal('50'), closing=Decimal('1100'))
    out_source = check_roll_forward([e_from_source], Tolerance(absolute=0.01))
    prev_closing = {'K1': Decimal('1000')}
    opening = opening_from(prev_closing)
    e_carried = RollForward(key='K1', opening=opening['K1'], movements=Decimal('50'), closing=Decimal('1100'))
    out_carried = check_roll_forward([e_carried], Tolerance(absolute=0.01))
    ok = len(out_source)==0 and len(out_carried)==1
    R("RCN-110", ok, f"source's-own-opening: breaks={len(out_source)} (Expected 0, passes over the restatement); opening_from(previous_closing): breaks={len(out_carried)} (Expected 1, catches it) -- {out_carried}")

print("=== RCN engine/nway 092-110 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
