import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "pack2"
WORK.mkdir(exist_ok=True, parents=True)

# CLI-240: pack parse on a directory, missing file, empty file
adir = WORK / "adir"
adir.mkdir(exist_ok=True)
code_d, out_d, err_d = c.run(["pack", "parse", str(adir)])
code_m, out_m, err_m = c.run(["pack", "parse", str(WORK / "nope.fix")])
empty = WORK / "empty.fix"
empty.write_text("")
code_e, out_e, err_e = c.run(["pack", "parse", str(empty)])
clean_e = code_e == 0 and "no structural defects" in out_e.lower()
ok = code_d != 0 and "Traceback" not in err_d and code_m != 0 and "Traceback" not in err_m and not clean_e
record(
    "CLI-240",
    "PASS" if ok else "FAIL",
    f"dir: code={code_d} err={err_d[:150]!r} | missing: code={code_m} err={err_m[:150]!r} | "
    f"empty: code={code_e} clean_pass={clean_e} out={out_e[:150]!r} err={err_e[:150]!r}",
)

# CLI-241: pack parse on a binary file does not crash
png = WORK / "img.png"
png.write_bytes(bytes(range(256)) * 4)
code, out, err = c.run(["pack", "parse", str(png)])
ok = code != 0 and "Traceback" not in err
record("CLI-241", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:250]!r}")

# CLI-242: pack parse masks a PAN
def iso8583_file():
    bits = ["0"] * 64
    for field in (2, 3, 4, 7, 11, 49):
        bits[field - 1] = "1"
    bitmap = "".join(f"{int(''.join(bits[i : i + 4]), 2):X}" for i in range(0, 64, 4))
    path = WORK / "auth.8583"
    path.write_text(
        "0200" + bitmap + "16" + "4111111111111111" + "000000" + "000000012345" + "0910120000" + "000001" + "826"
    )
    return path

i8583 = iso8583_file()
code_t, out_t, err_t = c.run(["pack", "parse", str(i8583)])
code_j, out_j, err_j = c.run(["--json", "pack", "parse", str(i8583)])
ok = "4111111111111111" not in out_t and "4111111111111111" not in err_t and "4111111111111111" not in out_j
record("CLI-242", "PASS" if ok else "FAIL", f"leaked_text={'4111111111111111' in out_t} leaked_json={'4111111111111111' in out_j}")

# CLI-243: pack concepts lists, and one concept names its boundary
code, out, err = c.run(["pack", "concepts"])
code2, out2, err2 = c.run(["pack", "concepts", "Exposure"])
ok = code == 0 and code2 == 0 and "What it is not" in out2 and "Why it matters" in out2
record("CLI-243", "PASS" if ok else "FAIL", f"list_code={code} concept_code={code2} out2_head={out2[:300]!r}")

# CLI-244: pack concepts unknown name
code, out, err = c.run(["pack", "concepts", "Wizard"])
ok = code == 1 and "Traceback" not in err and "KeyError" not in err
record("CLI-244", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:300]!r}")

# CLI-245: pack recognise refuses to guess between lookalike concepts
code, out, err = c.run(["pack", "recognise", "event_id", "ts", "payload"])
ok = code == 0 and "no concept recognised" in out.lower()
record("CLI-245", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-246: pack recognise on a real concept's columns
code, out, err = c.run(["pack", "recognise", "account_id", "ccy"])
ok = code == 0 and "recognition is a proposal" in out.lower()
record("CLI-246", "PASS" if ok else "FAIL", f"code={code} out={out[:400]!r}")

# CLI-247: pack recognise --as unknown concept
code, out, err = c.run(["pack", "recognise", "a", "b", "--as", "Wizard"])
ok = code == 1 and "Traceback" not in err and "KeyError" not in err
record("CLI-247", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:300]!r}")

# CLI-248: pack recognise with no columns and 500 columns
code, out, err = c.run(["pack", "recognise"])
ok1 = code == 2
many_cols = [f"col{i}" for i in range(500)]
code2, out2, err2 = c.run(["pack", "recognise"] + many_cols)
ok2 = code2 == 0 and "Traceback" not in err2 and len(out2) < 20000  # bounded, not a screen of 500 names
record("CLI-248", "PASS" if (ok1 and ok2) else "FAIL", f"no_args_code={code} many_code={code2} out2_len={len(out2)}")

# CLI-249: every pack subcommand works with no database (never touches --config at all)
subs = [
    ["pack", "list"], ["pack", "claims"], ["pack", "calendar", "TARGET2", "--year", "2030"],
    ["pack", "reconciliation"], ["pack", "soc2"], ["pack", "concepts"],
    ["pack", "recognise", "account_id", "ccy"], ["pack", "parse", str(i8583)],
]
bad249 = {}
for argv in subs:
    code, out, err = c.run(argv)
    if code not in (0, 1) or "Traceback" in err:
        bad249[" ".join(argv)] = (code, err[:150])
ok = not bad249
record("CLI-249", "PASS" if ok else "FAIL", f"bad={bad249}")

# CLI-250: every pack subcommand supports --json
bad250 = {}
for argv in subs:
    code, out, err = c.run(["--json"] + argv)
    try:
        json.loads(out)
    except Exception as e:
        bad250[" ".join(argv)] = (code, out[:150], str(e))
ok = not bad250
record("CLI-250", "PASS" if ok else "FAIL", f"bad={bad250}")

print("done pack batch part2")
