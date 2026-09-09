"""The studio's preview and its streaming backtest.

Driven against a real DuckDB file through the real application, because the
question a preview answers is "what will this find in my data" and a test with
a stubbed executor would confirm the shape of the answer while saying nothing
about whether it is true.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from prama.api import create_app
from prama.core.clock import utc_now
from prama.core.config import Configuration, ConfigurationBuilder
from prama.db import Database

pytestmark = pytest.mark.anyio

duckdb = pytest.importorskip("duckdb")

NOT_NULL = (
    "CHECK positions.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
)


@pytest.fixture
def warehouse(tmp_path: Path) -> Path:
    """Ten business days ending today, with two bad days and one empty one.

    Dated relative to now, because the backtest asks for the last N business
    days and a fixture with hard-coded dates would pass today and stop testing
    anything the day after.
    """
    path = tmp_path / "warehouse.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE positions (as_of_date VARCHAR, account_id VARCHAR, notional DOUBLE)"
    )
    days: list = []
    cursor = utc_now().date()
    while len(days) < 10:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()

    rows = []
    for index, day in enumerate(days):
        if index == 4:
            continue  # a day with nothing in it at all
        nulls = 3 if index in (2, 6) else 0
        for n in range(20):
            rows.append((day.isoformat(), f"ACC{n:03d}", None if n < nulls else 1000.0 + n))
    connection.executemany("INSERT INTO positions VALUES (?, ?, ?)", rows)
    connection.close()
    return path


def _config(base: Configuration, tenant_id: str, **preview: object) -> Configuration:
    return (
        ConfigurationBuilder()
        .with_defaults(base.raw())
        .with_mapping(
            {
                "tenancy": {"default_tenant": tenant_id},
                "web": {"preview": preview},
            },
            name="preview-test",
        )
        .build()
    )


async def _client(config: Configuration, database: Database) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(config, database=database)
    async with (
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http,
        app.router.lifespan_context(app),
    ):
        yield http


@pytest.fixture
async def studio(
    sqlite_config: Configuration, started_database: Database, tenant_id: str, warehouse: Path
) -> AsyncIterator[httpx.AsyncClient]:
    config = _config(
        sqlite_config, tenant_id, source=str(warehouse), dialect="duckdb", backtest_days=10
    )
    async for client in _client(config, started_database):
        yield client


@pytest.fixture
async def studio_without_data(
    sqlite_config: Configuration, started_database: Database, tenant_id: str
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(_config(sqlite_config, tenant_id, source=""), started_database):
        yield client


def _events(body: str) -> list[tuple[str, dict]]:
    """The SSE frames, parsed. Names and payloads, in order."""
    frames = []
    for block in body.strip().split("\n\n"):
        name, data = "", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if name:
            frames.append((name, json.loads(data) if data else {}))
    return frames


class TestThePreview:
    async def test_it_reports_what_is_in_the_data(self, studio: httpx.AsyncClient) -> None:
        body = " ".join(
            (await studio.post("/controls/preview", data={"source": NOT_NULL})).text.split()
        )
        assert "6</strong> of 180 rows" in body
        assert "verdict-fail" in body

    async def test_it_says_a_preview_is_not_evidence(self, studio: httpx.AsyncClient) -> None:
        """The sentence that stops a reader mistaking this for a run. A reader
        who takes a preview for evidence has been told something false by the
        screen, not by themselves."""
        body = " ".join(
            (await studio.post("/controls/preview", data={"source": NOT_NULL})).text.split()
        )
        assert "A preview is not evidence." in body
        assert "Nothing here was written to the ledger" in body

    async def test_it_shows_the_query_that_ran(self, studio: httpx.AsyncClient) -> None:
        body = (await studio.post("/controls/preview", data={"source": NOT_NULL})).text
        assert "SELECT" in body
        assert "positions" in body

    async def test_an_unrunnable_control_is_not_rendered_as_a_verdict(
        self, studio: httpx.AsyncClient
    ) -> None:
        body = " ".join(
            (
                await studio.post(
                    "/controls/preview",
                    data={
                        "source": "CHECK absent.thing IS NOT NULL SEVERITY major "
                        "DIMENSION completeness BECAUSE 'x'"
                    },
                )
            ).text.split()
        )
        assert "This control could not be run." in body
        assert "nothing here is a statement about the data" in body

    async def test_with_no_source_it_says_so_rather_than_showing_nothing(
        self, studio_without_data: httpx.AsyncClient
    ) -> None:
        """An empty panel reads as a clean result. This is the case where the
        screen must be loudest."""
        body = " ".join(
            (
                await studio_without_data.post("/controls/preview", data={"source": NOT_NULL})
            ).text.split()
        )
        assert "Nothing to preview against." in body
        assert "web.preview.source" in body

    async def test_nothing_reaches_the_ledger(
        self, studio: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The property the whole module is built around, asserted against the
        ledger itself rather than against the type."""
        await studio.post("/controls/preview", data={"source": NOT_NULL})
        async with started_database.unit_of_work() as uow:
            assert await uow.evidence.count_for(tenant_id) == 0
            assert await uow.evidence_runs.recent(tenant_id, limit=10) == []


class TestTheBacktestStream:
    async def _stream(self, client: httpx.AsyncClient, **params: object) -> list[tuple[str, dict]]:
        query = {"source": NOT_NULL, "period_column": "as_of_date", "days": 10}
        query.update(params)
        response = await client.get("/controls/backtest", params=query)
        assert response.headers["content-type"].startswith("text/event-stream")
        return _events(response.text)

    async def test_each_day_arrives_as_its_own_event(self, studio: httpx.AsyncClient) -> None:
        names = [name for name, _ in await self._stream(studio)]
        assert names[0] == "start"
        assert names.count("trial") == 10
        assert names[-1] == "done"

    async def test_the_stream_ends_with_a_terminal_event(self, studio: httpx.AsyncClient) -> None:
        """A stream that stopped and one that finished look identical to
        somebody watching rows appear."""
        names = [name for name, _ in await self._stream(studio)]
        assert names.count("done") == 1
        assert names.index("summary") < names.index("done")

    async def test_the_summary_separates_empty_days_from_quiet_ones(
        self, studio: httpx.AsyncClient
    ) -> None:
        [(_, summary)] = [(n, p) for n, p in await self._stream(studio) if n == "summary"]
        assert summary["evaluated"] == 9
        assert summary["empty"] == 1
        assert summary["alerting"] == 2
        assert "excluded from the rate rather than counted as quiet" in summary["message"]

    async def test_the_empty_day_is_not_reported_as_a_pass(self, studio: httpx.AsyncClient) -> None:
        trials = [p for n, p in await self._stream(studio) if n == "trial"]
        [empty] = [t for t in trials if not t["has_data"]]
        assert empty["verdict"] == "no_data"
        assert not empty["would_alert"]

    async def test_the_expected_volume_is_projected_from_what_was_evaluated(
        self, studio: httpx.AsyncClient
    ) -> None:
        [(_, summary)] = [(n, p) for n, p in await self._stream(studio) if n == "summary"]
        assert summary["alert_rate"] == pytest.approx(2 / 9)
        assert summary["per_30_periods"] == pytest.approx(30 * 2 / 9)

    async def test_a_missing_period_column_is_refused_with_a_reason(
        self, studio: httpx.AsyncClient
    ) -> None:
        """Refused rather than guessed. A backtest of the wrong slices looks
        exactly like a backtest of the right ones."""
        events = await self._stream(studio, period_column="")
        [(_, failure)] = [(n, p) for n, p in events if n == "failed"]
        assert "business date" in failure["message"]
        assert [n for n, _ in events][-1] == "done"

    async def test_no_configured_source_fails_as_an_event(
        self, studio_without_data: httpx.AsyncClient
    ) -> None:
        events = await self._stream(studio_without_data)
        [(_, failure)] = [(n, p) for n, p in events if n == "failed"]
        assert "no preview source is configured" in failure["message"]
        assert "web.preview.source" in failure["remedy"]

    async def test_an_injected_column_name_is_refused_with_a_usable_message(
        self, studio: httpx.AsyncClient
    ) -> None:
        """Not the barrier — the dialect quotes identifiers, so this would
        compile to a column of that name and find nothing. This is the second
        line, and what it buys is an error the author can act on rather than
        "no column named as_of_date; DROP TABLE positions --"."""
        events = await self._stream(studio, period_column="as_of_date; DROP TABLE positions --")
        [(_, failure)] = [(n, p) for n, p in events if n == "failed"]
        assert "not a column name" in failure["message"]
        assert "plain identifier" in failure["remedy"]
        assert not any(n == "trial" for n, _ in events)

    async def test_the_table_is_still_there_afterwards(
        self, studio: httpx.AsyncClient, warehouse: Path
    ) -> None:
        """The assertion that does not depend on the guard above: it holds
        because nothing concatenates caller text into a statement, which is the
        property that has to survive the guard being changed."""
        await self._stream(studio, period_column="as_of_date; DROP TABLE positions --")
        connection = duckdb.connect(str(warehouse), read_only=True)
        assert connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 180
        connection.close()

    async def test_a_control_that_will_not_parse_errors_every_period_not_none(
        self, studio: httpx.AsyncClient
    ) -> None:
        """Not a silent empty stream. "We could not look" must never render as
        "we looked and found nothing"."""
        events = await self._stream(studio, source="CHECK ???")
        trials = [p for n, p in events if n == "trial"]
        assert len(trials) == 10
        assert all(t["error"] for t in trials)
        [(_, summary)] = [(n, p) for n, p in events if n == "summary"]
        assert summary["alert_rate"] is None

    async def test_the_day_count_is_capped(self, studio: httpx.AsyncClient) -> None:
        """Past about a quarter the answer stops being about the control and
        starts being about how the business changed."""
        from prama.web.routes.preview_routes import MAX_PERIODS

        events = await self._stream(studio, days=100_000)
        [(_, start)] = [(n, p) for n, p in events if n == "start"]
        assert start["periods"] == MAX_PERIODS

    async def test_the_stream_is_not_buffered_by_a_proxy(self, studio: httpx.AsyncClient) -> None:
        """Without the header a reverse proxy delivers the whole stream at the
        end, which is exactly what streaming exists to avoid and looks like a
        bug in the application rather than in the proxy."""
        response = await studio.get(
            "/controls/backtest",
            params={"source": NOT_NULL, "period_column": "as_of_date", "days": 1},
        )
        assert response.headers["x-accel-buffering"] == "no"
        assert response.headers["cache-control"] == "no-cache"


class TestTheStudioScreen:
    async def test_the_backtest_panel_is_hidden_when_nothing_can_run(
        self, studio_without_data: httpx.AsyncClient
    ) -> None:
        """A button that always fails teaches people the screen is unreliable."""
        body = (await studio_without_data.get("/controls/studio")).text
        assert "Backtest" not in body
        assert 'id="preview"' in body

    async def test_it_appears_when_a_source_is_configured(self, studio: httpx.AsyncClient) -> None:
        body = (await studio.get("/controls/studio")).text
        assert 'id="backtest"' in body
        assert 'id="period-column"' in body
        assert "an empty day is not a passing day" in body


class TestTheDeclarationSuggestions:
    """Profiling for the declaration form.

    The panel exists to make a form quicker to fill in. The tests are about the
    line it must not cross while doing that: a form arriving already answered is
    a declaration nobody made, and every control derived from it would inherit
    an authority it never earned.
    """

    async def test_it_reports_what_the_table_looks_like(self, studio: httpx.AsyncClient) -> None:
        body = " ".join(
            (await studio.post("/declarations/suggest", data={"name": "positions"})).text.split()
        )
        assert "What the data suggests" in body
        assert "measured over all 180 rows" in body

    async def test_it_says_these_are_observations_not_declarations(
        self, studio: httpx.AsyncClient
    ) -> None:
        body = " ".join(
            (await studio.post("/declarations/suggest", data={"name": "positions"})).text.split()
        )
        assert "These are observations, not declarations." in body
        assert "a field accepted without being read is a statement nobody made" in body

    async def test_it_never_writes_a_declaration(
        self, studio: httpx.AsyncClient, started_database: Database, tenant_id: str
    ) -> None:
        """The endpoint hands the form things a person confirms. What the
        machine observed and what the business declared are the two halves this
        product exists to keep apart."""
        await studio.post("/declarations/suggest", data={"name": "positions"})
        async with started_database.unit_of_work() as uow:
            assert await uow.datasets.count_current(tenant_id) == 0

    async def test_a_table_that_is_not_there_says_nothing_was_read(
        self, studio: httpx.AsyncClient
    ) -> None:
        body = " ".join(
            (await studio.post("/declarations/suggest", data={"name": "absent"})).text.split()
        )
        assert "could not be profiled" in body
        assert "nothing here is a statement about the data" in body

    async def test_an_injected_table_name_is_refused(
        self, studio: httpx.AsyncClient, warehouse: Path
    ) -> None:
        body = (
            await studio.post(
                "/declarations/suggest",
                data={"name": "positions; DROP TABLE positions --"},
            )
        ).text
        assert "not a table name" in body
        connection = duckdb.connect(str(warehouse), read_only=True)
        assert connection.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 180
        connection.close()

    async def test_with_no_source_the_button_is_not_offered(
        self, studio_without_data: httpx.AsyncClient
    ) -> None:
        body = (await studio_without_data.get("/declarations/new")).text
        assert "See what the data suggests" not in body

    async def test_it_is_offered_when_a_source_is_configured(
        self, studio: httpx.AsyncClient
    ) -> None:
        body = " ".join((await studio.get("/declarations/new")).text.split())
        assert "See what the data suggests" in body
        assert "Nothing it finds is declared until you submit this form." in body
