import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "control4"
WORK.mkdir(exist_ok=True, parents=True)


def wf(name, text):
    p = WORK / name
    p.write_text(text, encoding="utf-8")
    return p


DBT = """
version: 2
models:
  - name: positions_eod
    columns:
      - name: account_id
        tests: [unique, not_null]
      - name: qty
        tests: [my_company.check_frtb]
"""
DBT_COMPLETE = (
    "version: 2\nmodels:\n  - name: t\n    columns:\n"
    "      - name: k\n        tests: [not_null]\n"
)

# CLI-149: --from is required and closed
code, out, err = c.run(["control", "import", str(wf("x.yml", DBT))])
ok1 = code == 2 and ("required" in err.lower() or "--from" in err.lower())
code2, out2, err2 = c.run(["control", "import", str(wf("x.yml", DBT)), "--from", "monte_carlo"])
ok2 = code2 == 2 and "dbt" in err2.lower()
ok = ok1 and ok2
record("CLI-149", "PASS" if ok else "FAIL", f"missing: code={code} err={err[:150]!r} | invalid('soda'): code={code2} err={err2[:250]!r}")

# CLI-150: control import exits non-zero when something did not come across
dbtfile = wf("schema.yml", DBT)
code, out, err = c.run(["control", "import", str(dbtfile), "--from", "dbt"])
ok = code == 1 and "did not come across" in out or "1 did not come across" in out
record("CLI-150", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-151: --out writes and still reports the residue; file re-reads with control check
outfile = WORK / "imported.pql"
code, out, err = c.run(["control", "import", str(dbtfile), "--from", "dbt", "--out", str(outfile)])
file_written = outfile.is_file()
code_check, out_check, err_check = c.run(["control", "check", str(outfile)])
ok = code == 1 and file_written and "did not come across" in out and code_check in (0, 1) and "no such file" not in out_check
record("CLI-151", "PASS" if ok else "FAIL", f"code={code} file_written={file_written} reports_residue={'did not come across' in out} recheck_code={code_check}")

# CLI-152: --out to an unwritable path
code, out, err = c.run(["control", "import", str(dbtfile), "--from", "dbt", "--out", "/proc/out.pql"])
ok = code == 1 and "Traceback" not in err and "OSError" not in err
record("CLI-152", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:300]!r}")

# CLI-153: control import on a file of the wrong format
ge_json = wf("ge.json", json.dumps({
    "expectations": [{"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "id"}}]
}))
code, out, err = c.run(["control", "import", str(ge_json), "--from", "dbt"])
ok = (code == 1 and ("mismatch" in out.lower() or "format" in out.lower() or "could not" in out.lower())) or (
    not (code == 1 and "0 controls imported" in out and len(err) == 0)
)
record("CLI-153", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r} err={err[:150]!r}")

# CLI-154: control import on a missing file exits 2 like _read's convention
code, out, err = c.run(["control", "import", str(WORK / "nope.yml"), "--from", "dbt"])
ok = code == 2 and "no such file" in out
record("CLI-154", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

print("done control batch part4 (import)")
