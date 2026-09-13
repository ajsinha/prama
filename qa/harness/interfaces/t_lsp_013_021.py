import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.lsp.server import PqlLanguageServer
from prama.lsp import protocol
from prama.pql.types import Catalogue, Column, DatasetSchema


def msg(method, params=None, id_=None):
    return protocol.Message(method=method, params=params or {}, id=id_)


cat = Catalogue(datasets={"trades": DatasetSchema(name="trades", columns=(Column("a", "TEXT"), Column("b", "TEXT")))})

# LSP-013: a diagnostic with no position (e.g. a suite-level "unchecked" finding
# with no source line) is reported at the top and says so
server13 = PqlLanguageServer()  # no catalogue -> the 'unchecked' finding has a position typically;
# instead force a no-position case: an empty document, or a lint-level finding without a location.
# Use a control referencing a totally undeclared dataset with an empty catalogue, which is what
# ControlCheckCommand's own 'unchecked' finding looks like -- check whether it carries a position.
r13 = server13.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///g.pql", "text": "CHECK nowhere.col IS NOT NULL BECAUSE 'x'"}}))
diags13 = r13[0]["params"]["diagnostics"]
no_position_diags = [d for d in diags13 if d["range"]["start"] == {"line": 0, "character": 0} and d["range"]["end"] == {"line": 0, "character": 0}]
ok13 = any("(no position in the source)" in d["message"] for d in no_position_diags) if no_position_diags else False
record("LSP-013", "PASS" if ok13 else "FAIL", f"diags={diags13}")

# LSP-014: a diagnostic's remedy is appended to the message
ok14 = any("\n" in d["message"] for d in diags13)
record("LSP-014", "PASS" if ok14 else "FAIL", f"messages={[d['message'] for d in diags13]}")

# LSP-015/016: zero length and column 0 -- construct directly via _diagnostics_for with a fake diagnostic
import dataclasses
from prama.pql.types import Finding

server15 = PqlLanguageServer()
server15._documents["file:///h.pql"] = "x"


class FakeDiag:
    def __init__(self, line, column, length, message="msg", remedy="", severity=1, has_position=True):
        self.line = line
        self.column = column
        self.length = length
        self.message = message
        self.remedy = remedy
        self.severity = severity
        self.has_position = has_position


class FakeService:
    def __init__(self, diags):
        self._diags = diags

    def diagnostics(self, text):
        return self._diags

    catalogue = cat


server15._service = FakeService([FakeDiag(line=3, column=5, length=0)])
notif15 = server15._diagnostics_for("file:///h.pql")
d15 = notif15["params"]["diagnostics"][0]
ok15 = d15["range"]["end"]["character"] - d15["range"]["start"]["character"] == 1
record("LSP-015", "PASS" if ok15 else "FAIL", f"range={d15['range']}")

server16 = PqlLanguageServer()
server16._documents["file:///i.pql"] = "x"
server16._service = FakeService([FakeDiag(line=1, column=0, length=1)])
notif16 = server16._diagnostics_for("file:///i.pql")
d16 = notif16["params"]["diagnostics"][0]
ok16 = d16["range"]["start"]["character"] >= 0
record("LSP-016", "PASS" if ok16 else "FAIL", f"range={d16['range']}")

# LSP-017: completion with no catalogue offers keywords/functions only
server17 = PqlLanguageServer()
server17.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///j.pql", "text": "CHECK "}}))
r17 = server17.handle(msg("textDocument/completion", {"textDocument": {"uri": "file:///j.pql"}, "position": {"line": 0, "character": 6}}, id_=9))
items17 = r17[0]["result"]["items"]
ok17 = len(items17) > 0 and r17[0]["result"]["isIncomplete"] is False
record("LSP-017", "PASS" if ok17 else "FAIL", f"n_items={len(items17)} isIncomplete={r17[0]['result']['isIncomplete']} sample={[i['label'] for i in items17[:5]]}")

# LSP-018: completion with a catalogue offers datasets and columns
server18 = PqlLanguageServer(catalogue=cat)
server18.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///k.pql", "text": "CHECK "}}))
r18a = server18.handle(msg("textDocument/completion", {"textDocument": {"uri": "file:///k.pql"}, "position": {"line": 0, "character": 6}}, id_=10))
labels_a = [i["label"] for i in r18a[0]["result"]["items"]]
server18.handle(msg("textDocument/didChange", {"textDocument": {"uri": "file:///k.pql"}, "contentChanges": [{"text": "CHECK trades."}]}))
r18b = server18.handle(msg("textDocument/completion", {"textDocument": {"uri": "file:///k.pql"}, "position": {"line": 0, "character": 13}}, id_=11))
labels_b = [i["label"] for i in r18b[0]["result"]["items"]]
ok18 = "trades" in labels_a and "a" in labels_b and "b" in labels_b
record("LSP-018", "PASS" if ok18 else "FAIL", f"after_CHECK={labels_a[:10]} after_trades.={labels_b[:10]}")

# LSP-019: hover on nothing returns null
server19 = PqlLanguageServer(catalogue=cat)
server19.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///l.pql", "text": "   \n"}}))
r19 = server19.handle(msg("textDocument/hover", {"textDocument": {"uri": "file:///l.pql"}, "position": {"line": 0, "character": 1}}, id_=12))
ok19 = r19[0]["result"] is None
record("LSP-019", "PASS" if ok19 else "FAIL", f"result={r19[0]['result']}")

# LSP-020: hover on a function returns markdown
divergent_pql = "CHECK trades SATISFIES EXCEL '=ROUND(a, 2) > 0'\n  SEVERITY major DIMENSION accuracy BECAUSE 'x'"
server20 = PqlLanguageServer(catalogue=cat)
server20.handle(msg("textDocument/didOpen", {"textDocument": {"uri": "file:///m.pql", "text": divergent_pql}}))
idx = divergent_pql.index("ROUND")
r20 = server20.handle(msg("textDocument/hover", {"textDocument": {"uri": "file:///m.pql"}, "position": {"line": 0, "character": idx + 1}}, id_=13))
result20 = r20[0]["result"]
ok20 = result20 is not None and result20.get("contents", {}).get("kind") == "markdown" and "ROUND" in result20["contents"]["value"]
record("LSP-020", "PASS" if ok20 else "FAIL", f"result={result20}")

# LSP-021: a malformed document produces diagnostics, not a dead server
server21 = PqlLanguageServer()
bad_docs = {
    "random-bytes": "\x00\x01\x02random garbage \xff",
    "5mb": "CHECK " + ("x" * 5_000_000),
    "unbalanced-quotes": "CHECK t.a MATCHES 'unterminated",
    "unterminated-string": "CHECK t.a SATISFIES EXCEL '=A1",
}
bad21 = {}
for label, text in bad_docs.items():
    try:
        r = server21.handle(msg("textDocument/didOpen", {"textDocument": {"uri": f"file:///{label}.pql", "text": text}}))
        if not (len(r) == 1 and r[0]["method"] == "textDocument/publishDiagnostics"):
            bad21[label] = f"unexpected reply shape: {r}"
    except Exception as e:
        bad21[label] = f"exception: {type(e).__name__} {str(e)[:150]}"
# server must still answer the next request
try:
    r_next = server21.handle(msg("initialize", {}, id_=99))
    still_alive = len(r_next) == 1 and "result" in r_next[0]
except Exception as e:
    still_alive = False
ok21 = not bad21 and still_alive
record("LSP-021", "PASS" if ok21 else "FAIL", f"bad={bad21} still_alive_after={still_alive}")

print("done lsp batch 2")
