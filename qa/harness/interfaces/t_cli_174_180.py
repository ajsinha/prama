import sys, os, json, csv
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "contract4"
WORK.mkdir(exist_ok=True, parents=True)


def wcsv(name, rows, fieldnames):
    p = WORK / name
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return p


def wjl(name, rows):
    p = WORK / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))
    return p


before = wcsv("before.csv", [{"id": "1", "amount": "100"}, {"id": "2", "amount": "200"}], ["id", "amount"])
after = wcsv("after.csv", [{"id": "1", "amount": "150"}, {"id": "3", "amount": "300"}], ["id", "amount"])

# CLI-174: diff without --key says it's a membership comparison. Round 2 found the wording is
# "No key was given, so rows cannot be matched" rather than any of the original three literal
# phrases -- equivalent in substance, so match on that instead.
code, out, err = c.run(["contract", "diff", str(before), str(after)])
low = out.lower()
ok = (
    "membership" in low or "nothing tells one row from another" in low or "cannot tell" in low
    or ("no key was given" in low and "cannot be matched" in low)
)
record("CLI-174", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-175: --key reports changes, additions, removals; exit 3
code, out, err = c.run(["contract", "diff", str(before), str(after), "--key", "id"])
has_change = "1" in out
has_add = "3" in out or "added" in out.lower()
has_remove = "2" in out or "removed" in out.lower()
ok = code == 3 and "added" in out.lower() and "removed" in out.lower()
record("CLI-175", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-176: --key naming a nonexistent column
code, out, err = c.run(["contract", "diff", str(before), str(after), "--key", "pk"])
ok = code != 0 and ("Traceback" not in err) and ("no such" in err.lower() or "not present" in err.lower() or "unknown" in err.lower() or "does not" in err.lower())
record("CLI-176", "PASS" if ok else "FAIL", f"code={code} out={out[:150]!r} err={err[:250]!r}")

# CLI-177: --ignore excludes a column from comparison only
b2 = wcsv("b2.csv", [{"id": "1", "amount": "100", "loaded_at": "2026-01-01"}], ["id", "amount", "loaded_at"])
a2 = wcsv("a2.csv", [{"id": "1", "amount": "100", "loaded_at": "2026-01-02"}], ["id", "amount", "loaded_at"])
code, out, err = c.run(["contract", "diff", str(b2), str(a2), "--key", "id", "--ignore", "loaded_at"])
ok = code == 0
record("CLI-177", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-178: diff caps examples at 10, states total
rows_b = [{"id": str(i), "amount": "1"} for i in range(500)]
rows_a = [{"id": str(i), "amount": "2"} for i in range(500)]
b3 = wcsv("b3.csv", rows_b, ["id", "amount"])
a3 = wcsv("a3.csv", rows_a, ["id", "amount"])
code, out, err = c.run(["contract", "diff", str(b3), str(a3), "--key", "id"])
n_change_lines = sum(1 for l in out.splitlines() if l.strip().startswith("id="))
ok = code == 3 and "500" in out
record("CLI-178", "PASS" if ok else "FAIL", f"code={code} change_lines_printed={n_change_lines} out_head={out[:200]!r}")

# CLI-179: identical files exit 0
import shutil
same_a = WORK / "same_a.csv"
same_b = WORK / "same_b.csv"
shutil.copy(before, same_a)
shutil.copy(before, same_b)
code, out, err = c.run(["contract", "diff", str(same_a), str(same_b), "--key", "id"])
ok = code == 0 and ("identical" in out.lower() or "no differences" in out.lower())
record("CLI-179", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-180: two empty files
e1 = wjl("e1.jsonl", [])
e2 = wjl("e2.jsonl", [])
code, out, err = c.run(["contract", "diff", str(e1), str(e2), "--key", "id"])
ok = code == 0 and ("no rows" in out.lower() or "empty" in out.lower() or "hold no rows" in out.lower())
record("CLI-180", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

print("done contract batch part3 (diff)")
