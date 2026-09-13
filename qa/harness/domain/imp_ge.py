import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.importers.great_expectations import GreatExpectationsImporter, _tolerance

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

def suite(*expectations, name="orders"):
    return {"expectation_suite_name": name, "expectations": list(expectations)}

@block("IMP-044")
def _():
    imp = GreatExpectationsImporter()
    exps = [
        {"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id"}},
        {"expectation_type":"expect_column_values_to_be_unique","kwargs":{"column":"id"}},
        {"expectation_type":"expect_column_values_to_be_in_set","kwargs":{"column":"status","value_set":["A","B"]}},
        {"expectation_type":"expect_column_values_to_be_between","kwargs":{"column":"amt","min_value":0,"max_value":100}},
        {"expectation_type":"expect_column_values_to_match_regex","kwargs":{"column":"code","regex":"^[A-Z]+$"}},
        {"expectation_type":"expect_table_row_count_to_be_between","kwargs":{"min_value":1,"max_value":1000}},
        {"expectation_type":"expect_table_row_count_to_equal","kwargs":{"value":500}},
    ]
    result = imp.read(suite(*exps))
    ok = len(result.controls)==7
    value_caveats = [c for c in result.caveats if 'null' in c.note.lower()]
    R("IMP-044", ok and len(value_caveats)>=3, f"controls={len(result.controls)} caveats={len(result.caveats)}")

@block("IMP-045")
def _():
    imp = GreatExpectationsImporter()
    r99 = imp.read(suite({"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id","mostly":0.99}}))
    r10 = imp.read(suite({"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id","mostly":1.0}}))
    rnone = imp.read(suite({"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id"}}))
    c99 = r99.controls[0].render(); c10 = r10.controls[0].render(); cnone = rnone.controls[0].render()
    ok = 'BELOW 1%' in c99 and 'BELOW' not in c10 and 'BELOW' not in cnone
    states_both = any('99%' in c.note or '0.99' in c.note for c in r99.caveats)
    R("IMP-045", ok and states_both, f"0.99={c99} 1.0={c10} none={cnone}")

@block("IMP-046")
def _():
    a,anote = _tolerance("0.99")
    b,bnote = _tolerance(None)
    c,cnote = _tolerance("high")
    R("IMP-046", not (c=="" and cnote==""), f"'0.99'(str)->{a!r}; None->{b!r}; 'high'->({c!r},{cnote!r}) -- an unreadable mostly silently becomes NO tolerance with no caveat and no unmapped entry, tighter than the suite with no report at all")

@block("IMP-047")
def _():
    imp = GreatExpectationsImporter()
    r1 = imp.read(suite({"expectation_type":"expect_column_values_to_be_unique","kwargs":{"column":"id"}}))
    r2 = imp.read(suite({"expectation_type":"expect_compound_columns_to_be_unique","kwargs":{"column_list":["a","b"]}}))
    ok = len(r1.caveats)==1 and 'weaker than the grain' in r1.caveats[0].note and len(r2.caveats)==0
    R("IMP-047", ok, f"r1_caveats={r1.caveats} r2_caveats={r2.caveats}")

@block("IMP-048")
def _():
    imp = GreatExpectationsImporter()
    r = imp.read(suite({"expectation_type":"expect_column_values_to_be_between","kwargs":{"column":"amt","min_value":0,"max_value":100,"strict_min":True}}))
    ok = not r.controls and 'exclusive' in r.unmapped[0].reason
    R("IMP-048", ok, f"{r.unmapped}")

@block("IMP-049")
def _():
    imp = GreatExpectationsImporter()
    r_min = imp.read(suite({"expectation_type":"expect_column_values_to_be_between","kwargs":{"column":"amt","min_value":0}}))
    r_max = imp.read(suite({"expectation_type":"expect_column_values_to_be_between","kwargs":{"column":"amt","max_value":100}}))
    ok_min = not r_min.controls and '>' in r_min.unmapped[0].remedy
    remedy_max = r_max.unmapped[0].remedy if r_max.unmapped else ""
    max_correct = '<' in remedy_max and '>' not in remedy_max
    R("IMP-049", ok_min and max_correct, f"min_only_remedy={r_min.unmapped[0].remedy if r_min.unmapped else None}; max_only_remedy={remedy_max}")

@block("IMP-050")
def _():
    imp = GreatExpectationsImporter()
    r_min = imp.read(suite({"expectation_type":"expect_table_row_count_to_be_between","kwargs":{"min_value":10}}))
    r_max = imp.read(suite({"expectation_type":"expect_table_row_count_to_be_between","kwargs":{"max_value":100}}))
    r_both = imp.read(suite({"expectation_type":"expect_table_row_count_to_be_between","kwargs":{"min_value":10,"max_value":100}}))
    r_neither = imp.read(suite({"expectation_type":"expect_table_row_count_to_be_between","kwargs":{}}))
    c_min = r_min.controls[0].render() if r_min.controls else None
    c_max = r_max.controls[0].render() if r_max.controls else None
    c_both = r_both.controls[0].render() if r_both.controls else None
    ok = ('AT LEAST' in c_min and 'AT MOST' in c_max and 'BETWEEN' in c_both and not r_neither.controls)
    R("IMP-050", ok, f"min={c_min} max={c_max} both={c_both} neither_unmapped={r_neither.unmapped}")

@block("IMP-051")
def _():
    imp = GreatExpectationsImporter()
    r1 = imp.read(suite({"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id"}}, name="warehouse.orders.critical"))
    r2 = imp.read({"expectations":[{"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id"}}]})
    t1 = r1.controls[0].target if r1.controls else None
    t2 = r2.controls[0].target if r2.controls else None
    R("IMP-051", None, f"suite_name='warehouse.orders.critical' -> control target dataset={t1!r} (naive .split('.')[-1] gives 'critical' not 'orders'); no name at all -> target={t2!r}")

@block("IMP-052")
def _():
    imp = GreatExpectationsImporter()
    json_text = '{"expectation_suite_name":"orders","expectations":[{"expectation_type":"expect_column_values_to_not_be_null","kwargs":{"column":"id"}}]}'
    result = imp.read_text(json_text)
    json_ok = len(result.controls)==1
    yaml_text = "a: 1\nb: [1,2\n"  # malformed YAML/not valid JSON
    try:
        imp.read_text(yaml_text)
        yaml_readable = True
    except Exception as e:
        yaml_readable = False
        err = e
    R("IMP-052", json_ok and not yaml_readable, f"json_ok={json_ok}; yaml_fails_honestly={not yaml_readable} ({err if not yaml_readable else ''})")

@block("IMP-053")
def _():
    imp = GreatExpectationsImporter()
    r = imp.read(suite({"expectation_type":"expect_column_values_to_be_increasing","kwargs":{"column":"id"}}))
    ok = not r.controls and 'single keyword' in r.unmapped[0].remedy
    R("IMP-053", ok, f"{r.unmapped}")

@block("IMP-054")
def _():
    imp = GreatExpectationsImporter()
    r = imp.read(suite({"expectation_type":"expect_column_values_to_be_in_set","kwargs":{"column":"city","value_set":["NEW  YORK","LA"]}}))
    c = r.controls[0].render() if r.controls else None
    ok = c and "NEW  YORK" in c
    R("IMP-054", ok, f"{c!r}")

print("=== IMP great_expectations 044-054 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
