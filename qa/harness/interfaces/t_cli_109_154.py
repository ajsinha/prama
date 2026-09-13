import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

SUITE = """
SUITE positions_eod_core {
  CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id)
    SEVERITY critical DIMENSION uniqueness BECAUSE 'Declared grain'

  CHECK positions_eod.notional_amount IS NOT NULL
    SEVERITY critical DIMENSION completeness BECAUSE 'CDE for FRTB'

  CHECK positions_eod.isin MATCHES /^[A-Z]{2}[0-9A-Z]{9}[0-9]$/
    SEVERITY major DIMENSION validity BECAUSE 'ISO 6166'
}
"""

WORK = c.WORKDIR / "control"
WORK.mkdir(exist_ok=True, parents=True)


def wf(name, text):
    p = WORK / name
    p.write_text(text, encoding="utf-8")
    return p


suite = wf("suite.pql", SUITE)

# CLI-109: clean suite -> Nothing to report, exit 0
code, out, err = c.run(["control", "check", str(suite)])
ok = code == 0 and "Nothing to report." in out and "3 control(s) read" in out
record("CLI-109", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-110: type error -> exit 1 with finding + remedy
type_err = wf("typeerr.pql", "CHECK positions_eod.notional_amount MATCHES /abc/\n  SEVERITY major DIMENSION validity BECAUSE 'x'\n")
code, out, err = c.run(["control", "check", str(type_err)])
ok = code == 1 and ("type" in out.lower() or "cannot" in out.lower())
record("CLI-110", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-111: --strict promotes warnings but not 'unchecked'
redundant = wf("redundant.pql", "CHECK t.a BETWEEN 0 AND 1 BECAUSE 'range'\nCHECK t.a IS NOT NULL BECAUSE 'null'\n")
code1, out1, _ = c.run(["control", "check", str(redundant)])
code2, out2, _ = c.run(["control", "check", str(redundant), "--strict"])
ok = code1 == 0 and code2 == 1
record("CLI-111", "PASS" if ok else "FAIL", f"without_strict={code1} with_strict={code2} out2={out2[:200]!r}")

# CLI-112: undeclared dataset reported once not per control
fifty = wf("fifty.pql", "\n".join(f"CHECK nowhere.col{i} IS NOT NULL BECAUSE 'x{i}'" for i in range(50)))
code, out, err = c.run(["control", "check", str(fifty)])
n_occurrences = out.count("nothing is known about nowhere")
ok = n_occurrences == 1
record("CLI-112", "PASS" if ok else "FAIL", f"code={code} occurrences={n_occurrences}")

# CLI-113: --json on a syntax error is valid JSON
badsyntax = wf("badsyntax.pql", "CHECK t.a IS NOT NULL SEVERITY urgent\n")
code, out, err = c.run(["--json", "control", "check", str(badsyntax)])
try:
    doc = json.loads(out)
    parse_ok = True
except Exception as e:
    doc = None
    parse_ok = False
ok = parse_ok and code == 1
record("CLI-113", "PASS" if ok else "FAIL", f"code={code} parse_ok={parse_ok} out={out[:200]!r}")

# CLI-114: missing file exits 2 across check/explain/format/compile
bad114 = {}
for sub in ["check", "explain", "format", "compile"]:
    code, out, err = c.run(["control", sub, str(WORK / "nosuch.pql")])
    if code != 2 or "no such file" not in out:
        bad114[sub] = (code, out[:100])
ok = not bad114
record("CLI-114", "PASS" if ok else "FAIL", f"bad={bad114}")

# CLI-115: directory where a file is expected
adir = WORK / "suite.pql.dir"
adir.mkdir(exist_ok=True)
code, out, err = c.run(["control", "check", str(adir)])
ok = code == 2 and "no such file" in out and "Traceback" not in err
record("CLI-115", "PASS" if ok else "FAIL", f"code={code} out={out!r} err={err[:150]!r}")

# CLI-116: non-UTF-8 file
latin1 = WORK / "latin1.pql"
latin1.write_bytes("CHECK t.a IS NOT NULL BECAUSE 'café \xe9'\n".encode("latin-1"))
code, out, err = c.run(["control", "check", str(latin1)])
ok = code == 1 and "Traceback" not in err and "UnicodeDecodeError" not in err
record("CLI-116", "PASS" if ok else "FAIL", f"code={code} out={out[:200]!r} err={err[:200]!r}")

# CLI-117: empty file
empty = wf("empty.pql", "")
code, out, err = c.run(["control", "check", str(empty)])
ok = code == 0 and "0 control(s) read" in out
record("CLI-117", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-118: explain renders one sentence per control
code, out, err = c.run(["control", "explain", str(suite)])
ok = code == 0 and out.count("· In positions_eod") == 3
record("CLI-118", "PASS" if ok else "FAIL", f"code={code} sentence_markers={out.count('· In positions_eod')}")

# CLI-119: explain prints Excel divergences
divg = wf("divg.pql", "CHECK positions SATISFIES EXCEL '=ROUND(notional, 2) > 0'\n  SEVERITY major DIMENSION accuracy BECAUSE 'rounded exposure'\n")
code, out, err = c.run(["control", "explain", str(divg)])
ok = code == 0 and "ROUND differs from Excel" in out
record("CLI-119", "PASS" if ok else "FAIL", f"code={code} out_tail={out[-300:]!r}")

# CLI-120: explain names functions an engine cannot run
ok = code == 0 and "cannot run on sqlite" in out
record("CLI-120", "PASS" if ok else "FAIL", f"present={'cannot run on sqlite' in out}")

# CLI-121: nested function found
nested = wf("nested.pql", "CHECK positions SATISFIES EXCEL '=IF(notional > 0, ROUND(notional, 2), 0) > 1'\n  SEVERITY major DIMENSION accuracy BECAUSE 'nested'\n")
code, out, err = c.run(["--json", "control", "explain", str(nested)])
doc = json.loads(out)
ok = code == 0 and any("ROUND differs from Excel" in n for n in doc[0]["divergences"])
record("CLI-121", "PASS" if ok else "FAIL", f"divergences={doc[0]['divergences'] if doc else None}")

# CLI-122: format prints canonical PQL without touching the file
mtime_before = suite.stat().st_mtime_ns
code, out, err = c.run(["control", "format", str(suite)])
mtime_after = suite.stat().st_mtime_ns
ok = code == 0 and out.startswith("CHECK positions_eod HAS UNIQUE KEY") and mtime_before == mtime_after
record("CLI-122", "PASS" if ok else "FAIL", f"code={code} mtime_unchanged={mtime_before==mtime_after} out_head={out[:60]!r}")

# CLI-123: format --write reports which happened
messy = wf("messy.pql", "CHECK   t.a   IS NOT NULL    BECAUSE 'x'\n")
code, out, err = c.run(["control", "format", str(messy), "--write"])
ok1 = code == 0 and "rewritten" in out.lower()
code2, out2, err2 = c.run(["control", "format", str(messy), "--write"])
ok2 = code2 == 0 and "already canonical" in out2.lower()
ok = ok1 and ok2
record("CLI-123", "PASS" if ok else "FAIL", f"first={out.strip()!r} second={out2.strip()!r}")

# CLI-124: format --write idempotent
before = messy.read_text()
code, out, err = c.run(["control", "format", str(messy), "--write"])
after = messy.read_text()
ok = code == 0 and "already canonical" in out.lower() and before == after
record("CLI-124", "PASS" if ok else "FAIL", f"unchanged={before==after} out={out.strip()!r}")

# CLI-125: format --write on read-only file
ro = wf("ro.pql", "CHECK t.a IS NOT NULL BECAUSE 'x'\n")
os.chmod(ro, 0o444)
is_root = os.geteuid() == 0
if is_root:
    record("CLI-125", "BLOCKED", "running as root; chmod 444 does not block writes, cannot exercise the refusal path")
else:
    code, out, err = c.run(["control", "format", str(ro), "--write"])
    ok = code == 1 and "Traceback" not in err and "PermissionError" not in err
    record("CLI-125", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:250]!r}")
os.chmod(ro, 0o644)

# CLI-126: format --write preserves comments, or refuses loudly
commented = wf("commented.pql", "# a leading comment\nCHECK t.a IS NOT NULL BECAUSE 'x'\n\n# a comment between\nCHECK t.b IS NOT NULL BECAUSE 'y'\n")
code, out, err = c.run(["control", "format", str(commented), "--write"])
after_text = commented.read_text()
comments_survived = "# a leading comment" in after_text and "# a comment between" in after_text
ok = code == 1 or comments_survived  # either loudly refused, or comments genuinely survived
record(
    "CLI-126",
    "PASS" if ok else "FAIL",
    f"code={code} comments_survived={comments_survived} after_text={after_text!r}",
)

print("done control batch part1")
