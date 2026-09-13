import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.lsp.server import PqlLanguageServer
from prama.lsp import protocol
from prama.pql.types import Catalogue, Column, DatasetSchema
from prama.version import VERSION


def msg(method, params=None, id_=None):
    return protocol.Message(method=method, params=params or {}, id=id_)


# LSP-001: initialize capabilities
server = PqlLanguageServer()
replies = server.handle(msg("initialize", {}, id_=1))
r = replies[0]
caps = r["result"]["capabilities"]
ok1 = (
    caps.get("textDocumentSync") == 1
    and caps.get("completionProvider", {}).get("triggerCharacters") == ["."]
    and caps.get("hoverProvider") is True
    and r["result"]["serverInfo"]["version"] == VERSION
)
record("LSP-001", "PASS" if ok1 else "FAIL", f"caps={caps} version={r['result']['serverInfo']['version']}")

# LSP-002: catalogue description with and without --catalogue
server_no_cat = PqlLanguageServer()
r_no = server_no_cat.handle(msg("initialize", {}, id_=1))[0]
desc_no = r_no["result"]["serverInfo"]["catalogue"]
cat = Catalogue(datasets={"trades": DatasetSchema(name="trades", columns=(Column("a", "TEXT"),))})
server_with_cat = PqlLanguageServer(catalogue=cat, catalogue_source="cat.json")
r_with = server_with_cat.handle(msg("initialize", {}, id_=1))[0]
desc_with = r_with["result"]["serverInfo"]["catalogue"]
ok2 = "nothing will be checked" in desc_no and "1 dataset(s) from cat.json" == desc_with
record("LSP-002", "PASS" if ok2 else "FAIL", f"without={desc_no!r} with={desc_with!r}")

# LSP-003: initialized is a notification, no reply
r3 = server.handle(msg("initialized", {}))
ok3 = r3 == []
record("LSP-003", "PASS" if ok3 else "FAIL", f"replies={r3}")

# LSP-004: unknown request -> METHOD_NOT_FOUND
r4 = server.handle(msg("textDocument/formatting", {}, id_=5))
ok4 = len(r4) == 1 and r4[0].get("error", {}).get("code") == protocol.METHOD_NOT_FOUND
record("LSP-004", "PASS" if ok4 else "FAIL", f"reply={r4}")

# LSP-005: unknown notification ignored silently
r5 = server.handle(msg("workspace/didChangeConfiguration", {}))
ok5 = r5 == []
record("LSP-005", "PASS" if ok5 else "FAIL", f"replies={r5}")

# LSP-006: didOpen publishes diagnostics immediately
server6 = PqlLanguageServer(catalogue=cat)
r6 = server6.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///a.pql", "text": "CHECK t.a IS NOT NULL SEVERITY urgent\n"}}))
ok6 = len(r6) == 1 and r6[0]["method"] == "textDocument/publishDiagnostics" and len(r6[0]["params"]["diagnostics"]) >= 1
record("LSP-006", "PASS" if ok6 else "FAIL", f"n_diagnostics={len(r6[0]['params']['diagnostics']) if r6 else 0}")

# LSP-007: didChange uses the LAST content change
server7 = PqlLanguageServer()
server7.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///b.pql", "text": "first"}}))
server7.handle(msg("textDocument/didChange", {"textDocument": {"uri": "file:///b.pql"}, "contentChanges": [{"text": "one"}, {"text": "two"}, {"text": "three-final"}]}))
ok7 = server7._documents["file:///b.pql"] == "three-final"
record("LSP-007", "PASS" if ok7 else "FAIL", f"stored={server7._documents.get('file:///b.pql')!r}")

# LSP-008: diagnostics follow a document that changes under the server
good_ctl = "CHECK trades.a IS NOT NULL BECAUSE 'ok'"
bad_ctl_line5 = "\n\n\n\nCHECK trades.a IS NOT NULL SEVERITY urgent\n"
server8 = PqlLanguageServer(catalogue=cat)
r8a = server8.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///c.pql", "text": bad_ctl_line5}}))
diag_before = r8a[0]["params"]["diagnostics"][0]
line_before = diag_before["range"]["start"]["line"]
shifted = "\n\n" + bad_ctl_line5
r8b = server8.handle(msg("textDocument/didChange", {"textDocument": {"uri": "file:///c.pql"}, "contentChanges": [{"text": shifted}]}))
diag_after = r8b[0]["params"]["diagnostics"][0]
line_after = diag_after["range"]["start"]["line"]
ok8 = line_after == line_before + 2
record("LSP-008", "PASS" if ok8 else "FAIL", f"line_before={line_before} line_after={line_after} (expected +2)")

# LSP-009: didChange with empty contentChanges keeps old text, republishes unchanged
server9 = PqlLanguageServer()
server9.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///d.pql", "text": "CHECK t.a IS NOT NULL BECAUSE 'x'"}}))
before_text = server9._documents["file:///d.pql"]
r9 = server9.handle(msg("textDocument/didChange", {"textDocument": {"uri": "file:///d.pql"}, "contentChanges": []}))
after_text = server9._documents["file:///d.pql"]
ok9 = before_text == after_text and len(r9) == 1 and r9[0]["method"] == "textDocument/publishDiagnostics"
record("LSP-009", "PASS" if ok9 else "FAIL", f"unchanged={before_text==after_text} republished={len(r9)==1}")

# LSP-010: didChange for a URI never opened
server10 = PqlLanguageServer()
try:
    r10 = server10.handle(msg("textDocument/didChange", {"textDocument": {"uri": "file:///never.pql"}, "contentChanges": [{"text": "CHECK t.a IS NOT NULL BECAUSE 'x'"}]}))
    ok10 = len(r10) == 1 and server10._documents.get("file:///never.pql") == "CHECK t.a IS NOT NULL BECAUSE 'x'"
    detail10 = f"replies={len(r10)} adopted_text={server10._documents.get('file:///never.pql')!r}"
except Exception as e:
    ok10 = False
    detail10 = f"exception: {type(e).__name__} {e}"
record("LSP-010", "PASS" if ok10 else "FAIL", detail10)

# LSP-011: didClose clears diagnostics
server11 = PqlLanguageServer()
server11.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///e.pql", "text": "CHECK t.a IS NOT NULL SEVERITY urgent"}}))
r11 = server11.handle(msg("textDocument/didClose", {"textDocument": {"uri": "file:///e.pql"}}))
ok11 = r11[0]["params"]["diagnostics"] == [] and r11[0]["params"]["uri"] == "file:///e.pql"
record("LSP-011", "PASS" if ok11 else "FAIL", f"reply={r11}")

# LSP-012: positions convert 1-based -> 0-based exactly once
server12 = PqlLanguageServer()
r12 = server12.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///f.pql", "text": "CHECK t.a IS NOT NULL SEVERITY urgent"}}))
d12 = r12[0]["params"]["diagnostics"][0]
ok12 = d12["range"]["start"]["line"] == 0  # PQL error is on line 1, col ~32; just check line conversion
record("LSP-012", "PASS" if ok12 else "FAIL", f"range={d12['range']}")

print("done lsp batch 1")
