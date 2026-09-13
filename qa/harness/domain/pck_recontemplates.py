import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from datetime import date
from prama.packs.banking import reconciliations as rc
from prama.recon.engine import Reconciliation
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

@block("PCK-203")
def _():
    ids = rc.identities()
    ok = len(ids)==9
    R("PCK-203", ok, f"identities({len(ids)})={ids}")

def bind_all(t):
    left_cols = {role: f"l_{role}" for role in (*t.key_roles, t.amount_role)}
    right_cols = {role: f"r_{role}" for role in (*t.key_roles, t.amount_role)}
    return t.bind(left_dataset="left_ds", right_dataset="right_ds",
                  left_columns=left_cols, right_columns=right_cols,
                  left_currency_column="ccy", right_currency_column="ccy", target_currency="USD")

@block("PCK-204")
def _():
    detail=[]
    ok=True
    for t in rc.TEMPLATES:
        try:
            defn = bind_all(t)
            recon = Reconciliation(defn)
            row = {c: 'K1' for c in defn.key.left}
            row[defn.left.amount_column]=100
            row['ccy']='USD'
            rowr = {c: 'K1' for c in defn.key.right}
            rowr[defn.right.amount_column]=100
            rowr['ccy']='USD'
            run = recon.run([row],[rowr], business_date=date(2026,1,1))
            detail.append(f"{t.identity}: completed={run.completed}")
        except Exception as e:
            ok=False
            detail.append(f"{t.identity}: EXCEPTION {type(e).__name__}: {e}")
    R("PCK-204", ok, "; ".join(detail))

@block("PCK-205")
def _():
    t = rc.template('subledger-to-gl')
    left_cols = {role: f"l_{role}" for role in (*t.key_roles, t.amount_role)}
    right_cols = {role: f"r_{role}" for role in (*t.key_roles, t.amount_role)}
    del right_cols['cost_centre']
    try:
        t.bind(left_dataset="l", right_dataset="r", left_columns=left_cols, right_columns=right_cols)
        R("PCK-205", False, "no exception for missing role on right side")
    except ValidationError as e:
        ok = 'right' in str(e) and 'cost_centre' in str(e)
        R("PCK-205", ok, f"{e}")

@block("PCK-206")
def _():
    t = rc.TEMPLATES[0]
    defn = bind_all(t)
    import dataclasses
    from prama.recon.normalise import AmountSpec
    defn2 = dataclasses.replace(defn,
        left=dataclasses.replace(defn.left, spec=AmountSpec(currency_column='ccy')),
        right=dataclasses.replace(defn.right, spec=AmountSpec(currency_column='ccy')),
        target_currency='')
    recon = Reconciliation(defn2)
    row = {c: 'K1' for c in defn2.key.left}; row[defn2.left.amount_column]=100; row['ccy']='EUR'
    rowr = {c: 'K1' for c in defn2.key.right}; rowr[defn2.right.amount_column]=100; rowr['ccy']='EUR'
    try:
        run = recon.run([row],[rowr], business_date=date(2026,1,1))
        R("PCK-206", not run.completed, f"completed={run.completed} refusal={run.refusal!r} (Expected: refusal at bind time OR a run comparing like with like -- neither: it ran and {'refused mid-run' if not run.completed else 'silently produced a result'})")
    except ValidationError as e:
        R("PCK-206", True, f"refused at bind/construction: {e}")

@block("PCK-207")
def _():
    t1 = rc.template('position-to-custodian')
    defn1 = bind_all(t1)
    recon1 = Reconciliation(defn1)
    row1 = {c:'K1' for c in defn1.key.left}; row1[defn1.left.amount_column]=100; row1['ccy']='USD'
    row1r = {c:'K1' for c in defn1.key.right}; row1r[defn1.right.amount_column]=101; row1r['ccy']='USD'
    run1 = recon1.run([row1],[row1r], business_date=date(2026,1,1))
    has_break1 = len(run1.population)>0

    t2 = rc.template('front-office-to-subledger')
    defn2 = bind_all(t2)
    recon2 = Reconciliation(defn2)
    row2 = {c:'K1' for c in defn2.key.left}; row2[defn2.left.amount_column]=100.00; row2['ccy']='USD'
    row2r = {c:'K1' for c in defn2.key.right}; row2r[defn2.right.amount_column]=100.005; row2r['ccy']='USD'
    run2 = recon2.run([row2],[row2r], business_date=date(2026,1,1))
    has_break2 = len(run2.population)>0
    R("PCK-207", has_break1 and not has_break2, f"exact_tolerance(1-unit diff)_has_break={has_break1}; materiality(0.005 diff)_has_break={has_break2}")

@block("PCK-208")
def _():
    t = rc.template('subledger-to-gl')
    rationale = t.tolerance_rationale
    tol = t.tolerance
    claims_currency_specific = 'currency-specific' in rationale.lower() or 'currency specific' in rationale.lower()
    from prama.semantic.relationships import Tolerance
    import dataclasses as dc
    tol_fields = dc.fields(Tolerance)
    has_currency_field = any('currency' in f.name for f in tol_fields)
    R("PCK-208", not (claims_currency_specific and not has_currency_field), f"rationale={rationale!r} tolerance={tol} Tolerance_fields={[f.name for f in tol_fields]} has_currency_awareness={has_currency_field}")

@block("PCK-209")
def _():
    t = rc.template('cashbook-to-statement')
    defn = bind_all(t)
    recon = Reconciliation(defn)
    # key_roles = account, value_date, reference; last key component (value_date) shifted by 2 days
    row = {'l_account':'ACC1', 'l_value_date': date(2026,1,1).isoformat(), 'l_reference':'REF1', 'l_amount':100, 'ccy':'USD'}
    rowr = {'r_account':'ACC1', 'r_value_date': date(2026,1,3).isoformat(), 'r_reference':'REF1', 'r_amount':100, 'ccy':'USD'}
    run = recon.run([row],[rowr], business_date=date(2026,1,1))
    n_pairs = len(run.match.pairs)
    n_breaks = len(run.population)
    n_missing_or_extra = sum(1 for b in run.population.breaks if b.kind.name in ('MISSING','EXTRA'))
    ok = n_pairs==1 and n_missing_or_extra==0
    kinds = [b.kind.name for b in run.population.breaks]
    R("PCK-209", ok, f"window={defn.date_window} pairs={n_pairs} breaks={n_breaks} break_kinds={kinds} (Expected: one pair classified TIMING, not one missing+one extra)")

@block("PCK-210")
def _():
    empties = [t.identity for t in rc.TEMPLATES if not t.expected_breaks]
    detail = []
    for t in rc.TEMPLATES:
        d = t.describe()
        detail.append('no taxonomy stated' in d)
    ok = not empties and not any(detail)
    R("PCK-210", ok, f"templates_with_empty_expected_breaks={empties}")

@block("PCK-212")
def _():
    import subprocess
    out = subprocess.run(["/home/ashutosh/PycharmProjects/prama/.venv/bin/prama","pack","reconciliation","nosuch"], capture_output=True, text=True)
    text = out.stdout + out.stderr
    ok = out.returncode != 0 and ('nine' not in text.lower() or True) and ('KeyError' not in text)
    lists_all_nine = all(ident in text for ident in rc.identities())
    R("PCK-212", ok and 'KeyError' not in text, f"exit={out.returncode} lists_all_nine={lists_all_nine} output={text[:300]!r}")

print("=== PCK reconciliations 203-212 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
