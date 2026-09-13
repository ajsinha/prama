import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.importers import importer, IMPORTERS
from prama.importers.dbt import DbtImporter
from prama.core.errors import RegistryError

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

@block("IMP-001")
def _():
    names = ('dbt','soda','great_expectations','great-expectations','GREAT EXPECTATIONS')
    detail = []
    ok = True
    for n in names[:4]:
        try:
            importer(n)
            detail.append(f"{n}: resolved")
        except Exception as e:
            ok = False
            detail.append(f"{n}: refused {e}")
    try:
        importer(names[4])
        ok = False
        detail.append(f"{names[4]}: resolved (should refuse)")
    except RegistryError:
        detail.append(f"{names[4]}: refused correctly")
    R("IMP-001", ok, "; ".join(detail))

@block("IMP-002")
def _():
    try:
        importer('montecarlo')
        R("IMP-002", False, "no exception")
    except RegistryError as e:
        ok = all(n in str(e) for n in ('dbt','soda','great_expectations'))
        R("IMP-002", ok, f"{e}")

@block("IMP-003")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[
        {"name":"id","tests":["unique","not_null"]},
        {"name":"status","tests":[{"accepted_values":{"values":[]}}]},
    ]}]}
    result = imp.read(doc)
    text = result.render()
    ok = str(result.imported) in text and len(result.caveats)>=1 and len(result.unmapped)>=1
    R("IMP-003", ok, f"imported={result.imported} caveats={len(result.caveats)} unmapped={len(result.unmapped)}; render:\n{text}")

@block("IMP-004")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"id","tests":["not_null"]}]}]}
    result = imp.read(doc)
    ok = "Nothing was left behind." in result.render()
    R("IMP-004", ok, f"{result.render()}")

@block("IMP-005")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"id","tests":["unique"]}]}]}
    result = imp.read(doc)
    ok = result.is_complete and len(result.caveats)==1
    R("IMP-005", None, f"is_complete={result.is_complete} caveats={len(result.caveats)} (is_complete ignores caveats, so 'complete' claims more than 'nothing lost meaning')")

@block("IMP-006")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","tests":["weird_custom_test"]}]}
    result = imp.read(doc)
    ok = len(result.unmapped)==1 and 'weird_custom_test' in result.unmapped[0].source
    R("IMP-006", ok, f"source={result.unmapped[0].source!r}")

@block("IMP-007")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders", "tests":[{"expression_is_true":{"expression":"amount > 0 AND"}}],
                       "columns":[{"name":"id","tests":["not_null"]}]}]}
    try:
        result = imp.read(doc)
        ok = result.imported>=1 and any('amount > 0 AND' in u.source or 'expression_is_true' in u.source for u in result.unmapped)
        R("IMP-007", ok, f"imported={result.imported} unmapped={[u.source for u in result.unmapped]}")
    except Exception as e:
        R("IMP-007", False, f"whole import ABORTED with unhandled {type(e).__name__}: {e}")

@block("IMP-008")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"id","tests":["not_null"]}]}]}
    result = imp.read(doc)
    ctrl_text = result.controls[0].render()
    ok = 'Imported from' in ctrl_text
    R("IMP-008", ok, f"{ctrl_text}")

@block("IMP-009")
def _():
    from prama.importers.soda import SodaImporter
    imp = SodaImporter()
    doc = {"checks for orders": ["missing_count(x) = 0 # it's a check with an apostrophe"]}
    # Actually test via origin escaping directly:
    from prama.importers.spi import because
    clause = because("a check with it's apostrophe")
    ok = "it''s" in clause
    from prama.pql.parser import parse_control
    try:
        parse_control(f"CHECK t.c IS NOT NULL {clause}")
        parses=True
    except Exception:
        parses=False
    R("IMP-009", ok and parses, f"clause={clause!r} parses={parses}")

@block("IMP-010")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"id","tests":["unique","not_null"]}]}]}
    result = imp.read(doc)
    texts = [c.render() for c in result.controls]
    ok = any('IS NOT NULL' in t for t in texts) and any('HAS UNIQUE KEY (id)' in t for t in texts)
    has_grain_caveat = any('weaker than the grain' in c.note for c in result.caveats)
    R("IMP-010", ok and has_grain_caveat, f"{texts}; caveats={[c.note[:40] for c in result.caveats]}")

@block("IMP-011")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"status","tests":[{"accepted_values":{"values":["A","B"]}}]}]}]}
    result = imp.read(doc)
    ok = len(result.caveats)==1 and 'TREAT UNKNOWN AS PASS' in result.caveats[0].note
    from prama.pql.parser import parse_control
    try:
        parse_control("CHECK t.c IN ('A') TREAT UNKNOWN AS PASS BECAUSE 'x'")
        real_clause = True
    except Exception as e:
        real_clause = False
    R("IMP-011", ok and real_clause, f"caveat={result.caveats[0].note if result.caveats else None}; TREAT_UNKNOWN_AS_PASS_parses={real_clause}")

@block("IMP-012")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"status","tests":[{"accepted_values":{}}]}]}]}
    result = imp.read(doc)
    ok = len(result.unmapped)==1 and 'Give the permitted values' in result.unmapped[0].remedy
    R("IMP-012", ok, f"{result.unmapped[0].remedy if result.unmapped else None}")

@block("IMP-013")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"account_id","tests":[
        {"relationships":{"to":"ref('accounts')","field":"id"}},
        ]}]},
        {"name":"orders2","columns":[{"name":"account_id","tests":[
        {"relationships":{"to":"source('raw','accounts')","field":"id"}},
        ]}]}]}
    result = imp.read(doc)
    texts = [c.render() for c in result.controls]
    ok = any('REFERENCES accounts.id' in t for t in texts) and sum('REFERENCES accounts.id' in t for t in texts)==2
    R("IMP-013", ok, f"{texts}")

@block("IMP-014")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"account_id","tests":[
        {"relationships":{"to":"ref('accounts', v=2)","field":"id"}}]}]}]}
    result = imp.read(doc)
    texts = [c.render() for c in result.controls]
    ok = any('REFERENCES accounts.id' in t for t in texts)
    R("IMP-014", ok, f"controls={texts} unmapped={[u.source for u in result.unmapped]}")

@block("IMP-015")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"account_id","tests":[
        {"relationships":{"to":"ref('accounts')"}}]}]}]}
    result = imp.read(doc)
    ok = len(result.unmapped)==1 and 'both' in result.unmapped[0].reason
    R("IMP-015", ok, f"{result.unmapped}")

@block("IMP-016")
def _():
    imp = DbtImporter()
    doc1 = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"accepted_range":{"min_value":0}}]}]}]}
    r1 = imp.read(doc1)
    doc2 = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"accepted_range":{"min_value":0,"max_value":100,"inclusive":False}}]}]}]}
    r2 = imp.read(doc2)
    ok = len(r1.unmapped)==1 and 'CHECK' in r1.unmapped[0].remedy and len(r2.unmapped)==1 and 'exclusive' in r2.unmapped[0].reason
    R("IMP-016", ok, f"r1={r1.unmapped} r2={r2.unmapped}")

@block("IMP-017")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"not_null_proportion":{"at_least":0.95}}]}]}]}
    result = imp.read(doc)
    ctrl = result.controls[0].render()
    ok = 'BELOW 5%' in ctrl and len(result.caveats)==1
    R("IMP-017", ok, f"{ctrl}; caveat={result.caveats[0].note if result.caveats else None}")

@block("IMP-018")
def _():
    imp = DbtImporter()
    doc1 = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"not_null_proportion":{"at_least":95}}]}]}]}
    r1 = imp.read(doc1)
    txt1 = r1.controls[0].render() if r1.controls else str(r1.unmapped)
    has_negative = '-' in txt1 and '%' in txt1
    R("IMP-018", not has_negative, f"at_least=95 (percentage not proportion) -> {txt1}")

@block("IMP-019")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","tests":[{"unique_combination_of_columns":{"combination_of_columns":["a","b","c"]}}]}]}
    result = imp.read(doc)
    ctrl = result.controls[0].render()
    ok = 'HAS UNIQUE KEY (a, b, c)' in ctrl and len(result.caveats)==0
    R("IMP-019", ok, f"{ctrl} caveats={result.caveats}")

@block("IMP-020")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","tests":[{"expression_is_true":{"expression":"amount % 3 = 0"}}]}]}
    result = imp.read(doc)
    ok = len(result.caveats)==1 and 'dialect' in result.caveats[0].note
    R("IMP-020", ok, f"{result.caveats}")

@block("IMP-021")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"dbt_utils.accepted_range":{"min_value":0,"max_value":100}}]}]}]}
    r1 = imp.read(doc)
    doc2 = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"dbt_expectations.expect_column_values_to_be_between":{"min_value":0,"max_value":100}}]}]}]}
    r2 = imp.read(doc2)
    ok = len(r1.controls)==1 and len(r2.controls)==0 and len(r2.unmapped)==1
    R("IMP-021", ok, f"r1_controls={len(r1.controls)} r2_controls={len(r2.controls)} r2_unmapped={[u.source for u in r2.unmapped]}")

@block("IMP-022")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"amt","tests":["assert_positive_amount"]}]}]}
    result = imp.read(doc)
    ok = len(result.unmapped)==1 and 'will not guess' in result.unmapped[0].remedy
    R("IMP-022", ok, f"{result.unmapped}")

@block("IMP-023")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"amt","tests":[{"accepted_values":{"values":["A"]},"config":{"severity":"warn"}}]}]}]}
    result = imp.read(doc)
    ok = len(result.unmapped)==1
    has_readable_name = result.unmapped[0].source.strip() != 'dbt test  on orders.amt' and 'dbt test' in result.unmapped[0].source
    empty_name_bug = 'dbt test  on' in result.unmapped[0].source
    R("IMP-023", not empty_name_bug, f"unmapped_source={result.unmapped[0].source!r}")

@block("IMP-024")
def _():
    imp = DbtImporter()
    doc = {
        "models":[{"name":"m1","columns":[{"name":"id","tests":["not_null"]}]}],
        "sources":[{"name":"raw","tables":[{"name":"src1","columns":[{"name":"id","tests":["not_null"]}]}]}],
        "seeds":[{"name":"s1","columns":[{"name":"id","tests":["not_null"]}]}],
        "snapshots":[{"name":"sn1","columns":[{"name":"id","tests":["not_null"]}]}],
    }
    result = imp.read(doc)
    ok = len(result.controls)==4
    targets = [c.target for c in result.controls]
    ok2 = 'src1' in targets
    R("IMP-024", ok and ok2, f"controls={len(result.controls)} targets={targets}")

@block("IMP-025")
def _():
    imp = DbtImporter()
    doc = {"models":[{"name":"orders","columns":[{"name":"id","data_tests":["not_null"]}]}]}
    result = imp.read(doc)
    ok = len(result.controls)==1
    R("IMP-025", ok, f"controls={len(result.controls)}")

@block("IMP-026")
def _():
    imp = DbtImporter()
    cases = [[], "a string", None, {}]
    detail = []
    ok = True
    for c in cases[:3]:
        result = imp.read(c)
        stated = len(result.unmapped)==1 and 'not a dbt schema' in result.unmapped[0].reason
        ok &= stated
        detail.append(f"{c!r}: unmapped={result.unmapped}")
    empty_dict_result = imp.read({})
    empty_ok = len(empty_dict_result.controls)==0
    nothing_said = "Nothing was left behind" in empty_dict_result.render()
    detail.append(f"empty dict: controls=0, render_says_nothing_left_behind={nothing_said}")
    R("IMP-026", ok, "; ".join(detail))

print("=== IMP dbt/spi 001-026 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
