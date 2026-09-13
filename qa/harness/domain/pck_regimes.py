import sys, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
import prama.packs as p
p.install_shipped()
from prama.packs.banking.regimes import REGIME_OBLIGATIONS, REGIME_SCOPE
from prama.packs.banking.obligations import OBLIGATIONS, ALL_OBLIGATIONS, DISCHARGEABLE_PRINCIPLES, SUPPORTED_NOT_DISCHARGED, catalogue
from prama.packs.banking.regulatory import Catalogue, Citation, Obligation, Template, Standing
from prama.pql.parser import parse_control
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

def _bind_val(role, dataset_role=False):
    if role in ("minimum",):
        return "0"
    if role in ("maximum",):
        return "1000000"
    if role == "window":
        return "24 HOURS"
    if role in ("dataset","trade_store","target_dataset"):
        return "accounts" if role=="dataset" else "trades"
    return "col"

@block("PCK-182")
def _():
    n = 0
    failures = []
    for ob in ALL_OBLIGATIONS:
        for t in ob.templates:
            n += 1
            cols = {r: _bind_val(r) for r in t.requires}
            try:
                pql = t.bind(cols)
                parse_control(pql)
            except Exception as e:
                failures.append((t.identity, str(e)[:150]))
    ok = len(failures)==0
    R("PCK-182", ok, f"templates_checked={n} failures={failures}")

@block("PCK-183")
def _():
    gdpr = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='gdpr-retention-floor'), None)
    assert gdpr is not None, "gdpr-retention-floor template not found"
    cols = {r: 'col' for r in gdpr.requires}
    pql = gdpr.bind(cols)
    try:
        ctrl = parse_control(pql)
        R("PCK-183", True, f"parsed OK: {pql}")
    except Exception as e:
        R("PCK-183", False, f"pql={pql!r} error={e}")

@block("PCK-184")
def _():
    from prama.pql.library import FUNCTIONS
    emir = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='emir-notional-sign'), None)
    cols = {r: 'col' for r in emir.requires}
    pql = emir.bind(cols)
    try:
        ctrl = parse_control(pql)
        from prama.pql.types import TypeChecker, Catalogue as TCatalogue, DatasetSchema, Column
        cat = TCatalogue.of(col={'col':'text'})
        cat2 = TCatalogue({'accounts': None})
        tc = TypeChecker(TCatalogue.of(accounts={'col':'text'}))
        findings = tc.check(ctrl)
        unresolved = [f for f in findings if 'unknown function' in f.message.lower() or 'no function' in f.message.lower() or 'not a known function' in f.message.lower()]
        R("PCK-184", len(unresolved)==0, f"pql={pql}; findings={[(f.level,f.message) for f in findings]}; FUNCTIONS has NOTIONAL_SIGN_MATCHES_SIDE: {'NOTIONAL_SIGN_MATCHES_SIDE' in [n for n in dir(FUNCTIONS)]}")
    except Exception as e:
        R("PCK-184", False, f"pql={pql!r} error={type(e).__name__}: {e}")

@block("PCK-185")
def _():
    from prama.packs.banking.crossfield import BANKING_FUNCTIONS
    sm = next(f for f in BANKING_FUNCTIONS if f.name=='SIGN_MATCHES_SIDE')
    emir = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='emir-notional-sign'), None)
    template_order = "notional first, side second" if "{notional}, {side}" in emir.pql else "side first, notional second"
    declared_order = sm.argument_types
    ok = template_order == "side first, notional second"
    R("PCK-185", ok, f"template argument order: {template_order}; SIGN_MATCHES_SIDE declared families: {declared_order} (TEXT,NUMBER means side,quantity)")

@block("PCK-186")
def _():
    t = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='mifir-t1-report-arrives'), None)
    results_ = {}
    for window in ('24 HOURS','1d','24','1 DAY'):
        cols = {r: (window if r=='window' else _bind_val(r)) for r in t.requires}
        pql = t.bind(cols)
        try:
            parse_control(pql)
            results_[window] = 'parsed'
        except Exception as e:
            results_[window] = f'refused: {type(e).__name__}'
    ok = results_.get('24 HOURS')=='parsed' and all(results_[w]!='parsed' for w in ('1d','24','1 DAY'))
    R("PCK-186", ok, f"{results_}")

@block("PCK-187")
def _():
    recon = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='reconciles-with'), None)
    if recon is None:
        R("PCK-187", None, "BLOCKED: no template literally named 'reconciles-with' found")
        return
    cols = {r: _bind_val(r) for r in recon.requires}
    if 'counterpart_measure' in cols:
        cols['counterpart_measure'] = 'finance_gl.col'
    pql = recon.bind(cols)
    try:
        ctrl = parse_control(pql)
        R("PCK-187", False, f"parsed without refusal referencing cross-dataset: {pql}")
    except Exception as e:
        R("PCK-187", True, f"refused: {type(e).__name__}: {e}")

@block("PCK-188")
def _():
    mifir = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='mifir-isin-valid'), None)
    if mifir is None:
        mifir = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if 'isin' in t.identity), None)
    try:
        mifir.bind({'dataset':'trades'})
        R("PCK-188", False, "no exception for missing binding")
    except ValidationError as e:
        ok = 'isin' in str(e).lower() or any(r in str(e) for r in mifir.requires)
        R("PCK-188", ok, f"{e}")

@block("PCK-189")
def _():
    t = OBLIGATIONS[0].templates[0]
    cols = {r: 'col' for r in t.requires}
    cols['extra1']='x'; cols['extra2']='y'; cols['extra3']='z'
    try:
        pql = t.bind(cols)
        R("PCK-189", True, f"extras ignored OK: {pql[:80]}...")
    except Exception as e:
        R("PCK-189", False, f"{type(e).__name__}: {e}")
    # also test out-of-step requires vs pql placeholder -> bare KeyError
    bad = Template(identity='bad', pql="CHECK {dataset}.{oops} IS NOT NULL BECAUSE 'x'", requires=("dataset",))
    try:
        bad.bind({'dataset':'t'})
        R2 = None
    except KeyError as e:
        R2 = f"bare KeyError: {e}"
    except ValidationError as e:
        R2 = f"ValidationError: {e}"
    results.append(("PCK-189b", "INFO", R2))

@block("PCK-190")
def _():
    t = OBLIGATIONS[0].templates[0]
    role = t.requires[0]
    cols = {r: ('{isin}' if r==role else _bind_val(r)) for r in t.requires}
    pql = t.bind(cols)
    literal_ok = '{isin}' in pql
    try:
        ctrl = parse_control(pql)
        parsed = True
    except Exception:
        parsed = False
    R("PCK-190", literal_ok, f"pql_contains_literal_brace={literal_ok} parses={parsed} pql={pql[:100]}")

@block("PCK-191")
def _():
    try:
        Obligation(identity='X', regime='R', principle='P1', citation=Citation(document='d',clause='c',authority='a'),
                   objective='o', templates=(), relationships=(), not_discharged='')
        R("PCK-191", False, "no exception for obligation with nothing")
    except ValueError as e:
        R("PCK-191", True, f"{e}")

@block("PCK-192")
def _():
    out = subprocess.run(["/home/ashutosh/PycharmProjects/prama/.venv/bin/prama","pack","claims"], capture_output=True, text=True)
    text = out.stdout
    n_unconfirmed = text.count('unconfirmed')
    n_confirmed_true = sum(1 for ob in ALL_OBLIGATIONS if ob.citation.confirmed)
    R("PCK-192", n_confirmed_true==0, f"confirmed_citations_in_code={n_confirmed_true}; 'unconfirmed' mentions in CLI output={n_unconfirmed}")

@block("PCK-193")
def _():
    try:
        Citation(document='d', clause='c', authority='a', confirmed=True)
        R("PCK-193", False, "no exception")
    except ValueError as e:
        R("PCK-193", True, f"{e}")

@block("PCK-194")
def _():
    out = subprocess.run(["/home/ashutosh/PycharmProjects/prama/.venv/bin/prama","pack","claims"], capture_output=True, text=True)
    text = out.stdout
    has_not_discharged = any(ob.not_discharged and ob.not_discharged in text for ob in ALL_OBLIGATIONS[:3])
    has_regime_scope_text = any(v[:20] in text for v in list(REGIME_SCOPE.values())[:3])
    R("PCK-194", out.returncode==0, f"exit={out.returncode} len={len(text)} sample_not_discharged_shown={has_not_discharged} sample_regime_scope_shown={has_regime_scope_text}")

@block("PCK-195")
def _():
    discharged = set(DISCHARGEABLE_PRINCIPLES)
    supported = set(SUPPORTED_NOT_DISCHARGED.keys())
    union = discharged | supported
    all14 = {f"P{i}" for i in range(1,15)}
    missing = all14 - union
    ok = missing == set()
    R("PCK-195", ok, f"union={sorted(union)} missing={sorted(missing)}")

@block("PCK-196")
def _():
    regimes_in_obligations = {ob.regime for ob in REGIME_OBLIGATIONS}
    missing = [r for r in regimes_in_obligations if r not in REGIME_SCOPE]
    all_have_not_clause = all('Not ' in REGIME_SCOPE[r] or 'not ' in REGIME_SCOPE[r] for r in REGIME_SCOPE if r in regimes_in_obligations)
    from prama.packs.banking.obligations import BCBS_239, ISO_20022
    bcbs_covered = BCBS_239 in REGIME_SCOPE
    iso_covered = ISO_20022 in REGIME_SCOPE
    R("PCK-196", not missing and bcbs_covered and iso_covered, f"regimes_missing_scope={missing}; BCBS_239_covered={bcbs_covered}; ISO_20022_covered={iso_covered}; REGIME_SCOPE_keys={list(REGIME_SCOPE.keys())}")

@block("PCK-197")
def _():
    t = next((t for ob in ALL_OBLIGATIONS for t in ob.templates if t.identity=='mifir-t1-every-trade-reported'), None)
    # direction: CHECK {trade_store}.{trade_id} REFERENCES {dataset}.{report_trade_id}
    ok = '{trade_store}' in t.pql.split('REFERENCES')[0]
    R("PCK-197", ok, f"pql={t.pql}")

@block("PCK-198")
def _():
    cat = catalogue()
    ob = ALL_OBLIGATIONS[0]
    cov = cat.coverage(ob.regime, controls_by_template={ob.templates[0].identity: ['ctrl-1']})
    entry = next((s for s in cov.standings if s.obligation.identity==ob.identity), None)
    R("PCK-198", entry is not None and entry.standing.name=='ADDRESSED_UNPROVEN' and entry.standing.is_a_gap, f"standing={entry.standing if entry else None} is_a_gap={entry.standing.is_a_gap if entry else None} label={entry.standing.label if entry else None}")

@block("PCK-199")
def _():
    cat = catalogue()
    ob = ALL_OBLIGATIONS[0]
    tmpl_id = ob.templates[0].identity
    cov = cat.coverage(ob.regime, controls_by_template={tmpl_id: ['c1','c2','c3']}, verdicts={'c1':'pass'})
    entry = next(s for s in cov.standings if s.obligation.identity==ob.identity)
    is_proven_clean = entry.standing.name == 'PROVEN_CLEAN'
    R("PCK-199", not is_proven_clean, f"controls=3, 1 pass, 2 never-ran -> standing={entry.standing} never_ran={entry.never_ran} passed={entry.passed} (Expected: something other than PROVEN_CLEAN, or never_ran surfaced prominently)")

@block("PCK-200")
def _():
    cat = catalogue()
    ob = ALL_OBLIGATIONS[0]
    cov = cat.coverage(ob.regime, controls_by_template={})
    entry = next((s for s in cov.standings if s.obligation.identity==ob.identity), None)
    ok = entry is not None and entry.standing.name=='UNADDRESSED'
    R("PCK-200", ok, f"standing={entry.standing if entry else None}; describe leads with unaddressed count: {cov.describe()[:200]}")

@block("PCK-201")
def _():
    cat = catalogue()
    cov = cat.coverage('MiFID II', controls_by_template={})
    d = cov.describe()
    ok = 'no obligations' in d.lower() or 'not loaded' in d.lower()
    R("PCK-201", ok, f"describe={d!r}")

@block("PCK-202")
def _():
    cat = catalogue()
    p4 = cat.of_principle('P4')
    regimes_seen = {ob.regime for ob in p4}
    ok = len(p4) > 0 and len(regimes_seen) >= 1
    from prama.packs.banking.obligations import BCBS_239
    bcbs_only = regimes_seen == {BCBS_239}
    R("PCK-202", ok and not bcbs_only, f"P4_count={len(p4)} regimes={regimes_seen}")

print("=== PCK regimes 182-202 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
