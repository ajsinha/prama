import asyncio, sys
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.sources.mongo import MongoConnector
from prama.connect.spi import SamplePlan

DOCS = [
    {"trade_id": "T1", "d": "2026-04-01"},
    {"trade_id": "T2", "d": "2026-04-01"},
    {"trade_id": "T3", "d": "2026-04-02"},
    {"trade_id": "T4", "d": "2026-04-02"},
    {"trade_id": "T5", "d": "2026-04-03"},
    {"trade_id": "T6", "d": "2026-04-03"},
]

class FakeCursor:
    def __init__(self, docs):
        self._docs = docs
        self._limit = None
    def limit(self, n):
        self._limit = n
        return self
    def __aiter__(self):
        docs = self._docs if self._limit is None else self._docs[: self._limit]
        async def gen():
            for d in docs:
                yield d
        return gen()

class FakeCollection:
    def __init__(self, docs):
        self._docs = docs
        self.find_calls = []
    def find(self, query):
        self.find_calls.append(query)
        # A real MongoDB driver would apply the filter; this fake reports what
        # a correct implementation would return if the predicate were actually
        # translated and applied ($eq on "d"). Since production code always
        # passes {} (per CON-014's hypothesis), record what it actually sent
        # and always return the whole collection to make the row-count
        # consequence visible.
        return FakeCursor(self._docs)

class FakeDB(dict):
    def __getitem__(self, name):
        return self.setdefault(name, FakeCollection(DOCS))

async def main():
    from prama.connect.spi import ConnectorError
    c = MongoConnector({"uri": "mongodb://x", "database": "d"})
    fake_db = FakeDB()
    c._client = {"d": fake_db}  # so self._client[self._database] -> fake_db
    plan = SamplePlan(predicate="d = '2026-04-01'")
    rows = []
    try:
        async for batch in c.read(("trades",), plan=plan):
            rows.extend(batch.to_pylist())
    except ConnectorError as e:
        # require_predicate_support() now raises before find() is ever reached
        # (pushdown_capabilities() is empty), so the fake collection's find()
        # is never called at all -- a stronger failure than "wrong rows
        # returned", not something the original script's happy path caught.
        log(
            "CON-014",
            "FAIL",
            f"raised {e.code} instead of returning filtered rows: {e}",
        )
        return
    coll = fake_db["trades"]
    log(
        "CON-014",
        "FAIL" if len(rows) != 2 else "PASS",
        f"find() called with query={coll.find_calls}; predicate='{plan.predicate}' requested "
        f"but rows returned={len(rows)} (of {len(DOCS)} total) -- "
        f"{'confirmed: find({}) issued, whole collection read despite declared PREDICATE_PUSHDOWN' if coll.find_calls == [{}] else 'predicate was applied'}",
    )

asyncio.run(main())
