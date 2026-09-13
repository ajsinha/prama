import sys, os, tempfile, sqlite3, logging, io, asyncio, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.db.settings import DbSettings

def cfg_with(overrides):
    return Configuration(deep_merge(DEFAULTS, overrides))

# CFG-044: echo=true logs SQL
import logging as lg
stream = io.StringIO()
handler = lg.StreamHandler(stream)
sa_logger = lg.getLogger("sqlalchemy.engine")
sa_logger.addHandler(handler)
sa_logger.setLevel(lg.INFO)
async def run_echo():
    from prama.db import Database
    tmp = tempfile.mkdtemp(prefix="cfgqa-44-")
    dbpath = os.path.join(tmp, "d.db")
    cfg = cfg_with({"database": {"sqlite": {"path": dbpath}, "echo": True}})
    settings = DbSettings.from_config(cfg)
    db = Database(settings)
    db.initialise(applied_by="qa")
    await db.start()
    from sqlalchemy import text
    engine = db._engines.async_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await db.stop()
asyncio.run(run_echo())
sa_logger.removeHandler(handler)
out = stream.getvalue()
R("CFG-044", "SELECT 1" in out, f"sqlalchemy.engine log captured {len(out)} bytes; contains SELECT 1={'SELECT 1' in out}")

# CFG-045: schema_dir relocates
import shutil
tmp45 = tempfile.mkdtemp(prefix="cfgqa-45-")
schema_dst = os.path.join(tmp45, "schema")
shutil.copytree(os.path.join(REPO, "schema"), schema_dst)
dbpath45 = os.path.join(tmp45, "d.db")
cfg45 = cfg_with({"database": {"sqlite": {"path": dbpath45}, "schema_dir": schema_dst}})
settings45 = DbSettings.from_config(cfg45)
from prama.db import Database
db45 = Database(settings45)
result45 = db45.initialise(applied_by="qa")
R("CFG-045", str(settings45.schema_file) == os.path.join(schema_dst, "sqlite.sql"), f"schema_file={settings45.schema_file}; init summary={result45.summary()[:80]}")

# CFG-046: missing schema file
from prama.core.errors import DatabaseError
tmp46 = tempfile.mkdtemp(prefix="cfgqa-46-")
empty_schema_dir = os.path.join(tmp46, "emptyschema")
os.makedirs(empty_schema_dir)
dbpath46 = os.path.join(tmp46, "d.db")
cfg46 = cfg_with({"database": {"sqlite": {"path": dbpath46}, "schema_dir": empty_schema_dir}})
settings46 = DbSettings.from_config(cfg46)
db46 = Database(settings46)
try:
    db46.initialise(applied_by="qa")
    R("CFG-046", False, "no exception raised")
except DatabaseError as e:
    ok = e.code == "DB.SCHEMA_FILE_MISSING" and "database.schema_dir" in e.remedy
    R("CFG-046", ok, f"{e.code}: {e.remedy!r}")
except Exception as e:
    R("CFG-046", False, f"{type(e).__name__}: {e}")

# CFG-047: supervisor shutdown_grace honoured
from prama.core.concurrency.supervisor import TaskSupervisor
async def cfg47():
    sup = TaskSupervisor(shutdown_grace=1.0)
    async def stubborn():
        while True:
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                # ignore cancellation, refuse to stop promptly -- but sleep loop still needs to await
                await asyncio.sleep(100)
    sup.spawn("stubborn", stubborn)
    await asyncio.sleep(0.1)
    t0 = time.monotonic()
    await sup.shutdown()
    dt = time.monotonic() - t0
    return dt
try:
    dt = asyncio.run(cfg47())
    R("CFG-047", 0.7 <= dt <= 3.0, f"shutdown() returned after {dt:.2f}s (grace=1.0s)")
except Exception as e:
    R("CFG-047", False, f"{type(e).__name__}: {e}")

# CFG-048: lease provider selection -- Database.lease_provider() ignores
# concurrency.lease.provider entirely and always returns DatabaseLeaseProvider.
from prama.db import Database
cfg48 = cfg_with({"database": {"sqlite": {"path": ":memory:"}}, "concurrency": {"lease": {"provider": "memory"}}})
settings48 = DbSettings.from_config(cfg48)
db48 = Database(settings48)
provider48 = db48.lease_provider()
R("CFG-048", type(provider48).__name__ == "MemoryLeaseProvider",
  f"with concurrency.lease.provider=memory, Database.lease_provider() returned {type(provider48).__name__} "
  f"(config value never read anywhere in src/prama; grep confirms no code branches on lease.provider)")

# CFG-049
from prama.core.concurrency.leases import LeaseSettings
try:
    LeaseSettings(ttl_seconds=10.0, renew_interval_seconds=10.0).validate()
    R("CFG-049", False, "no exception")
except ValueError as e:
    R("CFG-049", "expires between renewals" in str(e), str(e))

# CFG-050
import logging as lg2
logbuf = io.StringIO()
h50 = lg2.StreamHandler(logbuf)
leases_logger = lg2.getLogger("prama.core.concurrency.leases")
leases_logger.addHandler(h50)
leases_logger.setLevel(lg2.WARNING)
LeaseSettings(ttl_seconds=10.0, renew_interval_seconds=6.0).validate()
w1 = "consider ttl" in logbuf.getvalue()
logbuf.truncate(0); logbuf.seek(0)
LeaseSettings(ttl_seconds=30.0, renew_interval_seconds=10.0).validate()
w2 = "consider ttl" in logbuf.getvalue()
leases_logger.removeHandler(h50)
R("CFG-050", w1 and not w2, f"6s/10s warns={w1}; shipped-default 10s/30s warns={w2}")

# CFG-051
from prama.core.concurrency.leases import LeaseProvider, Lease, LeaseHolder
from prama.core.clock import ManualClock
from datetime import datetime, timezone, timedelta
class FakeProvider(LeaseProvider):
    async def acquire(self, resource, holder, ttl_seconds): return None
    async def renew(self, lease, ttl_seconds): return None
    async def release(self, lease): return True
    async def inspect(self, resource): return None
clock = ManualClock(datetime(2026,1,1, tzinfo=timezone.utc))
holder = LeaseHolder(FakeProvider(), "res", settings=LeaseSettings(ttl_seconds=30, renew_interval_seconds=5, clock_skew_allowance_seconds=2.0), clock=clock)
holder._lease = Lease(resource="res", holder="h", token="t", fencing_token=1,
                       acquired_at=clock.now(), expires_at=clock.now()+timedelta(seconds=1))
from prama.core.errors import LeaseLostError
try:
    holder.raise_if_lost()
    R("CFG-051", False, "no LeaseLostError despite skew allowance exceeding remaining validity")
except LeaseLostError as e:
    R("CFG-051", True, f"LeaseLostError as expected: {e}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
