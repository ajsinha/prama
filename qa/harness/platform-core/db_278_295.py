import sys, os, asyncio, tempfile
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.db import Database
from prama.db.settings import DbSettings
from prama.core.config import DEFAULTS
from prama.core.config.configuration import Configuration
from prama.core.config.sources import deep_merge
from prama.db.lease_provider import DatabaseLeaseProvider
from prama.core.clock import ManualClock
from datetime import datetime, UTC, timedelta

def make_db(path):
    cfg = Configuration(deep_merge(DEFAULTS, {"database": {"sqlite": {"path": path}}}))
    return Database(DbSettings.from_config(cfg))

async def main():
    tmp = tempfile.mkdtemp(prefix="dbqa-lease-")
    p = os.path.join(tmp, "d.db")
    db = make_db(p)
    db.initialise(applied_by="qa")
    await db.start()
    engine = db._engines.async_engine()

    clock = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
    providerA = DatabaseLeaseProvider(engine, clock=clock)
    providerB = DatabaseLeaseProvider(engine, clock=clock)

    # DB-278: exactly one grant per contention round, repeated
    grants = []
    for i in range(5):
        clock.advance(100)  # well beyond any TTL so each round starts fresh (resource name varies below anyway)
        resource = f"res278-{i}"
        resA, resB = await asyncio.gather(
            providerA.acquire(resource, "A", 30.0),
            providerB.acquire(resource, "B", 30.0),
        )
        grants.append((resA is not None, resB is not None))
    exactly_one = all((a != b) for a, b in grants)
    R("DB-278", exactly_one, f"grant pairs (A_won, B_won) per round={grants}")

    # DB-280: fencing token strictly increasing across 5 acquisitions by different holders
    tokens = []
    resource280 = "res280"
    for i, holder in enumerate(["h0","h1","h2","h3","h4"]):
        clock.advance(1)
        lease = await providerA.acquire(resource280, holder, 0.5)
        tokens.append(lease.fencing_token)
        await providerA.release(lease)
        clock.advance(1)  # ensure the previous lease is expired so the next holder can take it fresh (release already frees it though)
    R("DB-280", tokens == sorted(tokens) and len(set(tokens)) == 5, f"tokens={tokens}")

    # DB-281: a lost race returns None
    resource281 = "res281"
    leaseA281 = await providerA.acquire(resource281, "A281", 30.0)
    leaseB281 = await providerB.acquire(resource281, "B281", 30.0)
    R("DB-281", leaseA281 is not None and leaseB281 is None, f"A got={leaseA281 is not None}, B got={leaseB281}")

    # DB-282: renewal of a taken-over lease
    clock.advance(31)  # expire A's lease so B can take it
    leaseB282 = await providerB.acquire(resource281, "B282", 30.0)
    renewA282 = await providerA.renew(leaseA281, 30.0)
    R("DB-282", renewA282 is None and leaseB282 is not None, f"A renew after B took over={renewA282}; B acquired={leaseB282 is not None}")

    # DB-283: renewal of an expired-but-not-taken lease
    resource283 = "res283"
    leaseA283 = await providerA.acquire(resource283, "A283", 1.0)
    clock.advance(2)  # expire it, nobody else took it
    renew283 = await providerA.renew(leaseA283, 30.0)
    R("DB-283", renew283 is None, repr(renew283))

    # DB-284: release expires the row rather than deleting; next token continues
    resource284 = "res284"
    lease284a = await providerA.acquire(resource284, "A284", 30.0)
    token_before_release = lease284a.fencing_token
    released = await providerA.release(lease284a)

    # DB-285: release marks the holder -- checked BEFORE any re-acquisition overwrites it
    from sqlalchemy import text as satext
    async with engine.connect() as conn:
        row285 = (await conn.execute(satext("SELECT holder FROM lease WHERE resource=:r"), {"r": resource284})).first()
    R("DB-285", row285 is not None and row285[0].endswith("(released)"), f"holder={row285[0] if row285 else None!r}")

    lease284b = await providerA.acquire(resource284, "A284b", 30.0)
    R("DB-284", released is True and lease284b.fencing_token == token_before_release + 1,
      f"released={released}; token before={token_before_release}, after re-acquire={lease284b.fencing_token}")

    # DB-286: inspect on live vs expired lease, UTC-aware parsing
    resource286 = "res286"
    lease286 = await providerA.acquire(resource286, "A286", 30.0)
    inspected_live = await providerA.inspect(resource286)
    resource286b = "res286b"
    lease286b = await providerA.acquire(resource286b, "A286b", 1.0)
    clock.advance(2)
    inspected_expired = await providerA.inspect(resource286b)
    R("DB-286", inspected_live is not None and inspected_live.acquired_at.tzinfo is not None
      and inspected_live.expires_at.tzinfo is not None and inspected_expired is None,
      f"live inspect={inspected_live is not None} (tz-aware acquired={inspected_live.acquired_at.tzinfo is not None if inspected_live else None}); expired inspect={inspected_expired}")

    # DB-287: purge_before removes only long-expired rows
    resource287_live = "res287-live"
    resource287_old = "res287-old"
    live287 = await providerA.acquire(resource287_live, "A287", 30.0)
    old287 = await providerA.acquire(resource287_old, "A287old", 1.0)
    clock.advance(2)  # expire old287 (but live287's ttl=30s so still valid relative to "now")
    from prama.core.clock import Clock
    cutoff = (clock.now() - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    removed287 = await providerA.purge_before(cutoff)
    async with engine.connect() as conn:
        still_there_live = (await conn.execute(satext("SELECT 1 FROM lease WHERE resource=:r"), {"r": resource287_live})).first()
        still_there_old = (await conn.execute(satext("SELECT 1 FROM lease WHERE resource=:r"), {"r": resource287_old})).first()
    R("DB-287", still_there_live is not None and still_there_old is not None and removed287 == 0,
      f"cutoff was a week ago, neither row is that old yet: removed={removed287}, live row survives={still_there_live is not None}, "
      f"old-but-recent row also survives={still_there_old is not None} (correct: purge only removes rows older than the cutoff, "
      f"and nothing here is a week old)")
    # now actually advance far enough to exercise a real purge
    clock.advance(8 * 86400)
    removed287b = await providerA.purge_before((clock.now() - timedelta(days=7)).isoformat().replace("+00:00", "Z"))
    async with engine.connect() as conn:
        gone_after = (await conn.execute(satext("SELECT 1 FROM lease WHERE resource=:r"), {"r": resource287_old})).first()
    R("DB-287b", removed287b >= 1 and gone_after is None, f"after advancing 8 days and purging with a 7-day cutoff: removed={removed287b}, old row gone={gone_after is None}")

    # DB-288: ISO text comparison across a year boundary and a microsecond boundary
    resource288 = "res288"
    clock_boundary = ManualClock(datetime(2025, 12, 31, 23, 59, 59, 999900, tzinfo=UTC))
    providerC = DatabaseLeaseProvider(engine, clock=clock_boundary)
    leaseC = await providerC.acquire(resource288, "C288", 0.0002)  # expires at 2026-01-01T00:00:00.000100Z-ish
    clock_boundary.advance(0.0005)
    leaseD = await providerC.acquire(resource288, "D288", 30.0)
    R("DB-288", leaseD is not None, f"across a year+microsecond boundary, expired lease was taken over: {leaseD is not None}")

    for id_, res, obs in results:
        print(f"{id_}: {res} :: {obs}")

    await db.stop()

asyncio.run(main())
