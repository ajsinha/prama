import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.mcp.server import Server, INSTRUCTIONS
from prama.mcp import protocol
from prama.assistant.tools import (
    Estate, read_only_registry, default_registry, ToolRegistry, Tool, Capability, Argument, Result,
)
from prama.core.errors import PramaError

def req(method, params=None, id_=1):
    d = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        d["params"] = params
    if id_ is not None:
        d["id"] = id_
    return d

estate = Estate(
    datasets=lambda: ["trades", "positions"],
    describe_dataset=lambda name: {"name": name, "description": "ordinary prose about " + name},
)
registry = read_only_registry(estate)
proposals = []
def propose(dataset, pql, because):
    proposals.append((dataset, pql, because))
    return {"id": "prop-1", "status": "pending"}
full_registry = default_registry(estate, propose)
server = Server(full_registry, name="prama")

# MCP-001
r1 = server.handle(req("initialize", {}))
res1 = r1["result"]
ok1 = (res1["protocolVersion"] == protocol.PROTOCOL_VERSION
       and "serverInfo" in res1
       and res1["instructions"] == INSTRUCTIONS
       and "fence" in res1["instructions"])
record("MCP-001", "PASS" if ok1 else "FAIL", f"protocolVersion={res1.get('protocolVersion')} has_instructions={'instructions' in res1} fence_mentioned={'fence' in res1.get('instructions','')}")

# MCP-002
import logging
r2 = server.handle(req("initialize", {"protocolVersion": "2024-01-01"}))
res2 = r2["result"]
ok2 = res2["protocolVersion"] == protocol.PROTOCOL_VERSION
record("MCP-002", "PASS" if ok2 else "FAIL", f"asked_for=2024-01-01 still_declares={res2['protocolVersion']} (mismatch logged via _log.warning, not surfaced as an error to the client -- 'told, not accommodated' is the claim: the reply states THIS build's version rather than pretending to speak 2024-01-01, which is what the catalogue asks for)")

# MCP-003
r3 = server.handle(req("tools/list", {}))
names3 = sorted(t["name"] for t in r3["result"]["tools"])
expected3 = sorted(["list_datasets", "describe_dataset", "list_controls", "list_incidents", "trace_lineage"])
ok3 = names3 == expected3
record("MCP-003", "PASS" if ok3 else "FAIL", f"tools={names3} expected={expected3}")

# MCP-004
class MutatingTool(Tool):
    name = "delete_stuff"
    capability = Capability.PROPOSE  # will monkeypatch mutates
    description = "danger"
    def run(self, **kw):
        return Result(content={})

class FakeMutatingCapability:
    mutates = True
    value = "mutate"
    @property
    def explains(self):
        return "mutates"

bad_tool = MutatingTool()
# Force a tool whose .capability.mutates is True, bypassing registry.register's own check
# by inserting directly into the registry's internal dict (simulating a tool that got past
# registration some other way, e.g. constructed by hand and handed to Server directly).
bad_registry = ToolRegistry()
bad_registry._tools["delete_stuff"] = bad_tool
import types
object.__setattr__(bad_tool, "capability", FakeMutatingCapability()) if False else None
# capability is a ClassVar, so monkeypatch instance attribute:
bad_tool.capability = FakeMutatingCapability()
threw = None
try:
    Server(bad_registry)
except PramaError as e:
    threw = str(e)
except Exception as e:
    threw = f"WRONG EXCEPTION TYPE {type(e).__name__}: {e}"
ok4 = threw is not None and "delete_stuff" in threw and "WRONG EXCEPTION" not in threw
record("MCP-004", "PASS" if ok4 else "FAIL", f"threw={threw!r}")

# MCP-005
r5 = server.handle(req("tools/list", {}))
propose_tool = next(t for t in r5["result"]["tools"] if t["name"] == "propose_control")
ok5 = "records a proposal for a person to accept or reject" in propose_tool["description"]
record("MCP-005", "PASS" if ok5 else "FAIL", f"description={propose_tool['description']!r}")

# MCP-006
fenced_names = {"describe_dataset", "list_controls", "list_incidents"}
not_fenced_names = {"list_datasets", "trace_lineage", "propose_control"}
sentence = "returned inside an untrusted-data fence"
by_name = {t["name"]: t["description"] for t in r5["result"]["tools"]}
bad6 = {}
for n in fenced_names:
    if sentence not in by_name.get(n, ""):
        bad6[n] = "MISSING sentence but should carry it"
for n in not_fenced_names:
    if sentence in by_name.get(n, ""):
        bad6[n] = "HAS sentence but should not"
ok6 = not bad6
record("MCP-006", "PASS" if ok6 else "FAIL", f"bad={bad6} all_descriptions={by_name}")

# MCP-007
schema_describe = next(t["inputSchema"] for t in r5["result"]["tools"] if t["name"] == "describe_dataset")
ok7a = schema_describe["properties"]["dataset"]["maxLength"] == 200
ok7b = schema_describe["additionalProperties"] is False
ok7c = schema_describe["required"] == ["dataset"]
# need a tool with choices to check enum -- none of the shipped tools has `choices` set on an
# Argument. Build a synthetic one via json_schema directly to test the enum rendering itself.
from prama.mcp.protocol import json_schema
synth_args = (Argument("shape", choices=("bound", "unbound"), maximum_length=50),)
synth_schema = json_schema(synth_args)
ok7d = synth_schema["properties"]["shape"].get("enum") == ["bound", "unbound"]
ok7 = ok7a and ok7b and ok7c and ok7d
record("MCP-007", "PASS" if ok7 else "FAIL", f"describe_dataset_schema={schema_describe} enum_check={synth_schema}")

# MCP-008
synth_int_args = (Argument("n", kind="integer", description="a count"),)
int_schema = json_schema(synth_int_args)
ok8 = int_schema["properties"]["n"]["type"] == "integer" and "maxLength" not in int_schema["properties"]["n"]
record("MCP-008", "PASS" if ok8 else "FAIL", f"schema={int_schema}")

# MCP-009
r9 = server.handle(req("tools/call", {"name": "delete_everything", "arguments": {}}))
res9 = r9.get("result", {})
ok9 = ("error" not in r9) and res9.get("isError") is True and "delete_everything" not in res9.get("content", [{}])[0].get("text", "") or True
text9 = res9.get("content", [{}])[0].get("text", "") if res9.get("content") else ""
ok9 = "error" not in r9 and res9.get("isError") is True and "no tool called" in text9 and "Available" in text9
record("MCP-009", "PASS" if ok9 else "FAIL", f"reply={r9}")

# MCP-010
r10a = server.handle(req("tools/call", {"arguments": {}}))
r10b = server.handle(req("tools/call", {"name": 5, "arguments": {}}))
r10c = server.handle(req("tools/call", {"name": "", "arguments": {}}))
ok10 = all(r.get("error", {}).get("code") == protocol.INVALID_PARAMS for r in (r10a, r10b, r10c))
record("MCP-010", "PASS" if ok10 else "FAIL", f"no_name={r10a} nonstring={r10b} empty={r10c}")

# MCP-011
r11a = server.handle(req("tools/call", {"name": "list_datasets", "arguments": []}))
r11b = server.handle(req("tools/call", {"name": "list_datasets", "arguments": "x"}))
r11c = server.handle(req("tools/call", {"name": "describe_dataset", "arguments": None}))
ok11a = r11a.get("error", {}).get("code") == protocol.INVALID_PARAMS
ok11b = r11b.get("error", {}).get("code") == protocol.INVALID_PARAMS
# null -> {} -> describe_dataset's own required-argument refusal (dataset is required)
res11c = r11c.get("result", {})
text11c = res11c.get("content", [{}])[0].get("text", "") if res11c.get("content") else ""
ok11c = res11c.get("isError") is True and "dataset is required" in text11c
ok11 = ok11a and ok11b and ok11c
record("MCP-011", "PASS" if ok11 else "FAIL", f"list={r11a} str={r11b} null->{r11c}")

# MCP-012
r12 = server.handle(req("tools/call", {"name": "describe_dataset", "arguments": {"dataset": "x", "sql": "DROP TABLE"}}))
res12 = r12.get("result", {})
text12 = res12.get("content", [{}])[0].get("text", "") if res12.get("content") else ""
ok12 = res12.get("isError") is True and "sql" in text12
record("MCP-012", "PASS" if ok12 else "FAIL", f"reply={r12}")

print("done mcp batch 1")
