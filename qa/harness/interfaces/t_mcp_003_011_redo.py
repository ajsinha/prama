import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.mcp.server import Server
from prama.mcp import protocol
from prama.assistant.tools import Estate, read_only_registry

def req(method, params=None, id_=1):
    d = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        d["params"] = params
    if id_ is not None:
        d["id"] = id_
    return d

estate = Estate(datasets=lambda: ["trades"], describe_dataset=lambda n: {"name": n})
ro_server = Server(read_only_registry(estate), name="prama")

# MCP-003 redo, against a server constructed with read_only_registry (matches catalogue precondition)
r3 = ro_server.handle(req("tools/list", {}))
names3 = sorted(t["name"] for t in r3["result"]["tools"])
expected3 = sorted(["list_datasets", "describe_dataset", "list_controls", "list_incidents", "trace_lineage"])
ok3 = names3 == expected3
record(
    "MCP-003",
    "PASS" if ok3 else "FAIL",
    f"against a Server(read_only_registry(estate)) as the catalogue's precondition specifies: "
    f"tools={names3} expected={expected3} (my first attempt at this case wrongly used a "
    f"Server(default_registry(...)) which also carries propose_control -- that was a test setup "
    f"mistake on my part, not a product defect: default_registry is documented as 'read plus "
    f"propose, the full surface' and is a separate, intentional constructor from read_only_registry, "
    f"'the default for a Slack or Teams surface'. Corrected and re-run against the right precondition.)",
)

# MCP-011 redo: empty list vs non-empty list vs string vs null, on a full registry (list_datasets has
# no required args so 'accepted' is only visible via the empty-list case)
from prama.assistant.tools import default_registry
proposals = []
full_registry = default_registry(estate, lambda d, p, b: {"id": "x"})
server = Server(full_registry)

r_empty_list = server.handle(req("tools/call", {"name": "list_datasets", "arguments": []}))
r_nonempty_list = server.handle(req("tools/call", {"name": "list_datasets", "arguments": ["a", "b"]}))
r_string = server.handle(req("tools/call", {"name": "list_datasets", "arguments": "x"}))
r_null = server.handle(req("tools/call", {"name": "describe_dataset", "arguments": None}))

empty_list_treated_as_ok = "error" not in r_empty_list and r_empty_list.get("result", {}).get("isError") is False
nonempty_list_rejected = r_nonempty_list.get("error", {}).get("code") == protocol.INVALID_PARAMS
string_rejected = r_string.get("error", {}).get("code") == protocol.INVALID_PARAMS
null_becomes_empty_dict = r_null.get("result", {}).get("isError") is True

# The catalogue says: "the first two [[] and "x"] INVALID_PARAMS; null becomes {}". So [] should ALSO
# be INVALID_PARAMS, same as "x". Observed: [] is falsy, so `arguments or {}` silently turns [] into {},
# same as null -- meaning [] is NOT rejected, contradicting "the first two INVALID_PARAMS".
ok11 = (not empty_list_treated_as_ok) and nonempty_list_rejected and string_rejected and null_becomes_empty_dict
record(
    "MCP-011",
    "PASS" if ok11 else "FAIL",
    f"arguments=[] (empty list) -> {r_empty_list} -- ACCEPTED as if it were {{}} rather than refused with "
    f"INVALID_PARAMS, because `request.params.get('arguments') or {{}}` treats an empty list as falsy and "
    f"silently substitutes {{}}, identically to how null is (correctly, per the catalogue) handled. "
    f"arguments=['a','b'] (non-empty list) -> correctly INVALID_PARAMS ({r_nonempty_list}). "
    f"arguments='x' (string) -> correctly INVALID_PARAMS ({r_string}). "
    f"arguments=null -> correctly becomes {{}} ({r_null}). "
    f"The catalogue's Expected says '[] and \"x\" -> INVALID_PARAMS' but only a NON-empty list or a "
    f"non-empty string actually gets rejected; an empty list silently passes through disguised as null.",
)

print("done mcp 003/011 redo")
