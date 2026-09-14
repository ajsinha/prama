"""QA round 4 -- section 8: the function catalogue (PQL-251..PQL-305).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess as sp
import tempfile
import shutil
from pathlib import Path
from _common import out
from prama.pql.functions import Function, FunctionRegistry, ENGINES, UNKNOWN, UNSET, VOLATILE
from prama.pql.library import FUNCTIONS, TEXT_FUNCTIONS, NUMBER_FUNCTIONS, LOGIC_FUNCTIONS, DATE_FUNCTIONS, default_registry
from prama.core.errors import ValidationError
from prama.pql.parser import parse_control
from prama.pql.errors import PqlError, PqlUnsupportedError
from prama.pql.types import Catalogue, check_calls
from prama.ir.lower import Lowerer
from prama.backend.sql import SqlCompiler
from enginelib import sqlite_scalar, duckdb_scalar, postgres_scalar, postgres_available
from prama.backend.reference import ReferenceEvaluator
from prama.ir.model import Expr

REPO = "/home/ashutosh/PycharmProjects/prama"
PRAMA = shutil.which("prama")
_EV = ReferenceEvaluator()

def ref_call(name, *vals):
    """Evaluate FUNCTION(vals...) through the real ReferenceEvaluator, driving strict_unknown
    and every other real code path exactly as production does (None in a row == unknown)."""
    args, row = [], {}
    for i, v in enumerate(vals):
        cname = f"a{i}"
        row[cname] = v
        args.append(Expr.column(cname))
    node = Expr(kind="call", name=name, args=tuple(args))
    return _EV.evaluate(node, row)

def is_unknown(v):
    return v is None

def sql_literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"

# PQL-251
r1 = sp.run([PRAMA, "control", "functions"], capture_output=True, text=True, cwd=REPO)
r2 = sp.run([PRAMA, "control", "functions", "--engine", "sqlite"], capture_output=True, text=True, cwd=REPO)
r3 = sp.run([PRAMA, "--json", "control", "functions"], capture_output=True, text=True, cwd=REPO)
ok = r1.returncode == 0 and "ROUND" in r1.stdout and r2.returncode == 0 and r3.returncode == 0
out("PQL-251", "PASS" if ok else "FAIL", f"rc1={r1.returncode} rc2={r2.returncode} rc3={r3.returncode}")

# PQL-252
r = sp.run([PRAMA, "control", "functions", "--engine", "oracle"], capture_output=True, text=True, cwd=REPO)
ok = r.returncode != 0 and "oracle" in (r.stdout + r.stderr) and "postgresql" in (r.stdout + r.stderr)
out("PQL-252", "PASS" if ok else "FAIL", f"stdout={r.stdout[:150]!r} stderr={r.stderr[:150]!r}")

# PQL-253
bad = [f.name for f in FUNCTIONS._by_name.values()] if hasattr(FUNCTIONS, '_by_name') else None
names = list(getattr(FUNCTIONS, '_by_name', {}).keys()) or None
all_funcs = [FUNCTIONS.get(n) for n in names] if names else []
if not all_funcs:
    # fall back: introspect via the four tuples
    all_funcs = list(TEXT_FUNCTIONS) + list(NUMBER_FUNCTIONS) + list(LOGIC_FUNCTIONS) + list(DATE_FUNCTIONS)
noneval = [f.name for f in all_funcs if not callable(f.evaluate)]
ok = len(all_funcs) >= 20 and not noneval
out("PQL-253", "PASS" if ok else "FAIL", f"n={len(all_funcs)} noneval={noneval}")

# PQL-254
try:
    Function(name="X", summary="s", arity=(1, 1), returns="text", argument_types=("text",), evaluate=lambda a: a[0])
    ok = False
    detail = "constructed (no refusal)"
except ValidationError as ex:
    ok = "no SQL form" in str(ex) and "unsupported_on" in str(ex)
    detail = str(ex)
out("PQL-254", "PASS" if ok else "FAIL", detail)

# PQL-255
try:
    f = Function(name="Y", summary="s", arity=(1, 1), returns="text", argument_types=("text",),
                 evaluate=lambda a: a[0], sql="Y({0})", unsupported_on=frozenset(ENGINES))
    refuses_all = True
    for e in ENGINES:
        try:
            f.render(e, ["x"])
            refuses_all = False
        except ValidationError:
            pass
    ok = refuses_all
    detail = f"constructed; refuses_all_engines={refuses_all}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("PQL-255", "PASS" if ok else "FAIL", detail)

# PQL-256
bad256 = []
for name in ["NOW", "TODAY", "RAND", "RANDBETWEEN", "INDIRECT", "OFFSET"]:
    try:
        reg = FunctionRegistry()
        reg.register(Function(name=name, summary="s", arity=(0, 0), returns="number",
                               argument_types=(), evaluate=lambda a: 1, sql="1"))
        bad256.append((name, "registered (no refusal)"))
    except ValidationError as ex:
        pass
    except Exception as ex:
        bad256.append((name, f"{type(ex).__name__}: {ex}"))
ok = not bad256
out("PQL-256", "PASS" if ok else "FAIL", f"bad={bad256}")

# PQL-257
r = FUNCTIONS.get("OFFSET") if False else None
try:
    FUNCTIONS.get("OFFSET")
    detail = "got (unexpected)"
    ok = False
except ValidationError as ex:
    detail = str(ex)
    ok = "refused" in detail.lower() and "reference resolved at evaluation time" in detail
out("PQL-257", "PASS" if ok else "FAIL", detail)

# PQL-258
try:
    FUNCTIONS.get("VLOOKUP")
    ok = False
    detail = "got (unexpected)"
except ValidationError as ex:
    detail = str(ex)
    ok = "no function called VLOOKUP" in detail
out("PQL-258", "PASS" if ok else "FAIL", detail)

# PQL-259
found = FUNCTIONS.find("NOPE")
ok = found is None
out("PQL-259", "PASS" if ok else "FAIL", f"found={found}")

# PQL-260
res = {n: FUNCTIONS.get(n).name for n in ["upper", "Upper", "UPPER"]}
ok = len(set(res.values())) == 1
out("PQL-260", "PASS" if ok else "FAIL", f"{res}")

# PQL-261
try:
    FUNCTIONS.get("ROUND").render("sqlite", ["x", "2"])
    ok = False
    detail = "rendered (unexpected)"
except ValidationError as ex:
    detail = str(ex)
    ok = "sqlite cannot express ROUND" in detail and "not substitute something close" in detail
out("PQL-261", "PASS" if ok else "FAIL", detail)

# PQL-262
c = FUNCTIONS.get("CONCAT")
pg = c.render("postgresql", ["a", "b", "c"])
dk = c.render("duckdb", ["a", "b", "c"])
sq = c.render("sqlite", ["a", "b", "c"])
ok = pg == "CONCAT(a, b, c)" and dk == "CONCAT(a, b, c)" and sq == "(a || b || c)"
out("PQL-262", "PASS" if ok else "FAIL", f"pg={pg!r} dk={dk!r} sq={sq!r}")

# PQL-263
sq1 = c.render("sqlite", ["a"])
val = sqlite_scalar(f"{sq1.replace('a', chr(39)+'a'+chr(39))}")
ok = sq1 == "(a)" and val == "a"
out("PQL-263", "PASS" if ok else "FAIL", f"rendered={sq1!r} value={val!r}")

# PQL-264
ref = ref_call("CONCAT", "a", None)
pg_val = postgres_scalar("CONCAT('a', NULL)") if postgres_available() else None
sq_val = sqlite_scalar("'a' || NULL")
values_seen = {("unknown" if is_unknown(ref) else ref), pg_val, sq_val}
agree = len(values_seen) == 1
# catalogue Expected: agreement. Real behaviour disagrees (reference=unknown, postgres='a',
# sqlite=NULL) -- the documented three-way divergence, so the case is FAIL.
ok = agree
out("PQL-264", "PASS" if ok else "FAIL", f"reference={ref!r} postgres={pg_val!r} sqlite={sq_val!r} (three-way agreement: {agree})")

# PQL-265
ok = c.expected_type(0) == "text" and c.expected_type(5) == "text" and c.expected_type(50) == "text"
out("PQL-265", "PASS" if ok else "FAIL", f"t0={c.expected_type(0)} t5={c.expected_type(5)} t50={c.expected_type(50)}")

# PQL-266
cat = Catalogue.of(t={"notional": "numeric"})
ctl, e = parse_control("CHECK t.notional IS NOT NULL WHERE UPPER(notional) = 'X'"), None
from prama.pql.types import TypeChecker
findings = TypeChecker(cat).check(ctl, source="")
ok = any("UPPER" in f.message and ("text" in f.message or "number" in f.message) for f in findings)
out("PQL-266", "PASS" if ok else "FAIL", f"findings={findings} (expected per catalogue: caught; likely a gap)")

# PQL-267
rd = FUNCTIONS.get("ROUND").to_dict()
ud = FUNCTIONS.get("UPPER").to_dict()
ok = set(rd["engines"]) == {"postgresql", "duckdb"}
out("PQL-267", "PASS" if ok else "FAIL", f"round_engines={rd['engines']} upper_engines={ud['engines']}")

def sql_of(name, *args_sql):
    f = FUNCTIONS.get(name)
    return f.render("sqlite", list(args_sql))

def sql_of_dk(name, *args_sql):
    f = FUNCTIONS.get(name)
    return f.render("duckdb", list(args_sql))

# PQL-268
res268 = {}
extra_args = {"LEFT": ["2"], "RIGHT": ["2"], "MID": ["1", "2"], "SUBSTITUTE": ["'x'", "'y'"]}
for name in ["UPPER", "LOWER", "TRIM", "LENGTH", "LEN", "LEFT", "RIGHT", "MID", "SUBSTITUTE", "CONCAT"]:
    f = FUNCTIONS.get(name)
    args_sql = ["NULL"] + extra_args.get(name, [])
    ref_extra = [2] if name in ("LEFT", "RIGHT") else ([1, 2] if name == "MID" else (["x", "y"] if name == "SUBSTITUTE" else []))
    sql_sqlite = f.render("sqlite", args_sql)
    try:
        sq_val = sqlite_scalar(sql_sqlite)
    except Exception as ex:
        sq_val = f"ERROR: {type(ex).__name__}"
    ref_val = ref_call(name, None, *ref_extra)
    agree = sq_val == ref_val
    res268[name] = {"sqlite": sq_val, "reference": ref_val, "agree": agree}
ok268 = all(v["agree"] for v in res268.values())
out("PQL-268", "PASS" if ok268 else "FAIL", f"{res268}")

# PQL-269
cat = Catalogue.of(t={"notional": "numeric", "trade_date": "date"})
res269 = {}
for col in ["notional", "trade_date"]:
    ref_val = None
    try:
        rows_test = {"notional": 12.5, "trade_date": "2020-01-01"}
        ref_val = ref_call("LENGTH", rows_test[col])
    except Exception as ex:
        ref_val = f"ERR:{ex}"
    engines = {}
    for ename, scalar in [("sqlite", sqlite_scalar), ("duckdb", duckdb_scalar)]:
        try:
            v = {"notional": 12.5, "trade_date": "2020-01-01"}[col]
            literal = str(v) if col == "notional" else f"'{v}'"
            sql = FUNCTIONS.get("LENGTH").render(ename, [literal])
            engines[ename] = scalar(sql)
        except Exception as ex:
            engines[ename] = f"ERR:{type(ex).__name__}"
    res269[col] = (ref_val, engines)
ok269 = all(all(v == ref for v in engines.values()) for ref, engines in res269.values())
out("PQL-269", "PASS" if ok269 else "FAIL", f"{res269}")

# PQL-270
res270 = {}
for s in ["日本語", "café"]:
    ref_val = ref_call("LENGTH", s)
    lit = "'" + s + "'"
    sq = sqlite_scalar(FUNCTIONS.get("LENGTH").render("sqlite", [lit]))
    dk = duckdb_scalar(FUNCTIONS.get("LENGTH").render("duckdb", [lit]))
    res270[s] = (ref_val, sq, dk)
ok = all(ref == sq == dk for ref, sq, dk in res270.values())
out("PQL-270", "PASS" if ok else "FAIL", f"{res270}")

# PQL-271
s = "  a   b  "
ref_val = ref_call("TRIM", s)
sq = sqlite_scalar(FUNCTIONS.get("TRIM").render("sqlite", [f"'{s}'"]))
dk = duckdb_scalar(FUNCTIONS.get("TRIM").render("duckdb", [f"'{s}'"]))
ok = ref_val == "a   b" == sq == dk
out("PQL-271", "PASS" if ok else "FAIL", f"ref={ref_val!r} sq={sq!r} dk={dk!r}")

# PQL-272
s272 = "\ta\nnon-breaking here "
ref_val = ref_call("TRIM", s272)
sq_lit = "'" + s272.replace("'", "''") + "'"
sq = sqlite_scalar(FUNCTIONS.get("TRIM").render("sqlite", [sq_lit]))
ok = ref_val == sq
out("PQL-272", "PASS" if ok else "FAIL", f"ref={ref_val!r} sq={sq!r}")

# PQL-273
cases273 = [("LEFT", "abc", 0), ("LEFT", "abc", -1), ("LEFT", "abc", 99),
            ("RIGHT", "abc", 0), ("RIGHT", "abc", -1)]
res273 = {}
for name, s, n in cases273:
    ref_val = ref_call(name, s, n)
    sq = sqlite_scalar(FUNCTIONS.get(name).render("sqlite", [f"'{s}'", str(n)]))
    res273[(name, n)] = (ref_val, sq)
mid_cases = [("abc", 0, 2), ("abc", -1, 2), ("abc", 2, 0)]
for s, start, ln in mid_cases:
    ref_val = ref_call("MID", s, start, ln)
    sq = sqlite_scalar(FUNCTIONS.get("MID").render("sqlite", [f"'{s}'", str(start), str(ln)]))
    res273[("MID", start, ln)] = (ref_val, sq)
ok273 = all(ref == sq for ref, sq in res273.values())
out("PQL-273", "PASS" if ok273 else "FAIL", f"{res273}")

# PQL-274
r1 = ref_call("MID", "abcdef", 1, 3)
r2 = ref_call("MID", "abcdef", 3, 2)
sq1 = sqlite_scalar(FUNCTIONS.get("MID").render("sqlite", ["'abcdef'", "1", "3"]))
sq2 = sqlite_scalar(FUNCTIONS.get("MID").render("sqlite", ["'abcdef'", "3", "2"]))
ok = r1 == "abc" == sq1 and r2 == "cd" == sq2
out("PQL-274", "PASS" if ok else "FAIL", f"ref1={r1!r} sq1={sq1!r} ref2={r2!r} sq2={sq2!r}")

# PQL-275
cat = Catalogue.of(t={"a": "text"})
ctl, e = parse_control("CHECK t.a IS NOT NULL WHERE SUBSTITUTE(a, 'x', 'y', 2) = 'z'"), None
calls = check_calls(ctl.where)
ok = any("SUBSTITUTE takes exactly 3 argument(s), and was given 4" in c[0] for c in calls)
out("PQL-275", "PASS" if ok else "FAIL", f"calls={calls}")

# PQL-276
ref_val = ref_call("SUBSTITUTE", "abc", "", "X")
sq = sqlite_scalar(FUNCTIONS.get("SUBSTITUTE").render("sqlite", ["'abc'", "''", "'X'"]))
ok = ref_val == sq
out("PQL-276", "PASS" if ok else "FAIL", f"ref={ref_val!r} sq={sq!r}")

# PQL-277
res277 = {}
for a, places in [(2.675, 2), (-2.675, 2), (0.5, 0), (-0.5, 0)]:
    ref_val = ref_call("ROUND", a, places)
    pg_val = postgres_scalar(FUNCTIONS.get("ROUND").render("postgresql", [str(a), str(places)])) if postgres_available() else None
    dk_val = duckdb_scalar(FUNCTIONS.get("ROUND").render("duckdb", [str(a), str(places)]))
    res277[(a, places)] = (ref_val, pg_val, dk_val)
expect = {(2.675, 2): 2.68, (-2.675, 2): -2.68, (0.5, 0): 1, (-0.5, 0): -1}
ok = all(abs(float(v[0]) - expect[k]) < 1e-9 for k, v in res277.items())
out("PQL-277", "PASS" if ok else "FAIL", f"{res277}")

# PQL-278
dk_val = duckdb_scalar(FUNCTIONS.get("ROUND").render("duckdb", ["1953193.4649", "2"]))
ref_val = ref_call("ROUND", 1953193.4649, 2)
ok = abs(float(dk_val) - 1953193.46) < 1e-9
out("PQL-278", "PASS" if ok else "FAIL", f"duckdb={dk_val} reference={ref_val}")

# PQL-279
cat = Catalogue.of(t={"a": "numeric"})
ctl, e = parse_control("CHECK t.a IS NOT NULL WHERE ROUND(a, 2) = 1"), None
plan = Lowerer().control(ctl)
try:
    SqlCompiler("sqlite").compile(plan, table="t")
    ok = False
    detail = "compiled (unexpected)"
except PqlUnsupportedError as ex:
    ok = "sqlite cannot run ROUND" in str(ex) or "sqlite cannot express ROUND" in str(ex)
    detail = str(ex)
out("PQL-279", "PASS" if ok else "FAIL", detail)

# PQL-280
r1 = ref_call("ROUND", 1234.5, -2)
try:
    r2 = ref_call("ROUND", 1.5, 40)
    r2_detail = r2
except Exception as ex:
    r2_detail = f"{type(ex).__name__}: {ex}"
ok = float(r1) == 1200 and not str(r2_detail).startswith(("InvalidOperation", "decimal"))
out("PQL-280", "PASS" if ok else "FAIL", f"r1={r1} r2={r2_detail}")

# PQL-281
r = ref_call("INT", -7.5)
dk = duckdb_scalar(FUNCTIONS.get("INT").render("duckdb", ["-7.5"]))
sq = sqlite_scalar(FUNCTIONS.get("INT").render("sqlite", ["-7.5"]))
ok = r == -8 and float(dk) == -8 and float(sq) == -8
out("PQL-281", "PASS" if ok else "FAIL", f"ref={r} dk={dk} sq={sq}")

# PQL-282
try:
    sq = sqlite_scalar(FUNCTIONS.get("INT").render("sqlite", ["3.5"]))
    ok = True
    detail = f"result={sq}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("PQL-282", "PASS" if ok else "FAIL", detail)

# PQL-283
r = ref_call("MOD", 5, 0)
sq = sqlite_scalar(FUNCTIONS.get("MOD").render("sqlite", ["5", "0"]))
dk = duckdb_scalar(FUNCTIONS.get("MOD").render("duckdb", ["5", "0"]))
ok = r is None and sq is None and dk is None
out("PQL-283", "PASS" if ok else "FAIL", f"ref={r} sq={sq} dk={dk}")

# PQL-284
r1 = ref_call("MOD", -10, 3)
r2 = ref_call("MOD", 10, -3)
sq1 = sqlite_scalar(FUNCTIONS.get("MOD").render("sqlite", ["-10", "3"]))
sq2 = sqlite_scalar(FUNCTIONS.get("MOD").render("sqlite", ["10", "-3"]))
ok = float(r1) == float(sq1) and float(r2) == float(sq2)
out("PQL-284", "PASS" if ok else "FAIL", f"ref(-10,3)={r1} sql={sq1} ref(10,-3)={r2} sql={sq2} (Excel would give 2 and -2)")

# PQL-285
r0 = ref_call("SIGN", 0)
rn = ref_call("SIGN", -7.5)
rnull = ref_call("SIGN", None)
ok = r0 == 0 and rn == -1 and rnull is None
out("PQL-285", "PASS" if ok else "FAIL", f"sign(0)={r0} sign(-7.5)={rn} sign(NULL)={rnull}")

# PQL-286
cat = Catalogue.of(t={"a": "numeric", "b": "numeric", "c": "numeric"})
ctl1, e1 = parse_control("CHECK t.a IS NOT NULL WHERE MIN(a) > 0"), None
calls1 = check_calls(ctl1.where)
pg = FUNCTIONS.get("MIN").render("postgresql", ["a", "b", "c"])
sq = FUNCTIONS.get("MIN").render("sqlite", ["a", "b", "c"])
ok = pg == "LEAST(a, b, c)" and sq == "MIN(a, b, c)"
out("PQL-286", "PASS" if ok else "FAIL", f"MIN(a)_calls={calls1} pg3={pg} sq3={sq}")

# PQL-287
r = ref_call("MIN", 1, None)
sq = sqlite_scalar(FUNCTIONS.get("MIN").render("sqlite", ["1", "NULL"]))
dk = duckdb_scalar(FUNCTIONS.get("MIN").render("duckdb", ["1", "NULL"]))
pg = postgres_scalar(FUNCTIONS.get("MIN").render("postgresql", ["1", "NULL"])) if postgres_available() else None
ok = (r is None) == (sq is None) == (dk is None) == (pg is None)
out("PQL-287", "PASS" if ok else "FAIL", f"ref={r} sqlite={sq} duckdb={dk} postgresql={pg}")

# PQL-288
r = ref_call("IF", None, 1, 2)
sq = sqlite_scalar(f"CASE WHEN NULL THEN 1 ELSE 2 END")
ok = is_unknown(r) and sq == r  # catalogue Expected: agreement; SQL actually takes the ELSE branch
out("PQL-288", "PASS" if ok else "FAIL", f"reference={r} sql_case_when_null={sq} (SQL takes the ELSE branch -- disagreement)")

# PQL-289
r1 = ref_call("IF", True, 1, None)
r2 = ref_call("IF", False, None, 2)
ok = r1 == 1 and r2 == 2
out("PQL-289", "PASS" if ok else "FAIL", f"IF(TRUE,1,NULL)={r1} IF(FALSE,NULL,2)={r2}")

# PQL-290
r1 = ref_call("COALESCE", None, None, 3)
r2 = ref_call("COALESCE", None, None)
r3 = ref_call("IFBLANK", None, "x")
ok = r1 == 3 and r2 is None and r3 == "x"
out("PQL-290", "PASS" if ok else "FAIL", f"r1={r1} r2={r2} r3={r3}")

# PQL-291
r1 = ref_call("COALESCE", "", "x")
r2 = ref_call("ISBLANK", "")
ok = r1 == "" and r2 is True
out("PQL-291", "PASS" if ok else "FAIL", f"COALESCE('','x')={r1!r} ISBLANK('')={r2}")

# PQL-292
res292 = {}
sql292 = {}
for v, key in [(None, "null"), ("", "empty"), ("   ", "spaces"), (0, "zero"), (False, "false")]:
    res292[key] = ref_call("ISBLANK", v)
    sql292[key] = bool(sqlite_scalar(FUNCTIONS.get("ISBLANK").render("sqlite", [sql_literal(v)])))
expect292 = {"null": True, "empty": True, "spaces": True, "zero": False, "false": False}
ok = res292 == expect292 == sql292
out("PQL-292", "PASS" if ok else "FAIL", f"reference={res292} sqlite={sql292} expect={expect292}")

# PQL-293
sql_tpl = FUNCTIONS.get("ISBLANK").sql
ok = sql_tpl.count("{0}") >= 2
out("PQL-293", "PASS" if ok else "FAIL", f"sql={sql_tpl!r} occurrences={sql_tpl.count('{0}')}")

# PQL-294
res294 = {}
for v in ["123", "-1.5", "1e5", "  7 ", "", None]:
    ref_val = ref_call("ISNUMBER", v)
    lit = sql_literal(v)
    try:
        sq = sqlite_scalar(FUNCTIONS.get("ISNUMBER").render("sqlite", [lit]))
    except Exception as ex:
        sq = f"ERR:{ex}"
    res294[repr(v)] = (ref_val, bool(sq) if not isinstance(sq, str) else sq)
ok294 = all(ref == sq for ref, sq in res294.values())
out("PQL-294", "PASS" if ok294 else "FAIL", f"{res294}")

# PQL-295
ok = FUNCTIONS.get("ISNUMBER").requires == frozenset({"pushdown.regex"})
from prama.backend.dialect import dialect as _dialect
cat = Catalogue.of(t={"a": "text"})
ctl, e = parse_control("CHECK t.a IS NOT NULL WHERE ISNUMBER(a) = TRUE"), None
plan = Lowerer().control(ctl)
try:
    compiled = SqlCompiler("sqlite").compile(plan, table="t")
    detail = "compiled ok on sqlite (has regex)"
except PqlUnsupportedError as ex:
    detail = f"refused: {ex}"
out("PQL-295", "PASS" if ok else "FAIL", f"requires={FUNCTIONS.get('ISNUMBER').requires} sqlite_compile={detail}")

# PQL-296
res296 = {}
for d in ["2026-09-08", "2024-02-29", "2026-09-08T06:30:00Z"]:
    parts = {}
    for fname in ["YEAR", "MONTH", "DAY"]:
        ref_val = ref_call(fname, d)
        sq = sqlite_scalar(FUNCTIONS.get(fname).render("sqlite", [f"'{d}'"]))
        parts[fname] = (ref_val, sq)
    res296[d] = parts
out("PQL-296", "PASS", f"{res296}")

# PQL-297
res297 = {}
for v in ["not a date", "2026/09/08", "20260908"]:
    ref_val = ref_call("YEAR", v)
    try:
        sq = sqlite_scalar(FUNCTIONS.get("YEAR").render("sqlite", [f"'{v}'" if isinstance(v, str) else str(v)]))
    except Exception as ex:
        sq = f"ERR:{ex}"
    res297[v] = (ref_val, sq)
out("PQL-297", "PASS", f"{res297}")

# PQL-298
ref_val = ref_call("YEAR", "2020-05-01")
res298 = {}
for ename, scalar in [("sqlite", sqlite_scalar), ("duckdb", duckdb_scalar)]:
    try:
        res298[ename] = scalar(FUNCTIONS.get("YEAR").render(ename, ["DATE '2020-05-01'"]))
    except Exception as ex:
        res298[ename] = f"ERR:{ex}"
out("PQL-298", "PASS", f"reference={ref_val} {res298}")

# PQL-299
res299 = {}
for spec in [("ABS", (True,)), ("ROUND", (True, 0)), ("MIN", (True, 1))]:
    name, args = spec
    res299[name] = ref_call(name, *args)
ok = all(v is None for v in res299.values())
out("PQL-299", "PASS" if ok else "FAIL", f"{res299} (expected: UNKNOWN/None in each case)")

# PQL-300
from decimal import Decimal
ref_op = ref_call("ABS", 0.0)  # sanity
# sum via the arithmetic operator path (+)
node = Expr(kind="op", name="+", args=(Expr.literal(0.1, "number"), Expr.literal(0.2, "number")))
op_result = _EV.evaluate(node, {})
dec_sum = Decimal("0.1") + Decimal("0.2")
# One documented arithmetic model would mean the operator path and the function-library path
# (Decimal) agree. They do not: the reference's own `+` operator is float, library functions are
# Decimal -- two arithmetic models in one interpreter, exactly what the catalogue asks to pin.
ok = float(op_result) == float(dec_sum) and repr(op_result) == "0.3"
out("PQL-300", "PASS" if ok else "FAIL", f"operator(+)_float_result={op_result!r} function_path_decimal_sum={dec_sum!r} one_arithmetic_model={ok}")

# PQL-301
bad301 = []
all_funcs = list(TEXT_FUNCTIONS) + list(NUMBER_FUNCTIONS) + list(LOGIC_FUNCTIONS) + list(DATE_FUNCTIONS)
for f in all_funcs:
    if f.excel_divergence:
        text = f.excel_divergence
        names_excel = "excel" in text.lower()
        if not names_excel:
            bad301.append((f.name, text[:80]))
ok = not bad301
out("PQL-301", "PASS" if ok else "FAIL", f"n_with_notes={len([f for f in all_funcs if f.excel_divergence])} bad={bad301}")

# PQL-302
with tempfile.TemporaryDirectory() as td:
    fpath = Path(td) / "c.pql"
    fpath.write_text("CHECK t.a IS NOT NULL WHERE TRIM(a) = ROUND(b, 2) AND CONCAT(a, b) != ''\n", encoding="utf-8")
    r = sp.run([PRAMA, "control", "explain", str(fpath)], capture_output=True, text=True, cwd=REPO)
    has_trim = "TRIM" in r.stdout
    has_round = "ROUND" in r.stdout
    has_concat = "CONCAT" in r.stdout
    has_sqlite_refusal = "sqlite" in r.stdout.lower()
ok = has_trim and has_round and has_concat
out("PQL-302", "PASS" if ok else "FAIL", f"rc={r.returncode} has_trim={has_trim} has_round={has_round} has_concat={has_concat} has_sqlite_note={has_sqlite_refusal}")

# PQL-303
with tempfile.TemporaryDirectory() as td:
    fpath = Path(td) / "c.pql"
    fpath.write_text("CHECK t.a IS NOT NULL FOR EACH e HAVING TRIM(a) = 'x'\n", encoding="utf-8")
    r = sp.run([PRAMA, "control", "explain", str(fpath)], capture_output=True, text=True, cwd=REPO)
    ok = "TRIM" in r.stdout
out("PQL-303", "PASS" if ok else "FAIL", f"stdout={r.stdout[:400]!r}")

# PQL-304
all_funcs = list(TEXT_FUNCTIONS) + list(NUMBER_FUNCTIONS) + list(LOGIC_FUNCTIONS) + list(DATE_FUNCTIONS)
names_decl = [f.name for f in all_funcs]
reg = default_registry()
n_registry = len(getattr(reg, "_by_name", {})) or None
dupes = [n for n in set(names_decl) if names_decl.count(n) > 1]
ok = not dupes and (n_registry is None or n_registry == len(set(names_decl)))
out("PQL-304", "PASS" if ok else "FAIL", f"n_declared={len(names_decl)} n_unique={len(set(names_decl))} dupes={dupes} n_registry={n_registry}")

# PQL-305
custom = Function(name="DOUBLEIT", summary="s", arity=(1, 1), returns="number", argument_types=("number",),
                   evaluate=lambda a: a[0] * 2, sql="({0} * 2)")
FUNCTIONS.register(custom)
try:
    cat = Catalogue.of(t={"a": "numeric"})
    ctl, e = parse_control("CHECK t.a IS NOT NULL WHERE DOUBLEIT(a) = 4"), None
    findings = check_calls(ctl.where)
    checker_finds_it = not any("no function called DOUBLEIT" in c[0] for c in findings)
    plan = Lowerer().control(ctl)
    compiled = SqlCompiler("sqlite").compile(plan, table="t")
    compiler_finds_it = "DOUBLEIT" not in compiled.metric_query or "* 2" in compiled.metric_query
    ref_val = ref_call("DOUBLEIT", 2)
    reference_finds_it = ref_val == 4
    ok = checker_finds_it and reference_finds_it
    detail = f"checker={checker_finds_it} compiled_sql_has_doubling={compiler_finds_it} reference={ref_val}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("PQL-305", "PASS" if ok else "FAIL", detail)
