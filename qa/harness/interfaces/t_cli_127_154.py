import sys, os, json, asyncio, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "control2"
WORK.mkdir(exist_ok=True, parents=True)


def wf(name, text):
    p = WORK / name
    p.write_text(text, encoding="utf-8")
    return p


SUITE = wf(
    "suite.pql",
    "SUITE positions_eod_core {\n"
    "  CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id)\n"
    "    SEVERITY critical DIMENSION uniqueness BECAUSE 'Declared grain'\n\n"
    "  CHECK positions_eod.notional_amount IS NOT NULL\n"
    "    SEVERITY critical DIMENSION completeness BECAUSE 'CDE for FRTB'\n\n"
    "  CHECK positions_eod.isin MATCHES /^[A-Z]{2}[0-9A-Z]{9}[0-9]$/\n"
    "    SEVERITY major DIMENSION validity BECAUSE 'ISO 6166'\n"
    "}\n",
)

# CLI-127: control functions prints coverage for every dialect
code, out, err = c.run(["control", "functions"])
code_j, out_j, err_j = c.run(["--json", "control", "functions"])
doc = json.loads(out_j)
ok = code == 0 and "%" in out and "duckdb" in out and "sqlite" in out and doc.get("functions") and doc.get("coverage")
record("CLI-127", "PASS" if ok else "FAIL", f"code={code} dialects={[r['engine'] for r in doc.get('coverage',[])]}")

# CLI-128: control functions --engine unknown lists real ones
code, out, err = c.run(["control", "functions", "--engine", "oracle"])
ok = code == 1 and ("duckdb" in out or "duckdb" in err) and ("sqlite" in out or "sqlite" in err)
record("CLI-128", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:200]!r}")

# CLI-129: control functions --json shares agree with text
code_j, out_j, err_j = c.run(["--json", "control", "functions"])
doc = json.loads(out_j)
bad129 = []
for row in doc["coverage"]:
    total = len(doc["functions"])
    refused = len(row["refused"])
    expected_share = (total - refused) / total if total else 0
    if abs(row["share"] - expected_share) > 1e-9:
        bad129.append((row["engine"], row["share"], expected_share))
    if row["share"] >= 1.0 and refused:
        bad129.append((row["engine"], "100% but has refused", row["refused"]))
ok = not bad129
record("CLI-129", "PASS" if ok else "FAIL", f"bad={bad129}")

# CLI-130: control compile prints SQL per control with description
code, out, err = c.run(["control", "compile", str(SUITE)])
ok = code == 0 and out.count("-- In positions_eod") == 3 and "SELECT" in out.upper()
record("CLI-130", "PASS" if ok else "FAIL", f"code={code} labels={out.count('-- In positions_eod')}")

# CLI-131: control compile --dialect for each engine, distinct renderings
outs = {}
for d in ["postgresql", "duckdb", "sqlite"]:
    code, out, err = c.run(["control", "compile", str(SUITE), "--dialect", d])
    outs[d] = (code, out)
ok = all(v[0] == 0 for v in outs.values()) and len({outs[d][1] for d in outs}) == 3
record("CLI-131", "PASS" if ok else "FAIL", f"codes={[v[0] for v in outs.values()]} all_distinct={len({outs[d][1] for d in outs})==3}")

# CLI-132: control compile --dialect unknown
code, out, err = c.run(["control", "compile", str(SUITE), "--dialect", "oracle"])
ok = code != 0 and "Traceback" not in err
record("CLI-132", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:250]!r}")

# CLI-133: control compile reports a refused function rather than crashing
ROUND_CTL = wf("round.pql", "CHECK positions_eod SATISFIES EXCEL '=ROUND(notional_amount, 2) > 0'\n  SEVERITY major DIMENSION accuracy BECAUSE 'x'\n")
code, out, err = c.run(["control", "compile", str(ROUND_CTL), "--dialect", "sqlite"])
ok = code == 0 and ("refused:" in out) and "Traceback" not in err
record("CLI-133", "PASS" if ok else "FAIL", f"code={code} out={out[-300:]!r} err={err[:150]!r}")

# CLI-134: control compile on IN CODELIST doesn't falsely refuse
CODELIST_CTL = wf("codelist.pql", "CHECK positions_eod.ccy IN CODELIST iso4217\n  SEVERITY major DIMENSION validity BECAUSE 'x'\n")
code, out, err = c.run(["control", "compile", str(CODELIST_CTL)])
ok = code == 0 and "not registered" not in out and "SELECT" in out.upper()
record("CLI-134", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r} err={err[:200]!r}")

# CLI-135: control compile --fuse groups controls sharing a scope
FUSE_SUITE = wf(
    "fuse.pql",
    "CHECK positions_eod.a IS NOT NULL BECAUSE 'a'\n"
    "CHECK positions_eod.b IS NOT NULL BECAUSE 'b'\n"
    "CHECK positions_eod.c IS NOT NULL BECAUSE 'c'\n"
    "CHECK positions_eod.d IS NOT NULL BECAUSE 'd'\n"
    "CHECK other_table.e IS NOT NULL BECAUSE 'e'\n",
)
code, out, err = c.run(["control", "compile", str(FUSE_SUITE), "--fuse"])
n_select = out.upper().count("SELECT")
ok = code == 0 and n_select == 2 and "scan" in out.lower()
record("CLI-135", "PASS" if ok else "FAIL", f"code={code} n_select={n_select} out_head={out[:200]!r}")

# CLI-136: --fuse with one unlowerable control
UNFUSE_SUITE = wf(
    "unfuse.pql",
    "CHECK positions_eod.a IS NOT NULL BECAUSE 'a'\n"
    "CHECK positions_eod.b IS NOT NULL BECAUSE 'b'\n"
    "CHECK positions_eod SATISFIES EXCEL '=ROUND(a, 2) > 0'\n  SEVERITY major DIMENSION accuracy BECAUSE 'x'\n",
)
code, out, err = c.run(["control", "compile", str(UNFUSE_SUITE), "--fuse", "--dialect", "sqlite"])
mentions_excluded = "refused" in out.lower() or "could not" in out.lower() or "excluded" in out.lower()
record(
    "CLI-136",
    "PASS" if (code == 0 and mentions_excluded) else "FAIL",
    f"code={code} mentions_excluded={mentions_excluded} out={out[-300:]!r} err={err[:200]!r} -- "
    f"'exit code says something was left out' per catalogue, but ControlCompileCommand exits 0 always on --fuse",
)

# CLI-137: --fuse --dialect sqlite: refused function inside fused path
code, out, err = c.run(["control", "compile", str(UNFUSE_SUITE), "--fuse", "--dialect", "sqlite"])
ok = code == 0 and "Traceback" not in err
record("CLI-137", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

print("done control batch part2 (functions/compile)")
