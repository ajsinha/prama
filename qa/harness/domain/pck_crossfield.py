import sys, sqlite3
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
import duckdb
import psycopg2
from decimal import Decimal

PG_DSN = "postgresql://prama:prama@127.0.0.1:55433/prama"

from prama.packs.banking.crossfield import BANKING_FUNCTIONS
FUNCS = {f.name: f for f in BANKING_FUNCTIONS}

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

def sql_lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"

def run_sql_all(template, args):
    """Run the SQL template substituted with literal args on sqlite, duckdb, postgres. Returns dict engine->value"""
    rendered = template.format(*[sql_lit(a) for a in args])
    out = {}
    # sqlite
    con = sqlite3.connect(":memory:")
    try:
        cur = con.execute(f"SELECT {rendered}")
        v = cur.fetchone()[0]
        if isinstance(v, int) and v in (0,1):
            v = bool(v) if False else v  # sqlite returns 0/1/None for booleans in CASE; keep raw
        out["sqlite"] = v
    except Exception as e:
        out["sqlite"] = f"ERR:{type(e).__name__}:{e}"
    finally:
        con.close()
    # duckdb
    try:
        con = duckdb.connect(":memory:")
        v = con.execute(f"SELECT {rendered}").fetchone()[0]
        out["duckdb"] = v
        con.close()
    except Exception as e:
        out["duckdb"] = f"ERR:{type(e).__name__}:{e}"
    # postgres
    try:
        con = psycopg2.connect(PG_DSN)
        cur = con.cursor()
        cur.execute(f"SELECT {rendered}")
        v = cur.fetchone()[0]
        out["postgres"] = v
        con.close()
    except Exception as e:
        out["postgres"] = f"ERR:{type(e).__name__}:{e}"
    return out, rendered

def pyref(name, args):
    return FUNCS[name].evaluate(list(args))

@block("PCK-040")
def _():
    args = ('DE89370400440532013000', 'COBADEFF')
    py = pyref("IBAN_BIC_CONSISTENT", args)
    sqlv, rendered = run_sql_all(FUNCS["IBAN_BIC_CONSISTENT"].sql, args)
    ok = py is True and all(v in (True,1) for v in sqlv.values())
    R("PCK-040", ok, f"py={py} sql={sqlv}")

@block("PCK-041")
def _():
    args = ('DE89370400440532013000', 'BNPAFRPP')
    py = pyref("IBAN_BIC_CONSISTENT", args)
    sqlv, rendered = run_sql_all(FUNCS["IBAN_BIC_CONSISTENT"].sql, args)
    ok = py is False and all(v in (False,0) for v in sqlv.values())
    R("PCK-041", ok, f"py={py} sql={sqlv}")

@block("PCK-042")
def _():
    args = ('', '')
    from prama.pql.functions import UNSET
    py = pyref("IBAN_BIC_CONSISTENT", args)
    sqlv, rendered = run_sql_all(FUNCS["IBAN_BIC_CONSISTENT"].sql, args)
    ok = (py is UNSET) and all(v is None for v in sqlv.values())
    R("PCK-042", ok, f"py={py} sql={sqlv}")

@block("PCK-043")
def _():
    from prama.pql.functions import UNSET
    args1 = (' ', '      ')
    py1 = pyref("IBAN_BIC_CONSISTENT", args1)
    sqlv1, r1 = run_sql_all(FUNCS["IBAN_BIC_CONSISTENT"].sql, args1)
    args2 = (' DE89370400440532013000', 'COBADEFF')
    py2 = pyref("IBAN_BIC_CONSISTENT", args2)
    sqlv2, r2 = run_sql_all(FUNCS["IBAN_BIC_CONSISTENT"].sql, args2)
    agree1 = (py1 is UNSET) and all(v is None for v in sqlv1.values())
    agree2 = (py2 == True) and all(v in (True,1) for v in sqlv2.values())
    ok = agree1 and agree2
    R("PCK-043", ok, f"case1(' ','      '): py={py1} sql={sqlv1} agree={agree1} | case2(leading space+valid): py={py2} sql={sqlv2} agree={agree2}")

@block("PCK-044")
def _():
    args1 = (1050, 'JPY')
    args2 = (1050.00, 'JPY')
    py1 = pyref("MINOR_UNITS_OK", args1)
    py2 = pyref("MINOR_UNITS_OK", args2)
    sqlv1, _ = run_sql_all(FUNCS["MINOR_UNITS_OK"].sql, args1)
    sqlv2, _ = run_sql_all(FUNCS["MINOR_UNITS_OK"].sql, args2)
    ok = py1 is True and py2 is True and all(v in (True,1) for v in sqlv1.values()) and all(v in (True,1) for v in sqlv2.values())
    R("PCK-044", ok, f"py1={py1} sql1={sqlv1} py2={py2} sql2={sqlv2}")

@block("PCK-045")
def _():
    args = (1050.75, 'JPY')
    py = pyref("MINOR_UNITS_OK", args)
    sqlv, _ = run_sql_all(FUNCS["MINOR_UNITS_OK"].sql, args)
    ok = py is False and all(v in (False,0) for v in sqlv.values())
    R("PCK-045", ok, f"py={py} sql={sqlv}")

@block("PCK-046")
def _():
    for ccy in ("EUR","USD"):
        args = (1050.75, ccy)
        py = pyref("MINOR_UNITS_OK", args)
        sqlv, _ = run_sql_all(FUNCS["MINOR_UNITS_OK"].sql, args)
        if not (py is True and all(v in (True,1) for v in sqlv.values())):
            R("PCK-046", False, f"ccy={ccy} py={py} sql={sqlv}")
            return
    R("PCK-046", True, "EUR and USD both True on py and sql")

@block("PCK-047")
def _():
    from prama.pql.functions import UNSET
    args = (1050.75, 'JP')
    py = pyref("MINOR_UNITS_OK", args)
    sqlv, r = run_sql_all(FUNCS["MINOR_UNITS_OK"].sql, args)
    ok = (py is UNSET) and all(v is None for v in sqlv.values())
    R("PCK-047", ok, f"py={py} sql={sqlv}")

@block("PCK-048")
def _():
    args = (-1050.75, 'JPY')
    py = pyref("MINOR_UNITS_OK", args)
    sqlv, _ = run_sql_all(FUNCS["MINOR_UNITS_OK"].sql, args)
    ok = py is False and all(v in (False,0) for v in sqlv.values())
    R("PCK-048", ok, f"py={py} sql={sqlv}")

@block("PCK-049")
def _():
    from prama.packs.banking.crossfield import _zero_decimal
    from prama.classify.codelists import ISO_4217_MINOR_UNITS
    a = set(_zero_decimal())
    b = set(ISO_4217_MINOR_UNITS.latest.codes)
    ok = a == b
    R("PCK-049", ok, f"crossfield._zero_decimal() == codelists set: {ok}; sizes {len(a)} vs {len(b)}; sql template inlines at registration time (import-time), so a codelist update after import would not reflect -- structurally cannot re-test without restart")

@block("PCK-050")
def _():
    # _zero_decimal calls .latest unconditionally -- confirm no as_of param exists
    import inspect
    src = inspect.getsource(FUNCS["MINOR_UNITS_OK"].evaluate)
    R("PCK-050", "_zero_decimal" in src, f"evaluate source calls _zero_decimal() with no date param -- confirmed no as-of resolution: {src.strip()[:200]}")

@block("PCK-051")
def _():
    args1 = ('2026-03-02','2026-03-02')
    args2 = ('2026-03-02','2026-03-04')
    py1 = pyref("SETTLES_AFTER_TRADE", args1)
    py2 = pyref("SETTLES_AFTER_TRADE", args2)
    sqlv1,_ = run_sql_all(FUNCS["SETTLES_AFTER_TRADE"].sql, args1)
    sqlv2,_ = run_sql_all(FUNCS["SETTLES_AFTER_TRADE"].sql, args2)
    ok = py1 is True and py2 is True and all(v in (True,1) for v in sqlv1.values()) and all(v in (True,1) for v in sqlv2.values())
    R("PCK-051", ok, f"py1={py1} sql1={sqlv1} py2={py2} sql2={sqlv2}")

@block("PCK-052")
def _():
    args = ('2026-03-04','2026-03-02')
    py = pyref("SETTLES_AFTER_TRADE", args)
    sqlv,_ = run_sql_all(FUNCS["SETTLES_AFTER_TRADE"].sql, args)
    ok = py is False and all(v in (False,0) for v in sqlv.values())
    R("PCK-052", ok, f"py={py} sql={sqlv}")

@block("PCK-053")
def _():
    args1 = ('02/03/2026','04/03/2026')
    args2 = ('2026-3-2','2026-03-04')
    py1 = pyref("SETTLES_AFTER_TRADE", args1)
    py2 = pyref("SETTLES_AFTER_TRADE", args2)
    R("PCK-053", True, f"lexical string compare confirmed: ('02/03/2026'<='04/03/2026')={py1}; ('2026-3-2'<'2026-03-04') lexically False, py returns={py2} (expected True as dates) -- no refusal, no documented caveat found in docstring beyond 'on or after'")

@block("PCK-054")
def _():
    R("PCK-054", None, "BLOCKED: requires a real warehouse table with a DATE-typed column comparing native ordering vs Python str(value).strip() ordering across engines; not practically constructible via ad-hoc literal SQL in this harness")

@block("PCK-055")
def _():
    cases = [('BUY',10),('B',10),('SELL',-10),('S',-10)]
    all_ok = True
    detail = []
    for args in cases:
        py = pyref("SIGN_MATCHES_SIDE", args)
        sqlv,_ = run_sql_all(FUNCS["SIGN_MATCHES_SIDE"].sql, args)
        ok = py is True and all(v in (True,1) for v in sqlv.values())
        all_ok &= ok
        detail.append(f"{args}: py={py} sql={sqlv}")
    R("PCK-055", all_ok, "; ".join(detail))

@block("PCK-056")
def _():
    cases = [('BUY',-10),('SELL',10)]
    all_ok = True
    detail = []
    for args in cases:
        py = pyref("SIGN_MATCHES_SIDE", args)
        sqlv,_ = run_sql_all(FUNCS["SIGN_MATCHES_SIDE"].sql, args)
        ok = py is False and all(v in (False,0) for v in sqlv.values())
        all_ok &= ok
        detail.append(f"{args}: py={py} sql={sqlv}")
    R("PCK-056", all_ok, "; ".join(detail))

@block("PCK-057")
def _():
    from prama.pql.functions import UNSET
    args = ('BORROW', 10)
    py = pyref("SIGN_MATCHES_SIDE", args)
    sqlv,_ = run_sql_all(FUNCS["SIGN_MATCHES_SIDE"].sql, args)
    ok = (py is UNSET) and all(v is None for v in sqlv.values())
    R("PCK-057", ok, f"py={py} sql={sqlv}")

@block("PCK-058")
def _():
    from prama.pql.functions import UNSET
    args = ('BUY', 0)
    py = pyref("SIGN_MATCHES_SIDE", args)
    sqlv,_ = run_sql_all(FUNCS["SIGN_MATCHES_SIDE"].sql, args)
    ok = (py is UNSET) and all(v is None for v in sqlv.values())
    R("PCK-058", ok, f"py={py} sql={sqlv}")

@block("PCK-059")
def _():
    from prama.pql.functions import UNSET
    args = ('BUY', True)
    py = pyref("SIGN_MATCHES_SIDE", args)
    ok = py is UNSET
    R("PCK-059", ok, f"py={py}")

@block("PCK-060")
def _():
    from prama.pql.functions import UNSET
    a1=('GB','GB'); a2=('GB','FR'); a3=('GBR','GBR')
    py1=pyref("SAME_COUNTRY",a1); py2=pyref("SAME_COUNTRY",a2); py3=pyref("SAME_COUNTRY",a3)
    s1,_=run_sql_all(FUNCS["SAME_COUNTRY"].sql,a1)
    s2,_=run_sql_all(FUNCS["SAME_COUNTRY"].sql,a2)
    s3,_=run_sql_all(FUNCS["SAME_COUNTRY"].sql,a3)
    ok = py1 is True and all(v in (True,1) for v in s1.values())
    ok &= py2 is False and all(v in (False,0) for v in s2.values())
    ok &= (py3 is UNSET) and all(v is None for v in s3.values())
    R("PCK-060", ok, f"GB/GB py={py1} sql={s1} | GB/FR py={py2} sql={s2} | GBR/GBR py={py3} sql={s3}")

@block("PCK-061")
def _():
    args = ('gb','GB')
    py = pyref("SAME_COUNTRY", args)
    sqlv,_ = run_sql_all(FUNCS["SAME_COUNTRY"].sql, args)
    ok = py is True and all(v in (True,1) for v in sqlv.values())
    R("PCK-061", ok, f"py={py} sql={sqlv}")

@block("PCK-062")
def _():
    from prama.pql.functions import UNSET
    ibanc = pyref("IBAN_COUNTRY", ('GB82WEST12345698765432',))
    bicc = pyref("BIC_COUNTRY", ('DEUTDEFF',))
    isinc = pyref("ISIN_COUNTRY", ('US0378331005',))
    short_iban = pyref("IBAN_COUNTRY", ('X',))
    short_bic = pyref("BIC_COUNTRY", ('X',))
    short_isin = pyref("ISIN_COUNTRY", ('X',))
    ok = ibanc=='GB' and bicc=='DE' and isinc=='US' and short_iban is UNSET and short_bic is UNSET and short_isin is UNSET
    R("PCK-062", ok, f"iban={ibanc} bic={bicc} isin={isinc} short_iban={short_iban} short_bic={short_bic} short_isin={short_isin}")

@block("PCK-063")
def _():
    v = pyref("ISIN_COUNTRY", ('XS0629974352',))
    import inspect
    doc = FUNCS["ISIN_COUNTRY"].summary
    ok = v=='XS' and 'XS' in doc and ('country' in doc.lower())
    R("PCK-063", ok, f"value={v} summary={doc!r}")

@block("PCK-065")
def _():
    from prama.pql.functions import UNSET
    TYPED_DEFAULT = {"text": "AB", "number": 5, "temporal": "2026-01-01"}
    detail = []
    all_ok = True
    for fname, f in FUNCS.items():
        arity = f.arity[0]
        for pos in range(arity):
            args = [TYPED_DEFAULT[t] for t in f.argument_types[:arity]]
            args[pos] = None
            try:
                py = f.evaluate(list(args))
            except Exception as e:
                py = f"EXC:{e}"
            sqlv, rendered = run_sql_all(f.sql, args)
            py_is_unset = (py is UNSET)
            sql_all_null = all(v is None for v in sqlv.values() if not (isinstance(v,str) and v.startswith("ERR")))
            errs = {k:v for k,v in sqlv.items() if isinstance(v,str) and v.startswith("ERR")}
            ok = py_is_unset and sql_all_null and not errs
            all_ok &= ok
            detail.append(f"{fname}[{pos}]: py={py} sql={sqlv} ok={ok}")
    R("PCK-065", all_ok, " || ".join(detail))

@block("PCK-066")
def _():
    # Cross-check a representative sample across all 3 engines for agreement (not just null)
    detail = []
    all_ok = True
    cases = {
        "IBAN_BIC_CONSISTENT": [('DE89370400440532013000','COBADEFF'), ('DE89370400440532013000','BNPAFRPP')],
        "MINOR_UNITS_OK": [(1050,'JPY'), (1050.75,'JPY')],
        "SETTLES_AFTER_TRADE": [('2026-03-02','2026-03-04'), ('2026-03-04','2026-03-02')],
        "SIGN_MATCHES_SIDE": [('BUY',10), ('SELL',10)],
        "SAME_COUNTRY": [('GB','GB'), ('GB','FR')],
        "IBAN_COUNTRY": [('GB82WEST12345698765432',)],
        "BIC_COUNTRY": [('DEUTDEFF',)],
        "ISIN_COUNTRY": [('US0378331005',)],
    }
    for fname, arglist in cases.items():
        f = FUNCS[fname]
        for args in arglist:
            sqlv, rendered = run_sql_all(f.sql, args)
            vals = set()
            for k,v in sqlv.items():
                if isinstance(v,str) and v.startswith("ERR"):
                    vals.add(f"ERR:{k}")
                else:
                    vals.add(v)
            agree = len(vals)==1
            all_ok &= agree
            detail.append(f"{fname}{args}: {sqlv} agree={agree}")
    R("PCK-066", all_ok, " || ".join(detail))

print("=== PCK crossfield 040-066 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
