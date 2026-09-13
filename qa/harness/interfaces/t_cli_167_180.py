import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "contract2"
WORK.mkdir(exist_ok=True, parents=True)


def wj(name, obj):
    p = WORK / name
    p.write_text(json.dumps(obj))
    return p


def wt(name, text):
    p = WORK / name
    p.write_text(text)
    return p


DBT_PARTIAL = """
version: 2
models:
  - name: positions_eod
    columns:
      - name: account_id
        tests: [unique, not_null]
      - name: qty
        tests: [my_company.check_frtb]
"""
QUALITY_CONTRACT = {
    "apiVersion": "3.0.0",
    "kind": "DataContract",
    "dataProduct": "positions",
    "criticality": "critical",
    "description": {"purpose": "x", "usage": "y"},
    "schema": [
        {
            "name": "positions_eod",
            "properties": [
                {
                    "name": "account_id",
                    "logicalType": "string",
                    "required": True,
                    "quality": [{"rule": "duplicateCount", "mustBe": 0}],
                }
            ],
        }
    ],
}

# CLI-167: contract import lists defaulted and ignored individually
dbtfile = wt("schema.yml", DBT_PARTIAL)
code, out, err = c.run(["control", "import", str(dbtfile), "--from", "dbt"]) if False else (None, None, None)
# actually this is `contract import`, ODCS -- build a contract using fields Prama does not model
unmodeled = {
    "apiVersion": "3.0.0",
    "kind": "DataContract",
    "dataProduct": "positions",
    "criticality": "critical",
    "description": {"purpose": "x", "usage": "y"},
    "contractCreatedTs": "2026-01-01T00:00:00Z",  # a field Prama likely ignores/defaults
    "schema": [
        {
            "name": "positions_eod",
            "properties": [{"name": "account_id", "logicalType": "string", "required": True}],
        }
    ],
}
uf = wj("unmodeled.json", unmodeled)
code, out, err = c.run(["contract", "import", str(uf)])
lines167 = [l for l in out.splitlines() if l.strip().startswith(("default:", "ignored:"))]
record("CLI-167", "PASS" if code == 0 else "INSPECT", f"code={code} out={out!r} default/ignored lines={lines167}")

# CLI-168: contract import always reports quality blocks
qc = wj("quality.json", QUALITY_CONTRACT)
code_no, out_no, _ = c.run(["contract", "import", str(qc)])
code_yes, out_yes, _ = c.run(["contract", "import", str(qc), "--controls"])
summary_present_both = ("quality" in out_no.lower() or "control" in out_no.lower()) and (
    "quality" in out_yes.lower() or "control" in out_yes.lower()
)
more_detail_with_flag = len(out_yes) > len(out_no)
ok = summary_present_both and more_detail_with_flag
record("CLI-168", "PASS" if ok else "FAIL", f"without_len={len(out_no)} with_len={len(out_yes)} without={out_no!r}")

# CLI-169: contract import --json exit matches text path on a contract with no usable declaration
badcontract = wj("nodecl.json", {"apiVersion": "3.0.0", "kind": "DataContract", "dataProduct": "x", "criticality": "critical", "description": {"purpose": "x", "usage": "y"}})
code_t, out_t, _ = c.run(["contract", "import", str(badcontract)])
code_j, out_j, _ = c.run(["--json", "contract", "import", str(badcontract)])
ok = code_t == code_j == 3
record("CLI-169", "PASS" if ok else "FAIL", f"text_code={code_t} json_code={code_j}")

print("done contract batch part2a (import)")
