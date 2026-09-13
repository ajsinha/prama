import sys, json, dataclasses, datetime
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.siem import to_ecs, to_cef, render, severity_of, EXPORTABLE_DETAIL, FORMATS, Exported
from prama.security.egress import Gate, ResidencyRefused
from prama.core.errors import ValidationError

@dataclasses.dataclass
class FakeEvent:
    id: str = "01EVT"
    action: str = "control.approve"
    outcome: str = "success"
    tenant_id: str = "t1"
    actor_id: str = "alice"
    actor_kind: str = "principal"
    source_ip: str = "10.0.0.1"
    correlation_id: str = "01COR"
    object_kind: str = "control"
    object_id: str = "ctl-1"
    occurred_at: object = "2026-01-01T00:00:00Z"
    detail_json: object = None

# SEC-113: ECS JSON lines with required field names
evs = [FakeEvent(id=str(i)) for i in range(3)]
exp = to_ecs(evs)
ok = len(exp.lines) == 3
parsed = [json.loads(l) for l in exp.lines]
ok = ok and all("@timestamp" in p and p["event"]["action"] and p["event"]["outcome"] and p["user"]["id"] and p["source"]["ip"] and p["trace"]["id"] for p in parsed)
line("SEC-113", "PASS" if ok else "FAIL", f"n_lines={len(exp.lines)} sample_keys={sorted(parsed[0].keys()) if parsed else []}")

# SEC-114: CEF escapes special chars, one line, round trips
ev_special = FakeEvent(object_id="a=b|c\\d\ne\rf")
exp2 = to_cef([ev_special])
line_text = exp2.lines[0]
one_line = "\n" not in line_text and "\r" not in line_text
# find cs3 (objectId) in extension and check it's escaped
has_escapes = "\\=" in line_text and "\\n" in line_text and "\\r" in line_text and "\\\\" in line_text
line("SEC-114", "PASS" if (one_line and has_escapes) else "FAIL", f"one_line={one_line} has_escapes={has_escapes} rendered={line_text!r}")

# SEC-115: pipe in header field (action) escaped, header still 7 fields
ev_pipe = FakeEvent(action="cont|rol.approve")
exp3 = to_cef([ev_pipe])
header = exp3.lines[0].split("|")
# header fields are CEF:0, product, product, version, action, action, severity -- escaped pipes inside action must not create extra splits
unescaped_pipe_in_action = "cont|rol.approve" in exp3.lines[0]
escaped_present = "cont\\|rol.approve" in exp3.lines[0]
line("SEC-115", "PASS" if (not unescaped_pipe_in_action and escaped_present) else "FAIL", f"header_line={exp3.lines[0]!r}")

# SEC-116: severity derived: denied=8, failure=6, success=2
ok = severity_of("some.action", "denied") == 8 and severity_of("some.action", "failure") == 6 and severity_of("some.action", "success") == 2
line("SEC-116", "PASS" if ok else "FAIL", f"denied={severity_of('x','denied')} failure={severity_of('x','failure')} success={severity_of('x','success')}")

# SEC-117: elevated action outranks outcome
s1 = severity_of("role.grant", "success")
s2 = severity_of("report.read", "failure")
ok = s1 == 7 and s2 == 6 and s1 > s2
line("SEC-117", "PASS" if ok else "FAIL", f"role.grant/success={s1} report.read/failure={s2}")

# SEC-118: evidence.erase is loudest
s_erase = severity_of("evidence.erase", "success")
others = max(severity_of(a, "denied") for a in ["role.grant","principal.create","attestation.sign"])
ok = s_erase == 8 and s_erase >= others
line("SEC-118", "PASS" if ok else "FAIL", f"evidence.erase={s_erase} max_of_others_at_denied={others}")

# SEC-119: unknown outcome doesn't crash, defaults to 2
s3 = severity_of("some.action", "partial")
line("SEC-119", "PASS" if s3 == 2 else "FAIL", f"severity_of(unknown_action, 'partial')={s3}")

# SEC-120: only allow-listed detail keys exported
ev_detail = FakeEvent(detail_json={"dataset": "positions_eod", "password": "hunter2"})
exp4 = to_ecs([ev_detail])
parsed4 = json.loads(exp4.lines[0])
ok = "dataset" in parsed4["prama"] and "password" not in parsed4["prama"] and exp4.dropped_detail_keys == 1
line("SEC-120", "PASS" if ok else "FAIL", f"prama_detail={parsed4['prama']} dropped={exp4.dropped_detail_keys}")

# SEC-121: dropped count reported, described
desc = exp4.describe()
ok = "1" in desc and "not the same as" in desc
line("SEC-121", "PASS" if ok else "FAIL", f"describe={desc!r}")

# SEC-122: non-dict detail handled (string, list, None)
results = []
for bad_detail in ["a string", ["a", "list"], None]:
    ev = FakeEvent(detail_json=bad_detail)
    try:
        e = to_ecs([ev])
        results.append((e.dropped_detail_keys, "ok"))
    except Exception as exc:
        results.append((None, f"CRASHED: {exc}"))
ok = all(r == (0, "ok") for r in results)
line("SEC-122", "PASS" if ok else "FAIL", f"results={results}")

# SEC-123: CEF carries at most six custom strings, drops rest deterministically -- and pins whether cs1-6 or only cs5-6 are usable
ev_many = FakeEvent(detail_json={k: f"v{i}" for i, k in enumerate(sorted(EXPORTABLE_DETAIL)[:8])})
exp5 = to_cef([ev_many])
body = exp5.lines[0]
cs_slots_filled_from_detail = [f"cs{i}Label=" in body for i in range(1, 7)]
# cs1-4 are ALWAYS filled with tenant/objectKind/objectId/correlationId regardless of detail
import re
cs1_label = re.search(r"cs1Label=(\S+)", body).group(1)
cs5_label = re.search(r"cs5Label=(\S+)", body)
cs6_label = re.search(r"cs6Label=(\S+)", body)
cs7_present = "cs7" in body
detail_keys_actually_carried = sum(1 for i in (5,6) if re.search(rf"cs{i}Label=", body))
line("SEC-123", "FAIL" if (cs1_label == "tenant" and detail_keys_actually_carried <= 2) else "PASS",
     f"cs1Label={cs1_label!r} (fixed to 'tenant', not a detail key) cs5Label={cs5_label.group(1) if cs5_label else None} cs6Label={cs6_label.group(1) if cs6_label else None} cs7_present={cs7_present} -- "
     f"of 8 detail keys offered, only {detail_keys_actually_carried} were carried via cs5/cs6 because cs1..cs4 are reserved for tenant/objectKind/objectId/correlationId, "
     f"not available for arbitrary detail keys as the catalogue's Expected ('cs1..cs6 filled') implies")

print("SECTION SEC-113..123 DONE")
