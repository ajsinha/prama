import sys, json, dataclasses, datetime
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.siem import to_ecs, to_cef, render, Exported
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

# SEC-124: export gated before rendered
gate = Gate.for_tenant("EU", tenant_id="acme-eu")
try:
    render([FakeEvent()], "ecs", gate=gate, collector_region="US", jurisdiction="EU")
    line("SEC-124", "FAIL", "no exception; rendered despite EU-only residency and a US collector")
except ResidencyRefused as e:
    line("SEC-124", "PASS", f"ResidencyRefused: {e}")

# SEC-125: refused export refused wholesale -- confirm no partial Exported object escapes on refusal
try:
    result = render([FakeEvent(), FakeEvent()], "ecs", gate=gate, collector_region="US", jurisdiction="EU")
    line("SEC-125", "FAIL", f"got a result object instead of a refusal: {result}")
except ResidencyRefused:
    line("SEC-125", "PASS", "the whole call raised before any rendering; no partial Exported object was produced")

# SEC-126: unknown format refused with list of known ones
try:
    render([FakeEvent()], "leef")
    line("SEC-126", "FAIL", "no exception for an unknown format")
except ValidationError as e:
    ok = "cef" in str(e) and "ecs" in str(e)
    line("SEC-126", "PASS" if ok else "FAIL", f"ValidationError: {e}")
except Exception as e:
    line("SEC-126", "FAIL", f"wrong exception type {type(e)}: {e}")

# SEC-127: empty event stream renders empty, not a blank line
exp_empty = to_ecs([])
text_empty = exp_empty.text()
line("SEC-127", "PASS" if text_empty == "" else "FAIL", f"text()={text_empty!r}")

# SEC-128: timestamps render as ISO-8601 whether datetime or string
dt = datetime.datetime(2026, 4, 2, 6, 31, 0, tzinfo=datetime.timezone.utc)
ev_dt = FakeEvent(occurred_at=dt)
ev_str = FakeEvent(occurred_at=dt.isoformat())
ecs_dt = json.loads(to_ecs([ev_dt]).lines[0])["@timestamp"]
ecs_str = json.loads(to_ecs([ev_str]).lines[0])["@timestamp"]
cef_dt_line = to_cef([ev_dt]).lines[0]
cef_str_line = to_cef([ev_str]).lines[0]
import re
cef_dt_rt = re.search(r"rt=(\S+)", cef_dt_line).group(1)
cef_str_rt = re.search(r"rt=(\S+)", cef_str_line).group(1)
ok = ecs_dt == ecs_str == dt.isoformat() and cef_dt_rt == cef_str_rt == dt.isoformat()
line("SEC-128", "PASS" if ok else "FAIL", f"ecs_from_datetime={ecs_dt} ecs_from_string={ecs_str} cef_from_datetime={cef_dt_rt} cef_from_string={cef_str_rt}")

print("SECTION SEC-124..128 DONE")
