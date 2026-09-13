import sys, asyncio
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.sql.jdbc import JdbcConnector

JAR = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/dp/mysql-connector-j.jar"
CFG = {
    "dialect": "mysql",
    "jdbc_url": "jdbc:mysql://127.0.0.1:33061/prama?useSSL=false&allowPublicKeyRetrieval=true",
    "driver_class": "com.mysql.cj.jdbc.Driver",
    "driver_path": JAR,
    "user": "prama",
    "password": "prama",
}

async def con108():
    c = JdbcConnector(CFG)
    async with c:
        found = await c.discover()
    ok = len(found) > 0 and all(isinstance(o.estimated_rows, int) or o.estimated_rows is None for o in found)
    types = {o.qualified_name: type(o.estimated_rows).__name__ for o in found}
    log("CON-108", "PASS" if ok else "FAIL", f"discover() succeeded, {len(found)} table(s): {types}")

asyncio.run(con108())
