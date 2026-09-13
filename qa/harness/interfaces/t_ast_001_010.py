import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.assistant.tools import (
    Capability, Argument, Result, Tool, ToolRegistry, Estate,
    read_only_registry, default_registry, ListDatasets, DescribeDataset, ListControls,
    ListIncidents, TraceLineage, ProposeControl,
)
from prama.assistant.agent import Assistant
from prama.core.errors import ValidationError
from prama.llm.spi import ModelProvider, Request, Response, Hosting

# AST-001
members = list(Capability)
ok1 = set(m.name for m in members) == {"READ", "PROPOSE"} and all(not m.mutates for m in members)
record("AST-001", "PASS" if ok1 else "FAIL", f"members={[m.name for m in members]} mutates={[m.mutates for m in members]}")

# AST-002
class FakeMutCap:
    mutates = True
    value = "mutate"
class BadTool(Tool):
    name = "bad"
    capability = Capability.READ  # will override instance attr below
    description = "x"
    def run(self, **kw):
        return Result(content={})
bad = BadTool()
bad.capability = FakeMutCap()
reg = ToolRegistry()
threw2 = None
try:
    reg.register(bad)
except ValidationError as e:
    threw2 = str(e)
except Exception as e:
    threw2 = f"WRONG TYPE {type(e).__name__}: {e}"
ok2 = threw2 is not None and "WRONG TYPE" not in threw2 and "proposal" in threw2.lower()
record("AST-002", "PASS" if ok2 else "FAIL", f"threw={threw2!r}")

# AST-003
class NamelessTool(Tool):
    name = ""
    capability = Capability.READ
    description = "x"
    def run(self, **kw):
        return Result(content={})
reg3 = ToolRegistry()
threw3 = None
try:
    reg3.register(NamelessTool())
except ValidationError as e:
    threw3 = str(e)
ok3 = threw3 is not None and "NamelessTool" in threw3
record("AST-003", "PASS" if ok3 else "FAIL", f"threw={threw3!r}")

# AST-004
estate = Estate()
ro = read_only_registry(estate)
ok4 = set(ro.names()) == {"list_datasets", "describe_dataset", "list_controls", "list_incidents", "trace_lineage"}
record("AST-004", "PASS" if ok4 else "FAIL", f"names={ro.names()}")

# AST-005
full = default_registry(estate, lambda d, p, b: {})
diff = set(full.names()) - set(ro.names())
ok5 = diff == {"propose_control"}
record("AST-005", "PASS" if ok5 else "FAIL", f"diff={diff}")

# AST-006
class StubProvider(ModelProvider):
    name = "stub"
    hosting = Hosting.SELF_HOSTED
    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = 0
    def complete(self, request):
        self.calls += 1
        text = self._texts.pop(0) if self._texts else "done"
        return Response(text=text, model="stub", provider="stub", request_fingerprint=request.fingerprint)

asst = Assistant(StubProvider(["hello"]), full)
ok6 = asst.can_change_anything is False
# verify it's DERIVED not a hardcoded literal: monkeypatch a tool's capability to mutates=True and see if it flips
class FakeMutCap2:
    mutates = True
saved_cap = full.get("list_datasets").capability
full.get("list_datasets").capability = FakeMutCap2()
derived_flips = Assistant(StubProvider(["x"]), full).can_change_anything is True
full.get("list_datasets").capability = saved_cap
ok6 = ok6 and derived_flips
record("AST-006", "PASS" if ok6 else "FAIL", f"can_change_anything={asst.can_change_anything} derived_flips_when_forced={derived_flips}")

# AST-007
MARK = "MARKER-XYZ-7"
estate7 = Estate(
    datasets=lambda: ["ds1"],
    describe_dataset=lambda n: {"description": MARK},
    controls=lambda ds: [{"reason": MARK}],
    incidents=lambda: [{"note": MARK}],
    lineage=lambda col: [{"detail": MARK}],
)
tools7 = {
    "list_datasets": ListDatasets(estate7),
    "describe_dataset": DescribeDataset(estate7),
    "list_controls": ListControls(estate7),
    "list_incidents": ListIncidents(estate7),
    "trace_lineage": TraceLineage(estate7),
}
flagged = {}
for tname, tool in tools7.items():
    args = {"dataset": "ds1"} if tname in ("describe_dataset", "list_controls") else ({"column": "ds1.a"} if tname == "trace_lineage" else {})
    r = tool.call(args)
    carries_marker = MARK in str(r.content)
    flagged[tname] = {"carries_marker": carries_marker, "returns_untrusted_declared": tool.returns_untrusted, "actual_untrusted": r.untrusted}
mislabeled = {k: v for k, v in flagged.items() if v["carries_marker"] and not v["returns_untrusted_declared"]}
ok7 = not mislabeled
record(
    "AST-007",
    "PASS" if ok7 else "FAIL",
    f"per_tool={flagged} mislabeled_(carries_user_content_but_NOT_flagged_untrusted)={mislabeled} -- "
    f"the catalogue's own Expected explicitly anticipates trace_lineage as the one NOT flagged today, "
    f"'which is not flagged today', i.e. this is a documented/known-in-the-catalogue finding, not a "
    f"surprise -- confirming whether it is still true",
)

# AST-008
class ForcedUntrustedTool(Tool):
    name = "forced"
    capability = Capability.READ
    description = "x"
    returns_untrusted = True
    def run(self, **kw):
        return Result(content="plain", untrusted=False)  # tool's own Result says False
r8 = ForcedUntrustedTool().call({})
ok8 = r8.untrusted is True
record("AST-008", "PASS" if ok8 else "FAIL", f"result.untrusted={r8.untrusted}")

# AST-009: run a full conversation via Assistant.ask and confirm only estate callables were touched
touched = []
def mk(label, ret):
    def f(*a, **kw):
        touched.append((label, a, kw))
        return ret
    return f
estate9 = Estate(
    datasets=mk("datasets", ["ds1"]),
    describe_dataset=mk("describe_dataset", {"description": "x"}),
    controls=mk("controls", []),
    incidents=mk("incidents", []),
    lineage=mk("lineage", []),
    evidence=mk("evidence", {}),
)
reg9 = read_only_registry(estate9)
provider9 = StubProvider([
    'TOOL: {"name": "list_datasets", "arguments": {}}',
    'TOOL: {"name": "describe_dataset", "arguments": {"dataset": "ds1"}}',
    "Final answer using only what I read.",
])
asst9 = Assistant(provider9, reg9)
ans9 = asst9.ask("what datasets exist and describe ds1?")
ok9 = {t[0] for t in touched} <= {"datasets", "describe_dataset"} and len(touched) == 2
record("AST-009", "PASS" if ok9 else "FAIL", f"touched={[t[0] for t in touched]} answer={ans9.text!r}")

# AST-010: default estate returns empty, not an error
default_estate = Estate()
ok10a = default_estate.controls("x") == ()
ok10b = default_estate.incidents() == ()
ok10c = default_estate.lineage("x") == ()
ok10d = default_estate.evidence("x") == {}
ok10 = ok10a and ok10b and ok10c and ok10d
record("AST-010", "PASS" if ok10 else "FAIL", f"controls={default_estate.controls('x')} incidents={default_estate.incidents()} lineage={default_estate.lineage('x')} evidence={default_estate.evidence('x')}")

print("done ast 001-010")
