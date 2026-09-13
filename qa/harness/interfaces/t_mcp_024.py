import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
from prama.mcp.server import Server
from prama.mcp import protocol
from prama.mcp.estate import estate_for
from prama.assistant.tools import default_registry
import api_common as ac
import cli_common as cc

dbpath = str(cc.WORKDIR / "mcp024_unapplied.db")
import sqlite3
conn = sqlite3.connect(dbpath)
conn.execute("SELECT 1")
conn.close()
cfg = ac.sqlite_config(dbpath)
from prama.db import Database
db = Database.from_config(cfg)
# NOTE: deliberately do NOT call db.initialise() -- schema not applied, table absent

tenant_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
mcp_estate = estate_for(db, tenant_id)
mcp_registry = default_registry(mcp_estate, lambda d, p, b: {"id": "x"})
mcp_server = Server(mcp_registry)

def req(method, params=None, id_=1):
    d = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": id_}
    return d

r24 = mcp_server.handle(req("tools/call", {"name": "list_datasets", "arguments": {}}))
detail24 = json.dumps(r24)
mentions_sql = any(kw in detail24 for kw in ["SELECT", "sem_dataset", "sqlalchemy", "OperationalError", "no such table", ".py", "Traceback"])
is_internal_error = r24.get("error", {}).get("code") == protocol.INTERNAL_ERROR
ok24 = is_internal_error and not mentions_sql
record("MCP-024", "PASS" if ok24 else "FAIL", f"reply={r24} mentions_sql_or_internals={mentions_sql}")
print("done mcp024")
