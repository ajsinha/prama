import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

# CLI-216: bench run --seed required
code, out, err = c.run(["bench", "run"])
ok = code == 2 and "--seed" in err
record("CLI-216", "PASS" if ok else "FAIL", f"code={code} err={err[:200]!r}")

# CLI-217: same seed reproduces the same corpus and scores
code1, out1, _ = c.run(["--json", "bench", "run", "--seed", "42"])
code2, out2, _ = c.run(["--json", "bench", "run", "--seed", "42"])
ok = code1 == 0 and code2 == 0 and out1 == out2
record("CLI-217", "PASS" if ok else "FAIL", f"identical={out1==out2} len1={len(out1)} len2={len(out2)}")

# CLI-218: different seeds -> different corpora
code3, out3, _ = c.run(["--json", "bench", "run", "--seed", "43"])
ok = code3 == 0 and out3 != out1
record("CLI-218", "PASS" if ok else "FAIL", f"differs_from_seed42={out3!=out1}")

# CLI-219: --rows and --rate at edges
res219 = {}
for args in [["--rows", "0"], ["--rows", "1"], ["--rate", "0"], ["--rate", "1"], ["--rate", "1.5"], ["--rate", "-0.1"]]:
    code, out, err = c.run(["--json", "bench", "run", "--seed", "1"] + args)
    res219[" ".join(args)] = (code, "Traceback" in err, err[-150:] if code not in (0,) else "")
bad219 = {k: v for k, v in res219.items() if v[1]}
ok = not bad219
record("CLI-219", "PASS" if ok else "FAIL", f"{res219}")

# CLI-220: a class that planted nothing is named loudly
code, out, err = c.run(["bench", "run", "--seed", "1", "--rate", "0.001"])
mentions = "planted nothing" in out.lower() or "nothing this run" in out.lower()
record("CLI-220", "PASS" if mentions else "FAIL", f"code={code} mentions={mentions} out_tail={out[-400:]!r}")

# CLI-221: undefined metric prints a dash, not zero. Round 3/round 4's original
# fixture passed --rate 0.0, which is out of bounds ((0, 1]) and never reaches
# the precision column at all -- it just exercises the (unrelated) --rate
# refusal path this batch also fixed, so a clean exit with no Traceback was
# passing regardless of whether any dash was ever printed. Corrected: --rate
# 0.0 removed (a plain `bench run` already has a real undefined-precision row
# for free -- 'detect-nothing 0/28 - 0.00 -', where precision and F1 are
# genuinely undefined at 0 true positives and recall is a well-defined 0.00),
# and the assertion now actually reads the detect-nothing row's precision cell.
code, out, err = c.run(["bench", "run", "--seed", "1"])
detect_nothing_lines = [ln for ln in out.splitlines() if ln.strip().startswith("detect-nothing")]
precision_is_dash = bool(detect_nothing_lines) and detect_nothing_lines[0].split()[1:5] == ["bound", "0/28", "-", "0.00"]
record(
    "CLI-221",
    "PASS" if precision_is_dash else "FAIL",
    f"code={code} detect_nothing_row={detect_nothing_lines[0].strip() if detect_nothing_lines else None!r} "
    f"-- precision (0 true positives out of 0 predicted) prints '-', recall (0/28, well-defined) prints '0.00'",
)

# CLI-222: NOT-run baselines printed every run
code, out, err = c.run(["bench", "run", "--seed", "1"])
ok = code == 0 and ("not run" in out.lower() or "bounds and ablations" in out.lower())
record("CLI-222", "PASS" if ok else "FAIL", f"code={code} out_tail={out[-500:]!r}")

# CLI-223: bench taxonomy --family unknown
code, out, err = c.run(["bench", "taxonomy", "--family", "wizard"])
ok = code == 1 and "Traceback" not in err and "ValueError" not in err
record("CLI-223", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:250]!r}")

# CLI-224: bench runs with no database and no network -- our harness never opens a db for bench anyway; confirm no --config needed
code_r, out_r, err_r = c.run(["bench", "run", "--seed", "1"])
code_t, out_t, err_t = c.run(["bench", "taxonomy"])
ok = code_r == 0 and code_t == 0
record("CLI-224", "PASS" if ok else "FAIL", f"run_code={code_r} taxonomy_code={code_t} (no --config passed to either)")

print("done bench batch")
