import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from datetime import date
from decimal import Decimal
from prama.recon.normalise import RateSource, Unavailable, AmountNormaliser, AmountSpec, CodeNormaliser, Applied
from prama.core.errors import ValidationError

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

@block("RCN-026")
def _():
    rs = RateSource(source="vendorX")
    rs.add('EUR','USD', date(2026,3,2), '1.10')
    n = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='USD', rates=rs)
    result = n.normalise({'amt':'100'}, 'amt', date(2026,3,2))
    ok = result.value==Decimal('110.00') and any('vendorX' in d for _,d in result.steps) and any('2026-03-02' in d for _,d in result.steps)
    R("RCN-026", ok, f"value={result.value} steps={result.steps}")

@block("RCN-027")
def _():
    rs = RateSource()
    n = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='USD', rates=rs)
    try:
        n.normalise({'amt':'100'},'amt',date(2026,3,2))
        R("RCN-027", False, "no Unavailable raised")
    except Unavailable as e:
        ok = 'EUR' in str(e) and 'USD' in str(e) and '2026-03-02' in str(e)
        R("RCN-027", ok, f"{e}")

@block("RCN-028")
def _():
    from prama.recon.engine import Reconciliation, Definition, Side
    from prama.recon.match import MatchKey
    from prama.semantic.relationships import Tolerance
    rs = RateSource()
    for i in range(99):
        rs.add('EUR','USD', date(2026,3,2), '1.1')
    left_rows = [{'k':i,'amt':100,'ccy':'EUR'} for i in range(100)]
    right_rows = [{'k':i,'amt':110,'ccy':'EUR' if i<99 else 'GBP'} for i in range(100)]
    defn = Definition(name="t", left=Side(name="L", amount_column="amt", spec=AmountSpec(currency_column='ccy')),
                       right=Side(name="R", amount_column="amt", spec=AmountSpec(currency_column='ccy')),
                       key=MatchKey(left=('k',),right=('k',)), tolerance=Tolerance(absolute=0.01), target_currency='USD')
    recon = Reconciliation(defn, rates=rs)
    run = recon.run(left_rows, right_rows, business_date=date(2026,3,2))
    ok = not run.completed and run.refusal and len(run.population)==0 and len(run.rates_used) < 100
    R("RCN-028", ok, f"completed={run.completed} refusal={run.refusal!r} population_len={len(run.population)} rates_used_count={len(run.rates_used)}")

@block("RCN-029")
def _():
    rs0 = RateSource(carry_forward_days=0)
    rs0.add('EUR','USD', date(2026,2,27), '1.1')
    n0 = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='USD', rates=rs0)
    try:
        n0.normalise({'amt':'100'},'amt', date(2026,3,2))
        r1 = "NOT refused"
    except Unavailable as e:
        r1 = f"refused: {e}"
    rs3 = RateSource(carry_forward_days=3)
    rs3.add('EUR','USD', date(2026,2,27), '1.1')
    n3 = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='USD', rates=rs3)
    try:
        result = n3.normalise({'amt':'100'},'amt', date(2026,3,2))
        rate_obj = rs3.get('EUR','USD', date(2026,3,2))
        carried_noted = 'carried forward from 2026-02-27' in rate_obj.source and rate_obj.as_of==date(2026,2,27)
        r2 = f"succeeded, value={result.value}, rate.source={rate_obj.source!r}, rate.as_of={rate_obj.as_of}, carried_noted={carried_noted}"
    except Unavailable as e:
        r2 = f"refused (unexpected): {e}"
    ok = 'refused' in r1 and 'succeeded' in r2 and 'carried_noted=True' in r2
    R("RCN-029", ok, f"cf=0: {r1}; cf=3: {r2}")

@block("RCN-030")
def _():
    rs = RateSource()
    rs.add('USD','EUR', date(2026,3,2), '0.90909091')
    n = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='USD', rates=rs)
    result = n.normalise({'amt':'100'},'amt', date(2026,3,2))
    inverted_mentioned = any('inverted' in d for _,d in result.steps)
    R("RCN-030", inverted_mentioned, f"steps={result.steps}")

@block("RCN-031")
def _():
    rs = RateSource()
    rs.add('USD','EUR', date(2026,3,2), '0')
    n = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='USD', rates=rs)
    try:
        n.normalise({'amt':'100'},'amt', date(2026,3,2))
        R("RCN-031", False, "no exception")
    except Unavailable as e:
        R("RCN-031", True, f"{e}")
    except ZeroDivisionError as e:
        R("RCN-031", False, f"ZeroDivisionError leaked: {e}")

@block("RCN-032")
def _():
    rs = RateSource()
    n = AmountNormaliser(AmountSpec(currency='EUR'), target_currency='EUR', rates=rs)
    result = n.normalise({'amt':'100'},'amt', date(2026,3,2))
    ok = result.value==Decimal('100') and (not result.steps or all('identity' not in d for _,d in result.steps))
    # actually check via rates.get directly
    rate = rs.get('EUR','EUR', date(2026,3,2))
    ok2 = rate.rate==1 and rate.source=='identity'
    R("RCN-032", ok2, f"rate={rate}")

@block("RCN-033")
def _():
    rs = RateSource()
    rs.add('eur','usd', date(2026,3,2), '1.1')
    n = AmountNormaliser(AmountSpec(currency_column='ccy'), target_currency='USD', rates=rs)
    result = n.normalise({'amt':'100','ccy':'eur'}, 'amt', date(2026,3,2))
    ok = result.value==Decimal('110.0')
    R("RCN-033", ok, f"value={result.value}")

@block("RCN-034")
def _():
    n = AmountNormaliser(AmountSpec(currency_column='ccy'), target_currency='')
    try:
        result = n.normalise({'amt':'100','ccy':'EUR'}, 'amt', date(2026,3,2))
        R("RCN-034", False, f"no refusal; result={result.value} steps={result.steps}")
    except Unavailable as e:
        named_at_config = 'target' in str(e).lower() and 'missing' in str(e).lower()
        R("RCN-034", named_at_config, f"refused: {e} (Expected: refusal naming the missing target currency; got a rate-table-shaped message instead if named_at_config is False)")

@block("RCN-035")
def _():
    n = AmountNormaliser(AmountSpec(), target_currency='USD')
    try:
        n.normalise({'amt':'1,234.56'}, 'amt', date(2026,3,2))
        R("RCN-035", False, "no exception")
    except ValidationError as e:
        ok = '1,234.56' in str(e)
        R("RCN-035", ok, f"{e}")

@block("RCN-036")
def _():
    n = AmountNormaliser(AmountSpec(), target_currency='USD')
    result = n.normalise({}, 'amt', date(2026,3,2))
    ok = result.value is None and not result.steps
    R("RCN-036", ok, f"value={result.value} steps={result.steps}")

@block("RCN-037")
def _():
    rs = RateSource()
    rs.add('EUR','USD', date(2026,3,2), '1.1')
    spec = AmountSpec(invert_sign=True, scale=Decimal(1000), currency='EUR', scale_places=2)
    n = AmountNormaliser(spec, target_currency='USD', rates=rs)
    result = n.normalise({'amt':'1.2345'}, 'amt', date(2026,3,2))
    applied_order = [a.value for a,_ in result.steps]
    ok = applied_order == ['sign','scale','currency','rounding']
    expected_val = (Decimal('1.2345')* -1 * 1000 * Decimal('1.1')).quantize(Decimal('0.01'))
    ok2 = result.value == expected_val
    R("RCN-037", ok and ok2, f"order={applied_order} value={result.value} expected={expected_val}")

@block("RCN-038")
def _():
    n = AmountNormaliser(AmountSpec(scale_places=2), target_currency='USD')
    r1 = n.normalise({'amt':'1.005'},'amt',date(2026,3,2)).value
    r2 = n.normalise({'amt':'1.015'},'amt',date(2026,3,2)).value
    r3 = n.normalise({'amt':'1.025'},'amt',date(2026,3,2)).value
    ok = r1==Decimal('1.00') and r2==Decimal('1.02') and r3==Decimal('1.02')
    R("RCN-038", ok, f"1.005->{r1} 1.015->{r2} 1.025->{r3}")

@block("RCN-039")
def _():
    n = AmountNormaliser(AmountSpec(scale=Decimal(1000)), target_currency='USD')
    result = n.normalise({'amt':'12.5'},'amt',date(2026,3,2))
    ok = result.value==Decimal('12500') and any('1000' in d for _,d in result.steps)
    R("RCN-039", ok, f"value={result.value} steps={result.steps}")

@block("RCN-040")
def _():
    n_none = AmountNormaliser(AmountSpec(scale_places=None), target_currency='USD')
    n_zero = AmountNormaliser(AmountSpec(scale_places=0), target_currency='USD')
    a1 = n_none.normalise({'amt':'1.4'},'amt',date(2026,3,2)).value
    a2 = n_none.normalise({'amt':'1.5'},'amt',date(2026,3,2)).value
    b1 = n_zero.normalise({'amt':'1.4'},'amt',date(2026,3,2)).value
    b2 = n_zero.normalise({'amt':'1.5'},'amt',date(2026,3,2)).value
    ok = a1==Decimal('1.4') and a2==Decimal('1.5') and b1==Decimal('1') and b2==Decimal('2')
    R("RCN-040", ok, f"None:1.4->{a1} 1.5->{a2}; 0:1.4->{b1} 1.5->{b2}")

@block("RCN-041")
def _():
    cn = CodeNormaliser({'GB':'UK'}, name='ctry')
    try:
        cn.normalise('XX')
        R("RCN-041", False, "no exception")
    except Unavailable as e:
        R("RCN-041", True, f"{e}")

@block("RCN-042")
def _():
    cn = CodeNormaliser({'GB':'UK'}, name='ctry')
    got = cn.covers({'GB','XX','ZZ'})
    ok = got == ('XX','ZZ')
    R("RCN-042", ok, f"covers={got}")

@block("RCN-043")
def _():
    cn = CodeNormaliser({'GB':'GB'})
    r1 = cn.normalise('GB')
    r2 = cn.normalise('gb')
    ok1 = len(r1.steps)==0
    ok2 = len(r2.steps)==1
    R("RCN-043", ok1 and ok2, f"'GB'->steps={r1.steps}; 'gb'->steps={r2.steps} (same effective mapping, two different audit trails)")

@block("RCN-044")
def _():
    cn = CodeNormaliser({'GB':'UK'})
    result = cn.normalise(None)
    ok = result.value is None
    R("RCN-044", ok, f"value={result.value}")

print("=== RCN normalise 026-044 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
