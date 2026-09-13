import sys, os, json, csv
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "contract"
WORK.mkdir(exist_ok=True, parents=True)


def wj(name, obj):
    p = WORK / name
    p.write_text(json.dumps(obj))
    return p


def wt(name, text):
    p = WORK / name
    p.write_text(text)
    return p


CONTRACT = {
    "apiVersion": "3.0.0",
    "kind": "DataContract",
    "dataProduct": "positions",
    "criticality": "critical",
    "description": {"purpose": "EOD positions", "usage": "Risk"},
    "schema": [
        {
            "name": "positions_eod",
            "properties": [
                {"name": "account_id", "logicalType": "string", "required": True},
                {"name": "notional", "logicalType": "number", "required": True},
            ],
        }
    ],
}
contract_json = wj("contract.json", CONTRACT)
good = wj("good.json", [{"account_id": "A1", "notional": 10}, {"account_id": "A2", "notional": 20}])
missing_col = wj("missing.json", [{"account_id": "A1"}, {"account_id": "A2"}])
nulls = wj("nulls.json", [{"account_id": "A1", "notional": 10}, {"account_id": None, "notional": 20}])
extra = wj("extra.json", [{"account_id": "A1", "notional": 10, "new_column": "x"}])
empty = wt("empty.json", "[]")

# CLI-155
code, out, err = c.run(["contract", "check", str(contract_json), "--data", str(good)])
ok = code == 0 and "2" in out
record("CLI-155", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-156
code, out, err = c.run(["contract", "check", str(contract_json), "--data", str(missing_col)])
ok = code == 3 and "BREACH" in out and "notional" in out
record("CLI-156", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-157
code1, out1, _ = c.run(["contract", "check", str(contract_json), "--data", str(extra)])
code2, out2, _ = c.run(["contract", "check", str(contract_json), "--data", str(extra), "--allow-additions"])
ok = code1 == 3 and "BREACH" in out1 and code2 == 0 and "note" in out2
record("CLI-157", "PASS" if ok else "FAIL", f"without={code1}/{out1!r} with={code2}/{out2!r}")

# CLI-158
code, out, err = c.run(["contract", "check", str(contract_json), "--data", str(nulls)])
ok = code == 3 and "empty" in out.lower() and "account_id" in out
record("CLI-158", "PASS" if ok else "FAIL", f"code={code} out={out!r}")

# CLI-159: whitespace-only mandatory value
ws = wj("ws.json", [{"account_id": "  ", "notional": 10}])
code, out, err = c.run(["contract", "check", str(contract_json), "--data", str(ws)])
# code tests `in (None, "")`, so a value of "   " (non-empty) should NOT be flagged -> exit 0
ok = code == 0  # documents the actual (perhaps surprising) behavior
record(
    "CLI-159",
    "PASS" if ok else "FAIL",
    f"code={code} out={out!r} -- '   ' (whitespace) treated as present/non-empty since the code checks "
    f"row.get(name) in (None, ''), not .strip(); this is undocumented anywhere in --help",
)

# CLI-160: zero rows -> exit 3 on both text and JSON path (the fix mentioned in code comments)
code_t, out_t, err_t = c.run(["contract", "check", str(contract_json), "--data", str(empty)])
code_j, out_j, err_j = c.run(["--json", "contract", "check", str(contract_json), "--data", str(empty)])
doc_j = json.loads(out_j)
ok = code_t == 3 and code_j == 3 and doc_j.get("checked") is False
record("CLI-160", "PASS" if ok else "FAIL", f"text_code={code_t} json_code={code_j} json_checked={doc_j.get('checked')}")

# CLI-161: --data accepts .json, .jsonl, .csv with identical verdicts
rows = [{"account_id": "A1", "notional": 10}, {"account_id": "A2", "notional": 20}]
jsonf = wj("rows.json", rows)
jsonlf = wt("rows.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
csvf = WORK / "rows.csv"
with csvf.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["account_id", "notional"])
    writer.writeheader()
    writer.writerows(rows)
results161 = {}
for f in [jsonf, jsonlf, csvf]:
    code, out, err = c.run(["--json", "contract", "check", str(contract_json), "--data", str(f)])
    results161[f.suffix] = (code, json.loads(out).get("breached"))
ok = len({v for v in results161.values()}) == 1
record("CLI-161", "PASS" if ok else "FAIL", f"results={results161}")

# CLI-162: JSON object without 'rows' key
noobj = wj("noobj.json", {"data": rows})
code, out, err = c.run(["contract", "check", str(contract_json), "--data", str(noobj)])
ok = code == 3 and "checked" not in out  # should report "no rows" not silently pass
doc_check = None
code_j, out_j2, _ = c.run(["--json", "contract", "check", str(contract_json), "--data", str(noobj)])
doc_check = json.loads(out_j2)
ok = code == 3 and doc_check.get("rows") == 0 and doc_check.get("checked") is False
record("CLI-162", "PASS" if ok else "FAIL", f"code={code} out={out!r} json={doc_check}")

# CLI-163: CSV header repeats a column. The previous version of this check used a CSV
# ('id,id,amount') that shares NO column at all with the contract's real mandatory schema
# (account_id, notional) -- exit 3 there proves only that those two required columns are
# missing, not anything about how the duplicate 'id' header itself was handled; that breach
# would happen even if duplicate-header parsing were flawless. Test the actual parsing
# function directly, the way round 2's own repro did, and separately confirm a schema-fitting
# duplicate-header CSV surfaces the same behaviour through the real command.
from prama.cli.contract import _rows as _cli_contract_rows

dupcsv = WORK / "dup.csv"
dupcsv.write_text("id,id,amount\n1,2,300\n")
parsed_dup = _cli_contract_rows(str(dupcsv))
last_wins_silently = parsed_dup == [{"id": "2", "amount": "300"}]

dupcsv_fitting = WORK / "dup_fitting.csv"
dupcsv_fitting.write_text("account_id,account_id,notional\nA1,A2,10\n")
code, out, err = c.run(["--json", "contract", "check", str(contract_json), "--data", str(dupcsv_fitting)])
mentions_duplicate = "duplicate" in out.lower() or "duplicate" in err.lower() or "repeat" in out.lower()
ok = not last_wins_silently or mentions_duplicate
record(
    "CLI-163",
    "PASS" if ok else "FAIL",
    f"_rows() on 'id,id,amount' -> {parsed_dup} (silent last-wins={last_wins_silently}) -- "
    f"schema-fitting duplicate ('account_id,account_id,notional') through the real command: "
    f"code={code} out={out[:200]!r} err={err[:150]!r} mentions_duplicate_anywhere={mentions_duplicate}",
)

# CLI-164: directory and unreadable data file
adir = WORK / "adir"
adir.mkdir(exist_ok=True)
code_d, out_d, err_d = c.run(["contract", "check", str(contract_json), "--data", str(adir)])
unreadable = wt("unreadable.json", "[]")
os.chmod(unreadable, 0o000)
is_root = os.geteuid() == 0
if is_root:
    code_u, out_u, err_u = (None, None, "BLOCKED: root")
else:
    code_u, out_u, err_u = c.run(["contract", "check", str(contract_json), "--data", str(unreadable)])
os.chmod(unreadable, 0o644)
ok_d = code_d == 1 and "Traceback" not in err_d
ok_u = is_root or (code_u == 1 and "Traceback" not in err_u)
ok = ok_d and ok_u
record("CLI-164", "PASS" if ok else "FAIL", f"dir: code={code_d} err={err_d[:150]!r} | unreadable: code={code_u} err={err_u[:150] if err_u else ''!r} root={is_root}")

# CLI-165: broken contract syntax names the right format
badyaml = wt("bad.yaml", "a:\n\tb: 1\n")  # tab indent error
badjson = wt("bad.json", '{"a": 1,}')  # trailing comma
code_y, out_y, err_y = c.run(["contract", "check", str(badyaml), "--data", str(good)])
code_j2, out_j3, err_j3 = c.run(["contract", "check", str(badjson), "--data", str(good)])
ok = code_y == 1 and "YAML" in err_y and code_j2 == 1 and "JSON" in err_j3
record("CLI-165", "PASS" if ok else "FAIL", f"yaml: code={code_y} err={err_y[:200]!r} | json: code={code_j2} err={err_j3[:200]!r}")

# CLI-166: contract with no schema block
noschema = wj("noschema.json", {**{k: v for k, v in CONTRACT.items() if k != "schema"}})
code, out, err = c.run(["contract", "check", str(noschema), "--data", str(good)])
ok = code == 1 and "no schema" in err.lower()
record("CLI-166", "PASS" if ok else "FAIL", f"code={code} err={err[:250]!r}")

print("done contract batch part1")
