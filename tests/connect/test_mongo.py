"""MongoDB against a real server.

Skipped unless PRAMA_TEST_MONGO_URI names one::

    docker run -d --name prama-mongo -p 37017:27017 \\
      -e MONGO_INITDB_ROOT_USERNAME=prama -e MONGO_INITDB_ROOT_PASSWORD=prama mongo:7
    PRAMA_TEST_MONGO_URI="mongodb://prama:prama@127.0.0.1:37017/?authSource=admin" pytest -q

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import decimal
import os

import pytest

from prama.connect.spi import ConnectorError, HealthState, SamplePlan, SamplingStrategy

URI = os.environ.get("PRAMA_TEST_MONGO_URI", "")

pytestmark = pytest.mark.skipif(not URI, reason="set PRAMA_TEST_MONGO_URI to run against a server")


def connector(**changes):
    from prama.connect.sources.mongo import MongoConnector

    config = {"uri": URI, "database": "prama_test"}
    config.update(changes)
    return MongoConnector(config)


@pytest.fixture(scope="module", autouse=True)
def seeded():
    """A collection whose documents genuinely disagree, because that is the
    case this connector exists to report."""
    from bson.decimal128 import Decimal128
    from pymongo import MongoClient

    client = MongoClient(URI)
    collection = client["prama_test"]["trades"]
    collection.drop()
    collection.insert_many(
        [
            {
                "trade_id": "T1",
                "amount": Decimal128("1953193.464900000000"),
                "ccy": "GBP",
                "quantity": 100,
                "legs": [{"side": "buy"}, {"side": "sell"}],
            },
            {
                "trade_id": "T2",
                "amount": Decimal128("0.005000000000"),
                "ccy": None,
                # A string where the other document has a number. In a
                # relational source the database would have prevented this; here
                # it is the normal state of a collection nobody declared.
                "quantity": "one hundred",
            },
            {"trade_id": "T3", "amount": Decimal128("1.000000000000"), "ccy": "USD"},
        ]
    )
    client.close()
    yield


class TestItWorksAgainstARealServer:
    async def test_it_is_healthy(self) -> None:
        async with connector() as source:
            assert (await source.health()).state is HealthState.HEALTHY

    async def test_collections_are_datasets(self) -> None:
        async with connector() as source:
            found = await source.discover()
        assert [o.qualified_name for o in found] == ["trades"]

    async def test_the_row_estimate_is_free_not_a_scan(self) -> None:
        """`estimated_document_count` reads metadata; `count_documents({})`
        scans, and discovery runs across everything."""
        async with connector() as source:
            found = await source.discover()
        assert found[0].estimated_rows == 3

    async def test_reading_yields_every_document(self) -> None:
        rows = []
        async with connector() as source:
            async for batch in source.read(("trades",)):
                rows.extend(batch.to_pylist())
        assert len(rows) == 3

    async def test_a_sample_plan_bounds_the_read(self) -> None:
        rows = []
        plan = SamplePlan(strategy=SamplingStrategy.HEAD, rows=2)
        async with connector() as source:
            async for batch in source.read(("trades",), plan=plan):
                rows.extend(batch.to_pylist())
        assert len(rows) == 2


class TestTheSchemaIsInferredAndTheDisagreementsAreTheFinding:
    async def test_fields_come_from_the_whole_sample(self) -> None:
        """Taking the first document's keys would produce a schema nobody
        checked — T3 has no `legs` and T1 does."""
        async with connector() as source:
            schema = await source.describe(("trades",))
        assert {"trade_id", "amount", "ccy", "quantity", "legs"} <= set(schema.column_names)

    async def test_a_type_disagreement_is_reported_on_its_field(self) -> None:
        async with connector() as source:
            schema = await source.describe(("trades",))
        quantity = schema.column("quantity")
        assert quantity is not None
        assert "arrives as" in quantity.comment

    async def test_a_field_missing_from_some_documents_says_how_many(self) -> None:
        async with connector() as source:
            schema = await source.describe(("trades",))
        legs = schema.column("legs")
        assert legs is not None
        assert "absent from 2 of 3" in legs.comment
        assert legs.nullable

    async def test_the_sample_size_is_carried(self) -> None:
        """ "No document has this field" and "none of the ones I looked at" are
        different claims, and only one of them is true."""
        async with connector() as source:
            await source.describe(("trades",))
            assert source.last_schema_sample == 3


class TestExactNumbers:
    async def test_decimal128_stays_exact(self) -> None:
        """The obvious conversion is through float, and that is the one that
        loses money — the same trap as JDBC, a different library."""
        rows = []
        async with connector() as source:
            async for batch in source.read(("trades",)):
                rows.extend(batch.to_pylist())
        amounts = {row["trade_id"]: row["amount"] for row in rows}
        assert amounts["T1"] == decimal.Decimal("1953193.464900000000")
        assert isinstance(amounts["T1"], decimal.Decimal)

    async def test_a_nested_document_becomes_json_text(self) -> None:
        """Flattening invents columns the collection never promised and changes
        shape the moment a document nests one level deeper."""
        rows = []
        async with connector() as source:
            async for batch in source.read(("trades",)):
                rows.extend(batch.to_pylist())
        legs = next(r["legs"] for r in rows if r["trade_id"] == "T1")
        assert legs is not None
        assert "buy" in legs and "sell" in legs

    async def test_an_object_id_becomes_a_string(self) -> None:
        rows = []
        async with connector() as source:
            async for batch in source.read(("trades",)):
                rows.extend(batch.to_pylist())
        assert isinstance(rows[0]["_id"], str)

    async def test_a_null_stays_null(self) -> None:
        rows = []
        async with connector() as source:
            async for batch in source.read(("trades",)):
                rows.extend(batch.to_pylist())
        assert next(r["ccy"] for r in rows if r["trade_id"] == "T2") is None


class TestHonestyAboutWhatItCannotDo:
    async def test_it_does_not_claim_to_run_controls(self) -> None:
        """Mongo has an aggregation pipeline; it does not have SQL. Claiming
        otherwise would send a compiled SQL control to a source that cannot
        read one."""
        async with connector() as source:
            assert not source.can_run_controls

    async def test_the_snapshot_is_not_exact(self) -> None:
        async with connector() as source:
            snapshot = await source.snapshot(("trades",))
        assert not snapshot.exact
        assert "replica set" in snapshot.detail["why_inexact"]


class TestRefusals:
    async def test_a_source_with_no_database_is_refused(self) -> None:
        """A deployment holds several, and an estate declared against the wrong
        one is worse than a connection that failed."""
        with pytest.raises(ConnectorError, match="needs a database"):
            await connector(database="").open()

    async def test_using_it_unopened_is_a_clear_error(self) -> None:
        with pytest.raises(ConnectorError, match="before it was opened"):
            await connector().discover()

    async def test_an_unreachable_server_is_reported_as_such(self) -> None:
        async with connector(uri="mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200") as s:
            assert (await s.health()).state is not HealthState.HEALTHY
