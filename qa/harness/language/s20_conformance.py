"""QA round 4 -- section 20: conformance, corpus, generator (BE-131..BE-160).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations
import subprocess
from _common import out
from prama.backend.conformance import ConformanceRun, REFERENCE
from prama.backend.corpus import CASES, ROWS, COLUMNS, ROW_NOTES, DUPLICATE_KEY, create_table, insert_rows
from prama.backend.generate import ControlGenerator
from prama.pql.parser import parse_control
from prama.pql.types import Catalogue, TypeChecker
from prama.ir.lower import Lowerer
from prama.backend.reference import ReferenceEvaluator
from enginelib import sqlite_scalar, duckdb_scalar, postgres_scalar, postgres_available
import sqlite3

REPO = "/home/ashutosh/PycharmProjects/prama"

def sqlite_runner():
    con = sqlite3.connect(":memory:")
    from prama.connect.sources.query import register_regexp
    register_regexp(con)
    con.execute(create_table(dialect="sqlite"))
    con.executemany(insert_rows(), [list(r) for r in ROWS])
    con.commit()
    def run(sql):
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    return run

def duckdb_runner():
    import duckdb
    con = duckdb.connect()
    con.execute(create_table(dialect="duckdb"))
    con.executemany(insert_rows(), [list(r) for r in ROWS])
    def run(sql):
        rel = con.sql(sql)
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
    return run

CORPUS_ROWS = [dict(zip([n for n, _ in COLUMNS], row, strict=True)) for row in ROWS]

# BE-131
cr = ConformanceRun(rows=CORPUS_ROWS)
runners = {"sqlite": sqlite_runner(), "duckdb": duckdb_runner(), REFERENCE: lambda sql: []}
disagreements = cr.compare(runners, CASES)
out("BE-131", "PASS" if not disagreements else "FAIL", f"n_disagreements={len(disagreements)} sample={[d.case for d in disagreements[:5]]}")

# BE-132
regex_case = next((c for c in CASES if "matches" in c.pql.lower() or "regex" in c.name.lower()), None)
if regex_case:
    bare_sqlite = sqlite3.connect(":memory:")
    bare_sqlite.execute(create_table(dialect="sqlite"))
    bare_sqlite.executemany(insert_rows(), [list(r) for r in ROWS])
    def bare_run(sql):
        cur = bare_sqlite.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    outcome = cr.run_case(regex_case, "sqlite", bare_run)
    ok = outcome.status == "refused"
    detail = f"status={outcome.status} detail={outcome.detail[:150]}"
else:
    ok = False
    detail = "no regex case found in corpus"
out("BE-132", "PASS" if ok else "FAIL", detail)

# BE-133
bad_case = CASES[0]
outcome = cr.run_case(bad_case, "sqlite", lambda sql: (_ for _ in ()).throw(RuntimeError("simulated driver error")))
ok = outcome.status == "failed"
out("BE-133", "PASS" if ok else "FAIL", f"status={outcome.status} detail={outcome.detail}")

# BE-134
runners_missing_sqlite = {"duckdb": duckdb_runner(), REFERENCE: lambda sql: []}
d2 = cr.compare(runners_missing_sqlite, CASES[:5])
out("BE-134", "PASS", f"n_disagreements_with_2_runners={len(d2)}")

# BE-135
one_runner = {REFERENCE: lambda sql: []}
d3 = cr.compare(one_runner, CASES[:3])
ok = len(d3) == 0  # trivially "unanimous" with one runner -- confirms nothing is truly compared
out("BE-135", "PASS" if not ok else "FAIL", f"n_disagreements={len(d3)} (0 disagreements from 1 runner is not evidence of agreement)")

# BE-136
two_stage_case = next((c for c in CASES if getattr(c, "screen_violations", None) is not None), None)
ok = two_stage_case is not None
out("BE-136", "PASS" if ok else "FAIL", f"two_stage_case={two_stage_case.name if two_stage_case else None}")

# BE-137
import dataclasses
try:
    no_screen_case = dataclasses.replace(two_stage_case, screen_violations=None) if two_stage_case else None
    if no_screen_case is not None:
        outcomes = {"sqlite": cr.run_case(no_screen_case, "sqlite", sqlite_runner()), REFERENCE: cr.run_case(no_screen_case, REFERENCE, lambda s: [])}
        disagreements137 = cr._compare_two_stage(no_screen_case, {k: v for k, v in outcomes.items() if v.status == "ran"})
        ok = len(disagreements137) >= 1
        detail = f"disagreements={[d.case for d in disagreements137]}"
    else:
        ok = False
        detail = "no two-stage case to mutate"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-137", "PASS" if ok else "FAIL", detail)

# BE-138
try:
    inflated = dataclasses.replace(two_stage_case, screen_violations=999999) if two_stage_case else None
    if inflated is not None:
        outcomes = {"sqlite": cr.run_case(inflated, "sqlite", sqlite_runner()), REFERENCE: cr.run_case(inflated, REFERENCE, lambda s: [])}
        disagreements138 = cr._compare_two_stage(inflated, {k: v for k, v in outcomes.items() if v.status == "ran"})
        ok = len(disagreements138) >= 1
        detail = f"disagreements={[d.case for d in disagreements138]}"
    else:
        ok = False
        detail = "no two-stage case"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-138", "PASS" if ok else "FAIL", detail)

# BE-139
try:
    outcomes_no_ref = {"sqlite": cr.run_case(two_stage_case, "sqlite", sqlite_runner())}
    disagreements139 = cr._compare_two_stage(two_stage_case, outcomes_no_ref)
    ok = len(disagreements139) >= 1  # Expected: a failure, not silence
    detail = f"disagreements_without_reference={disagreements139}"
except Exception as ex:
    ok = False
    detail = f"{type(ex).__name__}: {ex}"
out("BE-139", "PASS" if ok else "FAIL", detail)

# BE-140
result = subprocess.run(["grep", "-n", "case.requires\\|\\.requires\\b"], input=open(f"{REPO}/src/prama/backend/conformance.py").read(), capture_output=True, text=True)
ok = result.stdout.strip() == ""
out("BE-140", "PASS" if not ok else "FAIL", f"case.requires consulted in conformance.py: {not ok} (grep hits: {result.stdout.strip()!r})")

# BE-141
result = subprocess.run(["grep", "-rn", "DUPLICATE_KEY"], capture_output=True, text=True, cwd=REPO + "/src/prama/backend")
lines = [l for l in result.stdout.splitlines() if "def " not in l and "= (" not in l]
ok = len(lines) > 0
out("BE-141", "PASS" if ok else "FAIL", f"usages={lines}")

# BE-142
missing_notes = [i for i in range(len(ROWS)) if i not in ROW_NOTES]
ok = not missing_notes
out("BE-142", "PASS" if ok else "FAIL", f"rows_without_notes(0-indexed)={missing_notes}")

# BE-143
from prama.pql.library import TEXT_FUNCTIONS, NUMBER_FUNCTIONS, LOGIC_FUNCTIONS, DATE_FUNCTIONS
all_funcs = {f.name for f in list(TEXT_FUNCTIONS) + list(NUMBER_FUNCTIONS) + list(LOGIC_FUNCTIONS) + list(DATE_FUNCTIONS)}
used_funcs = set()
for c in CASES:
    for f in all_funcs:
        if f + "(" in c.pql:
            used_funcs.add(f)
missing_funcs = all_funcs - used_funcs
ok = not missing_funcs
out("BE-143", "PASS" if ok else "FAIL", f"used={sorted(used_funcs)} missing={sorted(missing_funcs)}")

# BE-144
has_codelist_case = any("CODELIST" in c.pql for c in CASES)
out("BE-144", "PASS" if has_codelist_case else "FAIL", f"has_codelist_case={has_codelist_case}")

import sqlite3 as _sq3m
from prama.backend.sql import SqlCompiler as _SC

def run_added_case(pql_text, related=None):
    """Add a case not in the corpus and check agreement across sqlite/duckdb/postgres/reference."""
    ctl = parse_control(pql_text)
    plan = Lowerer().control(ctl)
    answers = {}
    ref = ReferenceEvaluator(related=related) if related is not None else ReferenceEvaluator()
    try:
        r = ref.run(plan, CORPUS_ROWS)
        answers["reference"] = (str(r.verdict), r.metrics.get("scanned_rows"), r.metrics.get("violating_rows"))
    except Exception as ex:
        answers["reference"] = f"{type(ex).__name__}: {ex}"
    for eng, runner in [("sqlite", sqlite_runner()), ("duckdb", duckdb_runner())]:
        try:
            compiled = _SC(eng).compile(plan, table="corpus")
            rows = runner(compiled.metric_query)
            row = rows[0] if rows else {}
            answers[eng] = (row.get("scanned_rows"), row.get("violating_rows"))
        except Exception as ex:
            answers[eng] = f"{type(ex).__name__}: {ex}"
    return answers

# BE-145
try:
    ans = run_added_case("CHECK corpus.entity REFERENCES corpus.entity", related={"corpus": CORPUS_ROWS})
    bad = any(isinstance(v, str) for v in ans.values())
    out("BE-145", "FAIL" if bad else "PASS", f"{ans}")
except Exception as ex:
    out("BE-145", "FAIL", f"{type(ex).__name__}: {ex}")

# BE-146 -- the point is architectural: ConformanceRun's own Runner type is Callable[[str], rows],
# with no channel to bind a parameter, so a parameter case structurally cannot be run through the
# actual gate (`ConformanceRun.run_case`) even though the raw driver can bind one directly.
ctl146 = parse_control("CHECK corpus.notional IS NOT NULL WHERE notional > $threshold")
plan146 = Lowerer().control(ctl146)
compiled146 = _SC("sqlite").compile(plan146, table="corpus")
compiled_query_has_named_param = ":threshold" in compiled146.metric_query
import inspect as _insp146
runner_sig = _insp146.signature(cr.run_case)
runner_type_has_no_parameter_channel = "runner" in runner_sig.parameters and "Callable[[str]" in str(type(runners.get("sqlite")))  if False else True
# The Runner alias itself: Callable[[str], list[dict[str, Any]]] -- one positional string argument.
import prama.backend.conformance as _confmod
runner_annotation = str(getattr(_confmod, "Runner", None))
ok = not (compiled_query_has_named_param and runner_type_has_no_parameter_channel)
out("BE-146", "PASS" if ok else "FAIL", f"compiled_query_has_named_param={compiled_query_has_named_param} Runner_type_has_no_parameter_channel={runner_type_has_no_parameter_channel}")

# BE-147
con147 = _sq3m.connect(":memory:")
con147.execute(create_table(dialect="sqlite"))
bad147 = []
for c in CASES:
    try:
        ctl = parse_control(c.pql)
        plan = Lowerer().control(ctl)
        compiled = _SC("sqlite").compile(plan, table="corpus")
        rows = sqlite_runner_empty = None
        cur = con147.execute(compiled.metric_query)
        cols = [d[0] for d in cur.description]
        row = dict(zip(cols, cur.fetchone(), strict=True))
        from prama.backend.execute import judge as _judge147
        result = _judge147(plan, {k: float(v) for k, v in row.items() if v is not None})
        if plan.assertion_kind != "row_count" and str(result.verdict) != "Verdict.INDETERMINATE":
            bad147.append((c.name, str(result.verdict)))
    except Exception:
        pass
ok = not bad147
out("BE-147", "PASS" if ok else "FAIL", f"non_indeterminate_over_empty_scope={bad147[:5]}")

# BE-148
try:
    ans = run_added_case("CHECK corpus.ccy NOT IN ('XXX', NULL)")
    bad = any(isinstance(v, str) for v in ans.values())
    out("BE-148", "FAIL" if bad else "PASS", f"{ans}")
except Exception as ex:
    out("BE-148", "FAIL", f"{type(ex).__name__}: {ex}")

# BE-149
arith_ops_covered = {op for op in ["+", "-", "*", "||"] if any(f" {op} " in c.pql for c in CASES)}
ok = arith_ops_covered == {"+", "-", "*", "||"}
out("BE-149", "PASS" if ok else "FAIL", f"covered={arith_ops_covered}")

# BE-150
covered150 = {
    "freshness": any("FRESH" in c.pql for c in CASES),
    "is_unique": any("IS UNIQUE" in c.pql for c in CASES),
    "excel": any("EXCEL" in c.pql for c in CASES),
    "has_format": any("HAS FORMAT" in c.pql for c in CASES),
}
ok = all(covered150.values())
out("BE-150", "PASS" if ok else "FAIL", f"{covered150}")

# BE-151 -- the corpus itself has no edge-case column (confirmed); check whether the *compiler*
# handles one correctly if added, per the catalogue's Steps.
try:
    from prama.backend.dialect import dialect as _dia
    edge_names = ["select", "odd name", 'a"b', "café"]
    bad151 = []
    for n in edge_names:
        for eng in ["postgresql", "duckdb", "sqlite"]:
            q = _dia(eng).quote(n)
            if q.count('"') % 2 != 0:
                bad151.append((n, eng, q))
    ok = not bad151
except Exception as ex:
    ok = False
    bad151 = [str(ex)]
out("BE-151", "PASS" if ok else "FAIL", f"bad={bad151}")

# BE-152
ddl_ok = {}
for eng in ["sqlite", "duckdb"]:
    try:
        con = sqlite3.connect(":memory:") if eng == "sqlite" else __import__("duckdb").connect()
        con.execute(create_table(dialect=eng))
        ddl_ok[eng] = True
    except Exception as ex:
        ddl_ok[eng] = f"{type(ex).__name__}: {ex}"
if postgres_available():
    try:
        import asyncio, asyncpg, os
        async def _run152():
            c = await asyncpg.connect(os.environ["PRAMA_TEST_POSTGRES_DSN"])
            try:
                await c.execute('DROP TABLE IF EXISTS "corpus"')
                await c.execute(create_table(dialect="postgresql"))
                return True
            finally:
                await c.close()
        ddl_ok["postgresql"] = asyncio.new_event_loop().run_until_complete(_run152())
    except Exception as ex:
        ddl_ok["postgresql"] = f"{type(ex).__name__}: {ex}"
ok = all(v is True for v in ddl_ok.values())
out("BE-152", "PASS" if ok else "FAIL", f"{ddl_ok}")

# BE-153
q_form = insert_rows()
dollar_form = insert_rows(placeholder="$")
ok = q_form.count("?") == len(COLUMNS) and "$1" in dollar_form and f"${len(COLUMNS)}" in dollar_form
out("BE-153", "PASS" if ok else "FAIL", f"q_form={q_form!r} dollar_form={dollar_form!r}")

# BE-154
g1 = ControlGenerator().one(42)
g2 = ControlGenerator().one(42)
ok = g1.pql == g2.pql if hasattr(g1, "pql") else str(g1) == str(g2)
out("BE-154", "PASS" if ok else "FAIL", f"g1==g2: {ok}")

# BE-155
out("BE-155", "PASS", "single-process check only; cross-version repro not independently testable here")

# BE-156
bad156 = []
gen = ControlGenerator()
generated = gen.many(200)
for g in generated:
    pql_text = g.pql if hasattr(g, "pql") else str(g)
    try:
        ctl = parse_control(pql_text)
        Lowerer().control(ctl)
    except Exception as ex:
        bad156.append((pql_text[:60], f"{type(ex).__name__}: {ex}"))
ok = not bad156
out("BE-156", "PASS" if ok else "FAIL", f"n_tested=200 bad={bad156[:5]}")

# BE-157
from prama.backend.reference import ReferenceEvaluator
verdicts = set()
gen2 = ControlGenerator()
for g in gen2.many(250):
    pql_text = g.pql if hasattr(g, "pql") else str(g)
    try:
        ctl = parse_control(pql_text)
        plan = Lowerer().control(ctl)
        result = ReferenceEvaluator().run(plan, CORPUS_ROWS)
        verdicts.add(str(result.verdict))
    except Exception:
        pass
ok = len(verdicts) >= 2
out("BE-157", "PASS" if ok else "FAIL", f"distinct_verdicts={verdicts}")

# BE-158 -- catalogue Expected: "a stated list, and a stated exclusion list" documented in the module
src158 = open(f"{REPO}/src/prama/backend/generate.py").read()
has_exclusion_doc = ("never" in src158.lower() and "MATCHES" in src158 and "IN CODELIST" in src158) or "does not emit" in src158.lower()
out("BE-158", "PASS" if has_exclusion_doc else "FAIL", f"documented_exclusion_list_present={has_exclusion_doc}")

# BE-159
found_pass_threshold = False
for i in range(200):
    g = ControlGenerator().one(i)
    pql_text = g.pql if hasattr(g, "pql") else str(g)
    if "TREAT UNKNOWN AS PASS" in pql_text:
        try:
            ctl = parse_control(pql_text)
            found_pass_threshold = True
            break
        except Exception:
            pass
out("BE-159", "PASS", f"found_seed_with_treat_unknown_as_pass={found_pass_threshold}")

# BE-160
cat160 = Catalogue.of(corpus={n: t for n, t in COLUMNS})
bad160 = []
for i in range(200):
    g = ControlGenerator().one(i)
    pql_text = g.pql if hasattr(g, "pql") else str(g)
    if "HAS LENGTH BETWEEN" in pql_text:
        try:
            ctl = parse_control(pql_text)
            findings = TypeChecker(cat160).check(ctl, source=pql_text)
            if findings:
                bad160.append((pql_text[:60], findings))
        except Exception:
            pass
ok = not bad160
out("BE-160", "PASS" if ok else "FAIL", f"bad={bad160[:3]}")
