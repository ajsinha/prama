import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.agent.residency import ResidencyPolicy, SampleDisposition, Boundary, _fingerprint
from prama.core.errors import ValidationError

# AGT-043: WITHHOLD sends nothing, names zone and investigate_at
policy43 = ResidencyPolicy(zone="pci-zone", samples=SampleDisposition.WITHHOLD, investigate_at="the pci-zone jump host")
boundary43 = Boundary(policy43)
rows43 = [{"a": i} for i in range(10)]
red43 = boundary43.apply(rows43)
ok43 = red43.rows == () and red43.withheld == 10 and "pci-zone" in red43.reason and "the pci-zone jump host" in red43.reason
record("AGT-043", "PASS" if ok43 else "FAIL", f"rows={red43.rows} withheld={red43.withheld} reason={red43.reason!r}")

# AGT-044: withheld sample distinguishable from no failing rows
red44_failing = boundary43.apply([{"a": 1}])
red44_none = boundary43.apply([])
ok44 = red44_failing.reason != red44_none.reason and "does not permit" in red44_failing.reason and "no failing rows" in red44_none.reason
record("AGT-044", "PASS" if ok44 else "FAIL", f"failing_reason={red44_failing.reason!r} none_reason={red44_none.reason!r}")

# AGT-045: MASK masks everything not explicitly permitted
policy45 = ResidencyPolicy(zone="z45", samples=SampleDisposition.MASK, may_send=("account_id",))
boundary45 = Boundary(policy45)
rows45 = [{"account_id": "ACC1", "pan": "4111111111111111", "new_column_since_policy": "surprise"}]
red45 = boundary45.apply(rows45)
row_out = red45.rows[0]
ok45 = row_out["account_id"] == "ACC1" and row_out["pan"] == "***" and row_out["new_column_since_policy"] == "***" and set(red45.masked) == {"pan", "new_column_since_policy"}
record("AGT-045", "PASS" if ok45 else "FAIL", f"row_out={row_out} masked={red45.masked}")

# AGT-046: never_send overrides may_send
policy46 = ResidencyPolicy(zone="z46", samples=SampleDisposition.MASK, may_send=("account_id", "pan"), never_send=("pan",))
boundary46 = Boundary(policy46)
rows46 = [{"account_id": "A1", "pan": "4111"}]
red46 = boundary46.apply(rows46)
row46 = red46.rows[0]
ok46 = row46["account_id"] == "A1" and row46["pan"] == "***" and boundary46.permits("pan") is False and boundary46.permits("account_id") is True
record("AGT-046", "PASS" if ok46 else "FAIL", f"row={row46} permits_pan={boundary46.permits('pan')} permits_account_id={boundary46.permits('account_id')}")

# AGT-047: case-insensitive column matching
policy47 = ResidencyPolicy(zone="z47", samples=SampleDisposition.MASK, may_send=("account_id",), never_send=("PAN",))
boundary47 = Boundary(policy47)
rows47 = [{"ACCOUNT_ID": "A1", "pan": "4111"}]
red47 = boundary47.apply(rows47)
row47 = red47.rows[0]
ok47 = row47["ACCOUNT_ID"] == "A1" and row47["pan"] == "***"
record("AGT-047", "PASS" if ok47 else "FAIL", f"row={row47}")

# AGT-048: SEND with a never_send list refused at declaration
threw48 = None
try:
    ResidencyPolicy(zone="z48", samples=SampleDisposition.SEND, never_send=("pan",))
except ValidationError as e:
    threw48 = str(e)
ok48 = threw48 is not None and "MASK" in threw48
record("AGT-048", "PASS" if ok48 else "FAIL", f"error={threw48!r}")

# AGT-049: MASK with empty allow-list refused
threw49 = None
try:
    ResidencyPolicy(zone="z49", samples=SampleDisposition.MASK, may_send=())
except ValidationError as e:
    threw49 = str(e)
ok49 = threw49 is not None and "WITHHOLD" in threw49
record("AGT-049", "PASS" if ok49 else "FAIL", f"error={threw49!r}")

# AGT-050: FINGERPRINT reveals nothing, is stable, differs on real difference
policy50 = ResidencyPolicy(zone="z50", samples=SampleDisposition.FINGERPRINT)
boundary50 = Boundary(policy50)
row_a = {"account_id": "A1", "amount": 100}
row_b = {"account_id": "A1", "amount": 100}
row_c = {"account_id": "A1", "amount": 101}
red50 = boundary50.apply([row_a, row_b, row_c])
fps = [r["fingerprint"] for r in red50.rows]
no_original_value = all("A1" not in str(r) and "100" not in str(r) and "101" not in str(r) for r in red50.rows)
ok50 = fps[0] == fps[1] and fps[0] != fps[2] and no_original_value
record("AGT-050", "PASS" if ok50 else "FAIL", f"fingerprints={fps} no_original_value_present={no_original_value}")

# AGT-051: fingerprint stable across key order
fp1 = _fingerprint({"a": 1, "b": 2, "c": 3})
fp2 = _fingerprint({"c": 3, "a": 1, "b": 2})
ok51 = fp1 == fp2
record("AGT-051", "PASS" if ok51 else "FAIL", f"fp1={fp1} fp2={fp2}")

# AGT-052: max_sample_rows caps and overflow counted, under MASK/SEND/FINGERPRINT
rows52 = [{"account_id": f"A{i}"} for i in range(200)]
res52 = {}
for disp, extra in [
    (SampleDisposition.MASK, {"may_send": ("account_id",)}),
    (SampleDisposition.SEND, {}),
    (SampleDisposition.FINGERPRINT, {}),
]:
    p = ResidencyPolicy(zone="z52", samples=disp, max_sample_rows=50, **extra)
    b = Boundary(p)
    red = b.apply(rows52)
    res52[disp.value] = {"n_rows": len(red.rows), "withheld": red.withheld}
ok52 = all(v["n_rows"] == 50 and v["withheld"] == 150 for v in res52.values())
record("AGT-052", "PASS" if ok52 else "FAIL", f"per_disposition={res52}")

# AGT-053: mask token fixed at ***
ok53 = Boundary.MASK == "***"
record("AGT-053", "PASS" if ok53 else "FAIL", f"MASK={Boundary.MASK!r}")

print("done agt 043-053")
