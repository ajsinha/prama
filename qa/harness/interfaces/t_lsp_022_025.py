import sys, os, io, json, subprocess
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.lsp import protocol

# LSP-022: malformed JSON on the wire -> $/malformed, ignored; stream stays synchronised
stream = io.BytesIO()
bad_body = b"not json at all"
stream.write(f"Content-Length: {len(bad_body)}\r\n\r\n".encode() + bad_body)
# a genuine JSON value that is not an object (e.g. a bare number)
non_object_body = b"42"
stream.write(f"Content-Length: {len(non_object_body)}\r\n\r\n".encode() + non_object_body)
# a well-formed next message
good_payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}
good_body = json.dumps(good_payload).encode()
stream.write(f"Content-Length: {len(good_body)}\r\n\r\n".encode() + good_body)
stream.seek(0)

m1 = protocol.read_message(stream)
try:
    m2 = protocol.read_message(stream)
    m2_detail = repr(m2)
    m2_crashed = False
except Exception as e:
    m2 = None
    m2_detail = f"UNCAUGHT {type(e).__name__}: {e}"
    m2_crashed = True
if not m2_crashed:
    m3 = protocol.read_message(stream)
else:
    m3 = None
ok22 = m1 is not None and m1.method == "$/malformed" and not m2_crashed and m3 is not None and m3.method == "initialize"
record(
    "LSP-022",
    "PASS" if ok22 else "FAIL",
    f"m1(non-JSON body)={m1} -- correctly becomes $/malformed. "
    f"m2(well-framed body that is valid JSON but NOT an object, e.g. the bare integer 42)={m2_detail} -- "
    + ("CRASHES with an uncaught AttributeError ('int' object has no attribute 'get') inside "
       "read_message() itself, in the PROTOCOL layer, before the server ever gets a chance to catch it -- "
       "this would kill the LSP server process on the next message, taking the editor's session with it, "
       "exactly the failure mode the module docstring warns against" if m2_crashed else "handled without crashing"),
)

# LSP-023: Content-Length is in bytes, not characters
stream2 = io.BytesIO()
protocol.write_message(stream2, {"jsonrpc": "2.0", "method": "test", "params": {"text": "café → 😀"}})
raw = stream2.getvalue()
header_line = raw.split(b"\r\n")[0].decode()
declared_len = int(header_line.split(":")[1].strip())
body_start = raw.index(b"\r\n\r\n") + 4
actual_body = raw[body_start:]
ok23a = declared_len == len(actual_body)  # byte length, not character length
stream2.seek(0)
roundtrip = protocol.read_message(stream2)
ok23b = roundtrip.params.get("text") == "café → 😀"

# mis-declared: declare the CHARACTER count instead of the byte count
text = "café → 😀"
char_len = len(text)  # character count
body3 = json.dumps({"jsonrpc": "2.0", "method": "x", "params": {"t": text}}, ensure_ascii=False).encode("utf-8")
stream3 = io.BytesIO()
stream3.write(f"Content-Length: {char_len}\r\n\r\n".encode("ascii"))  # WRONG (too short vs actual utf-8 bytes)
stream3.write(body3)
# a following, well-formed message, to see if the stream can still recover
stream3.write(f"Content-Length: {len(good_body)}\r\n\r\n".encode() + good_body)
stream3.seek(0)
try:
    mis_declared = protocol.read_message(stream3)
    recovered = protocol.read_message(stream3)
    recovered_ok = recovered is not None and recovered.method == "initialize"
except Exception as e:
    mis_declared = f"EXCEPTION {type(e).__name__}: {e}"
    recovered_ok = False
record(
    "LSP-023",
    "PASS" if (ok23a and ok23b) else "FAIL",
    f"byte_length_correct={ok23a} roundtrip_exact={ok23b} declared_char_len={char_len} "
    f"mis_declared_result={mis_declared!r} stream_recovers_after_mis_declared_length={recovered_ok} "
    f"(recovery is NOT claimed by the catalogue as guaranteed within one framing bug -- 'does not "
    f"permanently desynchronise' is the claim, which a single read may still violate for this one message)",
)

# LSP-024: header block with no Content-Length, and a non-numeric one
stream4 = io.BytesIO(b"X-Something: value\r\n\r\n")
r4 = protocol.read_message(stream4)
stream5 = io.BytesIO(b"Content-Length: abc\r\n\r\n")
r5 = protocol.read_message(stream5)
ok24 = r4 is None and r5 is None
record("LSP-024", "PASS" if ok24 else "FAIL", f"no_content_length_result={r4} non_numeric_result={r5}")

# LSP-025: shutdown then exit is 0; exit alone is 1
def run_sequence(messages):
    req = b""
    for payload in messages:
        body = json.dumps(payload).encode()
        req += f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    proc = subprocess.run(["prama", "lsp", "serve"], input=req, capture_output=True, timeout=30, env=os.environ)
    return proc.returncode


rc_shutdown_then_exit = run_sequence([
    {"jsonrpc": "2.0", "id": 1, "method": "shutdown"},
    {"jsonrpc": "2.0", "method": "exit"},
])
rc_exit_alone = run_sequence([
    {"jsonrpc": "2.0", "method": "exit"},
])
ok25 = rc_shutdown_then_exit == 0 and rc_exit_alone == 1
record("LSP-025", "PASS" if ok25 else "FAIL", f"shutdown_then_exit_rc={rc_shutdown_then_exit} exit_alone_rc={rc_exit_alone}")

print("done lsp batch 3")
