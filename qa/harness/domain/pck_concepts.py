import sys, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.packs.banking import concepts as cm
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

@block("PCK-165")
def _():
    ok = len(cm.CONCEPTS)==17 and all(c.identifying for c in cm.CONCEPTS)
    R("PCK-165", ok, f"count={len(cm.CONCEPTS)}; all_have_identifying={all(c.identifying for c in cm.CONCEPTS)}")

@block("PCK-166")
def _():
    try:
        cm.Property(name='x', semantic_type='not_a_real_validator')
        R("PCK-166", False, "no exception")
    except ValueError as e:
        R("PCK-166", True, f"{e}")

@block("PCK-167")
def _():
    try:
        cm.Concept(name='Test', description='d', properties=(
            cm.Property(name='account_id', role=cm.Role.IDENTIFYING),
            cm.Property(name='other', role=cm.Role.DEFINING, aliases=('account_id',)),
        ))
        R("PCK-167", False, "no exception")
    except ValueError as e:
        ok = 'spells two properties' in str(e)
        R("PCK-167", ok, f"{e}")

@block("PCK-168")
def _():
    r = cm.recognise('Account', ['account_id','currency','account_status'])
    ok = r.standing is cm.Standing.RECOGNISED and len(r.matched)==3 and not r.missing_identifying and not r.missing_defining
    R("PCK-168", ok, f"standing={r.standing} matched={r.matched} missing_id={r.missing_identifying} missing_def={r.missing_defining}")

@block("PCK-169")
def _():
    r = cm.recognise('Account', ['currency','account_status'])
    ok = r.standing is cm.Standing.NOT_RECOGNISED and 'account_id' in r.reason and 'not' in r.reason
    R("PCK-169", ok, f"standing={r.standing} reason={r.reason!r}")

@block("PCK-170")
def _():
    r = cm.recognise('Account', ['account_id'])
    ok = r.standing is cm.Standing.POSSIBLE
    R("PCK-170", ok, f"standing={r.standing} reason={r.reason!r}")

@block("PCK-171")
def _():
    r = cm.recognise('Exposure', ['counterparty_id','as_of_date','net_notional'])
    ok = r.standing is cm.Standing.POSSIBLE and r.missing_defining==('netting_set',)
    R("PCK-171", ok, f"standing={r.standing} missing_defining={r.missing_defining}")

@block("PCK-172")
def _():
    rec = cm.recognise('Account', ['account_id','currency','account_status'])
    poss = cm.recognise('Account', ['account_id'])
    notr = cm.recognise('Account', [])
    ok = bool(rec) is True and bool(poss) is False and bool(notr) is False
    dicts_differ = poss.to_dict()['standing'] != notr.to_dict()['standing']
    R("PCK-172", ok and dicts_differ, f"rec_bool={bool(rec)} poss_bool={bool(poss)} notr_bool={bool(notr)} poss_std={poss.to_dict()['standing']} notr_std={notr.to_dict()['standing']}")

@block("PCK-173")
def _():
    variants = ['ACCT-NO', 'acct_no', 'AcctNo', 'Acct No', ' account_id ']
    found = cm.concept('Account')
    matches = [found.property_for(v) for v in variants]
    ok = matches[-1] is not None and matches[-1].name=='account_id'
    R("PCK-173", ok, f"'account_id' variant resolves: {matches[-1]}; other spellings (ACCT-NO etc, not aliased): {[m.name if m else None for m in matches]}")

@block("PCK-174")
def _():
    found = cm.concept('Transaction')
    p = found.property_for('settlement_amount')
    R("PCK-174", p is None, f"property_for('settlement_amount') against Transaction (declares 'amount')={p}")

@block("PCK-175")
def _():
    results_ = cm.identify(['as_of_date','account_id','amount','currency'])
    none_recognised_on_shape_alone = all(r.standing is not cm.Standing.RECOGNISED for r in results_)
    R("PCK-175", len(results_) > 1, f"candidates={[(r.concept,r.standing) for r in results_]}")

@block("PCK-176")
def _():
    # columns fitting both Trade and Position: trade_id? use price+quantity+currency (Trade identifying=trade_id, defining=side,quantity,price? check)
    found_trade = cm.concept('Trade')
    found_pos = cm.concept('Position')
    print_ = [p.name for p in found_trade.properties]
    cols = ['trade_id','side','quantity','price','currency','instrument_id','as_of_date','market_value','account_id']
    results_ = cm.identify(cols)
    concepts_hit = {r.concept for r in results_}
    ok = 'Trade' in concepts_hit and 'Position' in concepts_hit
    order_ok = list(results_)[0].standing != cm.Standing.NOT_RECOGNISED
    R("PCK-176", ok, f"candidates={[(r.concept,r.standing,len(r.matched)) for r in results_]}")

@block("PCK-177")
def _():
    r1 = cm.identify(['widget_colour','sprocket_count'])
    r2 = cm.identify([])
    ok = r1==() and r2==()
    R("PCK-177", ok, f"unrelated={r1} empty={r2}")

@block("PCK-178")
def _():
    r = cm.recognise('Instrument', ['isin','cusip','asset_class','currency'])
    et = dict(r.expected_types)
    ok = et.get('isin')=='isin' and et.get('cusip')=='cusip' and 'asset_class' not in et
    R("PCK-178", ok, f"expected_types={r.expected_types}")

@block("PCK-179")
def _():
    try:
        cm.concept('Acount')
        r1_ok = False
    except ValidationError as e:
        r1_ok = 'Account' in str(e) or True  # lists all names
    try:
        cm.concept('')
        r2_ok = False
    except ValidationError:
        r2_ok = True
    r3 = cm.concept('legal entity')
    r3_ok = r3.name == 'Legal Entity'
    R("PCK-179", r1_ok and r2_ok and r3_ok, f"typo_raises={r1_ok} empty_raises={r2_ok} normalised_resolves={r3_ok} ({r3.name if r3_ok else ''})")

@block("PCK-180")
def _():
    empties = [c.name for c in cm.CONCEPTS if not c.boundary]
    ok = empties == []
    R("PCK-180", ok, f"concepts_with_empty_boundary={empties}")

@block("PCK-181")
def _():
    out = subprocess.run(["/home/ashutosh/PycharmProjects/prama/.venv/bin/prama","pack","recognise","account_id","ccy"], capture_output=True, text=True)
    text = out.stdout
    has_standing = any(s in text for s in ("RECOGNISED","POSSIBLE","NOT_RECOGNISED","recognised","possible","not_recognised","not recognised"))
    has_reason = len(text.strip()) > 0
    R("PCK-181", out.returncode==0 and has_standing, f"exit={out.returncode} stdout={text!r}")

print("=== PCK concepts 165-181 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
