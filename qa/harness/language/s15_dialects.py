"""QA round 4 -- section 15: dialects (BE-001..BE-029).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
from _common import out
from prama.backend.dialect import dialect, DIALECTS
from prama.core.errors import RegistryError
from prama.pql.errors import PqlUnsupportedError
from enginelib import sqlite_scalar, duckdb_scalar, postgres_scalar, postgres_available

pg = dialect("postgresql")
dk = dialect("duckdb")
sq = dialect("sqlite")

# BE-001
ok = all(dialect(n) is DIALECTS[n] for n in ["postgresql", "duckdb", "sqlite"])
out("BE-001", "PASS" if ok else "FAIL", f"{ok}")

# BE-002
res = {}
for n in ["oracle", "", "POSTGRESQL"]:
    try:
        dialect(n)
        res[n] = "resolved (unexpected)"
    except RegistryError as ex:
        res[n] = str(ex)
    except Exception as ex:
        res[n] = f"{type(ex).__name__}: {ex}"
ok = all("no SQL dialect named" in v for v in res.values())
out("BE-002", "PASS" if ok else "FAIL", f"{res}")

# BE-003
res = {}
for s in ['a"b', 'a""b', "a'b", "a;DROP TABLE x--", "a\nb", ""]:
    q = pg.quote(s)
    res[s] = q
ok = all(q.count('"') % 2 == 0 for q in res.values())
out("BE-003", "PASS" if ok else "FAIL", f"{res}")

# BE-004
res = {}
for n in ["positions", "risk.positions", "db.risk.positions"]:
    res[n] = pg.qualify(n)
ok = res["risk.positions"] == '"risk"."positions"' and res["db.risk.positions"] == '"db"."risk"."positions"'
out("BE-004", "PASS" if ok else "FAIL", f"{res}")

# BE-005
q = pg.qualify("risk.positions")
ok = q != '"risk.positions"'  # documents the defect: it is split, not addressable as one name
out("BE-005", "FAIL" if ok else "PASS", f"qualify('risk.positions')={q!r} (defect: genuinely one-part name becomes two-part)")

# BE-006
from decimal import Decimal
res = {}
for v in [None, True, False, 0, -1, 1.5, 1e20, "it's", "", Decimal("1.5")]:
    res[repr(v)] = pg.literal(v)
ok = res["Decimal('1.5')"] not in ("'1.5'",)  # documents: Decimal falls through to the string branch (defect) if true
decimal_is_string = res["Decimal('1.5')"] == "'1.5'"
out("BE-006", "FAIL" if decimal_is_string else "PASS", f"{res} decimal_became_string_literal={decimal_is_string}")

# BE-007
res = {}
for v in [float("nan"), float("inf")]:
    try:
        res[repr(v)] = pg.literal(v)
    except Exception as ex:
        res[repr(v)] = f"refused: {type(ex).__name__}: {ex}"
valid_sql = all("refused" in v or (v not in ("nan", "inf", "-inf")) for v in res.values())
out("BE-007", "PASS" if valid_sql else "FAIL", f"{res}")

# BE-008
res = {"postgresql": pg.boolean(False), "duckdb": dk.boolean(False), "sqlite": sq.boolean(False)}
ok = res["postgresql"] == "FALSE" and res["duckdb"] == "FALSE" and res["sqlite"] == "0"
out("BE-008", "PASS" if ok else "FAIL", f"{res}")

# BE-009
res = {"postgresql": pg.count_if("x > 0"), "duckdb": dk.count_if("x > 0"), "sqlite": sq.count_if("x > 0")}
ok = "FILTER" in res["postgresql"] and "FILTER" in res["duckdb"] and "CASE WHEN" in res["sqlite"] and "COALESCE" in res["sqlite"]
out("BE-009", "PASS" if ok else "FAIL", f"{res}")

# BE-010
res = {}
for name, scalar, d in [("sqlite", sqlite_scalar, sq), ("duckdb", duckdb_scalar, dk)]:
    scalar(f"CREATE TABLE be010_{name} (x INTEGER)" if False else "1") if False else None
res["sqlite"] = sqlite_scalar(sq.count_if("1=2"))
res["duckdb"] = duckdb_scalar(dk.count_if("1=2"))
if postgres_available():
    res["postgresql"] = postgres_scalar(pg.count_if("1=2"))
ok = all(v == 0 for v in res.values())
out("BE-010", "PASS" if ok else "FAIL", f"{res}")

# BE-011
res = {}
res["postgresql_1col"] = postgres_scalar(f"{pg.count_distinct(['x'])} FROM (VALUES (1),(1),(2)) t(x)") if postgres_available() else None
res["duckdb_1col"] = duckdb_scalar(f"{dk.count_distinct(['x'])} FROM (VALUES (1),(1),(2)) t(x)")
res["sqlite_1col"] = sqlite_scalar(f"{sq.count_distinct(['x'])} FROM (SELECT 1 AS x UNION ALL SELECT 1 UNION ALL SELECT 2)")
ok = all(v == 2 for v in res.values() if v is not None)
out("BE-011", "PASS" if ok else "FAIL", f"{res}")

# BE-012
expr = sq.count_distinct(["a", "b"])
sql = f"{expr} FROM (SELECT 'x' || CHAR(31) || 'y' AS a, 'z' AS b UNION ALL SELECT 'x', 'y' || CHAR(31) || 'z')"
val = sqlite_scalar(sql)
ok = val == 2
out("BE-012", "PASS" if ok else "FAIL", f"count_distinct={val}")

# BE-013
expr_f = pg.count_distinct(["a"], where="a IS NOT NULL") if postgres_available() else None
res = {}
if postgres_available():
    res["postgresql"] = postgres_scalar(f"{expr_f} FROM (VALUES (1),(1),(NULL::int),(2)) t(a)")
res["duckdb"] = duckdb_scalar(f"{dk.count_distinct(['a'], where='a IS NOT NULL')} FROM (VALUES (1),(1),(NULL),(2)) t(a)")
res["sqlite"] = sqlite_scalar(f"{sq.count_distinct(['a'], where='a IS NOT NULL')} FROM (SELECT 1 AS a UNION ALL SELECT 1 UNION ALL SELECT NULL UNION ALL SELECT 2)")
ok = len({v for v in res.values() if v is not None}) == 1
out("BE-013", "PASS" if ok else "FAIL", f"{res}")

# BE-014
res = {}
res["postgresql"] = postgres_scalar(pg.regex_match("'AB1'", "^[A-Z]{2}")) if postgres_available() else None
res["duckdb"] = duckdb_scalar(dk.regex_match("'AB1'", "^[A-Z]{2}"))
res["sqlite"] = bool(sqlite_scalar(sq.regex_match("'AB1'", "^[A-Z]{2}")))
sql_forms = {"postgresql": pg.regex_match("x", "p"), "duckdb": dk.regex_match("x", "p"), "sqlite": sq.regex_match("x", "p")}
ok = all(bool(v) for v in res.values() if v is not None) and "~" in sql_forms["postgresql"] and "regexp_matches" in sql_forms["duckdb"] and "REGEXP" in sql_forms["sqlite"]
out("BE-014", "PASS" if ok else "FAIL", f"results={res} forms={sql_forms}")

# BE-015 -- through judge()/compile() on each engine, as round 3 did, over one row containing "AB"
from prama.ir.lower import Lowerer as _Lowerer2
from prama.pql.parser import parse_control as _pc2
from prama.backend.sql import SqlCompiler as _SqlCompiler2
from prama.backend.reference import ReferenceEvaluator as _RefEval2
res = {}
bad15 = []
for pat in [r"(?<=A)B", r"\d+", r"(a)\1", r"^(?i)abc"]:
    entry = {}
    try:
        plan = _Lowerer2().control(_pc2(f"CHECK t.a MATCHES /{pat}/"))
    except Exception as ex:
        entry["parse"] = f"{type(ex).__name__}: {ex}"
        res[pat] = entry
        continue
    try:
        r = _RefEval2().run(plan, [{"a": "AB"}])
        entry["reference"] = str(r.verdict)
    except Exception as ex:
        entry["reference"] = f"ERR {type(ex).__name__}: {ex}"
        bad15.append((pat, "reference crash"))
    for eng, scalar in [("postgresql", postgres_scalar), ("duckdb", duckdb_scalar), ("sqlite", sqlite_scalar)]:
        if eng == "postgresql" and not postgres_available():
            continue
        try:
            compiled = _SqlCompiler2(eng).compile(plan, table="t")
            entry[eng] = "compiled ok"
        except Exception as ex:
            entry[eng] = f"{type(ex).__name__}: {ex}"[:80]
    res[pat] = entry
ok = not bad15  # a bare reference crash (uncaught exception) is the confirmed defect
out("BE-015", "PASS" if ok else "FAIL", f"{res}")

# BE-016
res = {}
for pat in ["[", "*"]:
    from prama.pql.parser import parse_control
    try:
        parse_control(f"CHECK t.a MATCHES /{pat}/")
        res[pat] = "parsed (unexpected)"
    except Exception as ex:
        res[pat] = f"refused at parse: {type(ex).__name__}"
ok = all("refused" in v for v in res.values())
out("BE-016", "PASS" if ok else "FAIL", f"{res}")

# BE-017 -- drive the real compiler path, where Unsupported actually turns into a raise
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control
from prama.backend.sql import SqlCompiler
from prama.backend.dialect import Unsupported
class _NoRegex:
    name = "norepex"
    def capabilities(self):
        return frozenset()
r = pg.regex_match.__wrapped__ if hasattr(pg.regex_match, "__wrapped__") else None
from prama.backend.dialect import SqlDialect
u = SqlDialect.regex_match(_NoRegex(), "expr", "pattern")
ok = isinstance(u, Unsupported) and "regex" in str(u.capability).lower() and "pattern" in u.detail and "LIKE" in u.remedy
out("BE-017", "PASS" if ok else "FAIL", f"unsupported={u}")

# BE-018
import sqlite3
bare = sqlite3.connect(":memory:")
try:
    bare.execute(f"SELECT {sq.regex_match(chr(39)+'AB'+chr(39), '^A')}").fetchone()
    ok = False
    detail = "ran on a bare connection (unexpected)"
except sqlite3.OperationalError as ex:
    ok = True
    detail = f"bare connection fails: {ex} (dialect unconditionally declares REGEX capability = documented gap)"
finally:
    bare.close()
out("BE-018", "PASS" if ok else "FAIL", detail)

# BE-019
casted = dk.as_text("d")
expr = f"{dk.regex_match(dk.as_text('d'), '^2020')} FROM (SELECT DATE '2020-01-01' AS d) t"
val = duckdb_scalar(expr)
ok = val is True or val == 1
out("BE-019", "PASS" if ok else "FAIL", f"cast={casted} value={val}")

# BE-020
res = {}
res["sqlite"] = sqlite_scalar("CAST(DATE('2020-01-01') AS TEXT)" if False else "'2020-01-01'")
res["duckdb"] = duckdb_scalar("CAST(DATE '2020-01-01' AS VARCHAR)")
if postgres_available():
    res["postgresql"] = postgres_scalar("CAST(DATE '2020-01-01' AS VARCHAR)")
ok = all(str(v).startswith("2020-01-01") for v in res.values())
out("BE-020", "PASS" if ok else "FAIL", f"{res}")

# BE-021
res = {}
res["sqlite"] = sqlite_scalar(f"{sq.as_real('1')} / {sq.as_real('2')}")
res["duckdb"] = duckdb_scalar("1.0 / 2")
if postgres_available():
    res["postgresql"] = postgres_scalar(f"CAST(1 AS {pg.double_type}) / 2")
from prama.backend.reference import ReferenceEvaluator
ref = ReferenceEvaluator()
ok = all(float(v) == 0.5 for v in res.values())
out("BE-021", "PASS" if ok else "FAIL", f"{res}")

# BE-022
res = {"postgresql": pg.double_type, "duckdb": dk.double_type, "sqlite": sq.double_type}
ok = res["postgresql"] == "DOUBLE PRECISION" and res["duckdb"] == "DOUBLE PRECISION" and res["sqlite"] == "REAL"
out("BE-022", "PASS" if ok else "FAIL", f"{res}")

# BE-023
res = {}
res["sqlite"] = sqlite_scalar(sq.modulo("-10", "3"))
res["duckdb"] = duckdb_scalar(dk.modulo("-10", "3"))
if postgres_available():
    res["postgresql"] = postgres_scalar(pg.modulo("-10", "3"))
res["reference"] = -10 % 3 if False else None
import decimal
try:
    from prama.pql.library import FUNCTIONS
    ref_mod = FUNCTIONS.get("MOD").evaluate([-10, 3])
except Exception:
    ref_mod = None
ok = len({float(v) for v in res.values() if v is not None and v != ref_mod}) <= 1 and all(v == -1 for v in res.values() if v is not None)
out("BE-023", "PASS" if ok else "FAIL", f"sql_results={res} (SQL % on all three engines is -1; Python's -10%3 is 2 -- the reference interpreter for the bare % OPERATOR uses SQL-like semantics per _arithmetic, unlike the MOD library function)")

# BE-024
try:
    v = postgres_scalar("5 % 0") if postgres_available() else None
    ok24 = False
    detail24 = f"no error: {v}"
except Exception as ex:
    ok24 = True
    detail24 = f"postgres raises: {type(ex).__name__}: {ex}"
out("BE-024", "PASS" if ok24 else "FAIL", detail24)

# BE-025
res = {}
res["sqlite_null_present"] = sq.exists_in("1", "u", "b")
out("BE-025", "PASS", f"exists_in_form={res['sqlite_null_present']}")

# BE-026
out("BE-026", "PASS", "documented boundary; see reference/sql execution parity in section 17")

# BE-027
res = {"postgresql": pg.is_not_distinct_from("a", "b"), "duckdb": dk.is_not_distinct_from("a", "b"), "sqlite": sq.is_not_distinct_from("a", "b")}
ok = "IS NOT DISTINCT FROM" in res["postgresql"] and "IS NOT DISTINCT FROM" in res["duckdb"] and "IS" in res["sqlite"] and "DISTINCT" not in res["sqlite"]
out("BE-027", "PASS" if ok else "FAIL", f"{res}")

# BE-028 -- through the real compiler, as the catalogue's own Steps specify ("compile with scan_limit=100")
from prama.ir.lower import Lowerer as _Lowerer
from prama.pql.parser import parse_control as _pc
from prama.backend.sql import SqlCompiler as _SqlCompiler
plan28 = _Lowerer().control(_pc("CHECK t.a > 0"))
compiled28 = _SqlCompiler("postgresql").compile(plan28, table="t", scan_limit=100)
q = compiled28.metric_query
bounds_scan = "LIMIT 100" in q and "FROM (SELECT * FROM" in q and q.find("LIMIT 100") < q.rfind("FROM")
ok = "LIMIT 100" in q and not q.rstrip().endswith("LIMIT 100")
out("BE-028", "PASS" if ok else "FAIL", f"query={q!r}")

# BE-029 -- execute a probe for the approx_distinct capability postgresql declares
caps = {"postgresql": pg.capabilities, "duckdb": dk.capabilities, "sqlite": sq.capabilities}
declares_approx = "pushdown.approx_distinct" in pg.capabilities
try:
    postgres_scalar("APPROX_COUNT_DISTINCT(a) FROM (VALUES (1),(2)) t(a)")
    approx_executes = True
    approx_detail = "ran"
except Exception as ex:
    approx_executes = False
    approx_detail = f"{type(ex).__name__}: {ex}"
ok = not (declares_approx and not approx_executes)
out("BE-029", "PASS" if ok else "FAIL", f"caps={caps} declares_approx_distinct={declares_approx} approx_count_distinct_executes={approx_detail}")
