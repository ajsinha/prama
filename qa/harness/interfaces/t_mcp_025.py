import sys, os, json, io
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.mcp.server import Server, serve_stdio
from prama.mcp import protocol
from prama.assistant.tools import Estate, read_only_registry

estate = Estate(datasets=lambda: [], describe_dataset=lambda n: {})
server = Server(read_only_registry(estate))

lines = [
    "",  # blank line
    json.dumps([1, 2, 3]),  # JSON array (not an object)
    json.dumps("just a string"),  # JSON string
    "{not valid json,,,",  # invalid JSON
    json.dumps({"jsonrpc": "2.0", "method": "x" * 10_000_000, "id": 1}),  # ~10MB line
    json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 99}),  # valid ping
]
stdin = io.StringIO("\n".join(lines) + "\n")
stdout = io.StringIO()
crashed = None
try:
    serve_stdio(server, stdin, stdout)
except Exception as e:
    crashed = f"{type(e).__name__}: {str(e)[:200]}"

out_lines = [l for l in stdout.getvalue().splitlines() if l.strip()]
replies = []
for l in out_lines:
    try:
        replies.append(json.loads(l))
    except Exception as e:
        replies.append(f"UNPARSEABLE OUTPUT LINE: {l[:200]}")

codes = [r.get("error", {}).get("code") if isinstance(r, dict) else None for r in replies]
ping_reply = next((r for r in replies if isinstance(r, dict) and r.get("id") == 99), None)
ping_ok = ping_reply is not None and "result" in ping_reply

# Expected: blank line skipped (no reply); array -> INVALID_REQUEST; string -> INVALID_REQUEST;
# invalid JSON -> PARSE_ERROR; 10MB line with valid JSON+valid method name should just get METHOD_NOT_FOUND
# (it's a valid object, "x"*10000000 is just an unknown method -- not something serve_stdio itself
# should choke on); final ping answered.
n_replies = len(replies)
has_parse_error = protocol.PARSE_ERROR in codes
has_invalid_request = codes.count(protocol.INVALID_REQUEST) >= 2  # array + string
ok25 = crashed is None and has_parse_error and has_invalid_request and ping_ok
record(
    "MCP-025",
    "PASS" if ok25 else "FAIL",
    f"crashed={crashed} n_input_lines={len(lines)} n_replies={n_replies} error_codes_seen={codes} "
    f"ping_answered={ping_ok} raw_last_2_replies={replies[-2:] if len(replies)>=2 else replies}",
)
print("done mcp025")
