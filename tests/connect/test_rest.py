"""The REST connector, against a real HTTP server.

A stdlib server in a thread, so this is a genuine socket round trip rather than
a mocked client. The things worth testing are all things a mock would have been
told to do: that pagination is followed to the end, that a page cap is
*reported* rather than swallowed, that a 429 is honoured, and that a snapshot
says it is not one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from prama.connect.spi import (
    ConnectorError,
    HealthState,
    SamplePlan,
    SamplingStrategy,
    UnauthorisedError,
)

pytest.importorskip("httpx", reason="needs the 'rest' extra")

from prama.connect.sources.rest import RestConnector

#: Mutable per-test server behaviour, set by the fixtures below.
STATE: dict[str, object] = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        """Quiet. The test output is the interesting part."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if STATE.get("require_token") and self.headers.get("Authorization") != "Bearer s3cret":
            self._send(401, {"error": "unauthorised"})
            return

        if STATE.get("rate_limit_once") and not STATE.get("_limited"):
            STATE["_limited"] = True
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(b"{}")
            return

        if parsed.path.endswith("/notjson"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
            return

        page = int(query.get("page", ["1"])[0])
        total = int(STATE.get("pages", 3))
        # Past the last page the server returns nothing, as a real one does. A
        # test server that keeps inventing rows makes a page-parameter read run
        # to the cap and hides whatever the connector actually did.
        rows = (
            [
                {"id": (page - 1) * 2 + n, "amount": 10.5 + n, "currency": "GBP", "tags": ["a"]}
                for n in range(2)
            ]
            if page <= total
            else []
        )
        if STATE.get("mixed_types") and page == 2:
            rows[0]["amount"] = "eleven"
        body: dict[str, object] = {"data": {"items": rows}}
        if page < total:
            base = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
            body["links"] = {"next": f"{base}/orders?page={page + 1}"}
        elif STATE.get("cycle"):
            base = f"http://{self.server.server_address[0]}:{self.server.server_address[1]}"
            body["links"] = {"next": f"{base}/orders?page=1"}
        self._send(200, body)

    def _send(self, status: int, body: object) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def server() -> Iterator[str]:
    STATE.clear()
    STATE.update({"pages": 3})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def connector(base: str, **config) -> RestConnector:
    settings = {
        "base_url": base,
        "endpoints": ["orders"],
        "records_path": "data.items",
        "next_path": "links.next",
    }
    settings.update(config)
    return RestConnector(settings)


async def read_all(source: RestConnector, path=("orders",), plan=None) -> list[dict]:
    rows: list[dict] = []
    async for batch in source.read(path, plan=plan):
        rows.extend(batch.to_pylist())
    return rows


class TestPaginationIsFollowed:
    async def test_every_page_is_read_not_just_the_first(self, server: str) -> None:
        """A completeness control over the first page of forty passes and means
        nothing."""
        async with connector(server) as source:
            rows = await read_all(source)
        assert len(rows) == 6
        assert {row["id"] for row in rows} == set(range(6))

    async def test_page_numbers_work_when_there_is_no_next_link(self, server: str) -> None:
        async with connector(server, next_path="", page_param="page") as source:
            rows = await read_all(source)
        assert len(rows) == 6

    async def test_a_page_cap_is_reported_not_swallowed(self, server: str) -> None:
        """Stopping early is a fact about the data, and a read that silently
        returns a third of a dataset is worse than one that fails."""
        async with connector(server, page_limit=2) as source:
            rows = await read_all(source)
        assert len(rows) == 4
        assert source.last_read_truncated is True

    async def test_a_complete_read_is_not_marked_truncated(self, server: str) -> None:
        async with connector(server) as source:
            await read_all(source)
        assert source.last_read_truncated is False
        assert source.last_read_pages == 3

    async def test_a_cycling_next_link_terminates(self, server: str) -> None:
        """An endpoint whose next link points back at an earlier page would
        otherwise be read forever, and a hung read is worse than a short one
        because nobody can see it.

        Asserting termination rather than an exact row count, because that is
        what the connector actually guarantees: `/orders` and `/orders?page=1`
        are different strings, so the first lap round a cycle can repeat pages
        before the exact-repeat check fires. The page cap bounds the rest.
        """
        STATE["cycle"] = True
        async with connector(server, page_limit=20) as source:
            rows = await read_all(source)
        assert source.last_read_pages < 20, "the cycle was not detected at all"
        assert rows

    async def test_a_link_pointing_at_itself_stops_immediately(self, server: str) -> None:
        """The exact-repeat case, which the check does catch."""
        STATE["pages"] = 1
        STATE["cycle"] = True
        async with connector(server, page_limit=20) as source:
            await read_all(source)
        assert source.last_read_pages <= 2

    async def test_a_row_limit_stops_early_without_claiming_truncation(self, server: str) -> None:
        plan = SamplePlan(strategy=SamplingStrategy.HEAD, rows=3)
        async with connector(server) as source:
            rows = await read_all(source, plan=plan)
        assert len(rows) == 3
        assert source.last_read_truncated is False


class TestSchemaInference:
    async def test_columns_come_from_the_whole_sample(self, server: str) -> None:
        async with connector(server) as source:
            schema = await source.describe(("orders",))
        assert set(schema.column_names) == {"id", "amount", "currency", "tags"}

    async def test_a_type_disagreement_is_reported_on_the_column(self, server: str) -> None:
        """A schema taken from record one is a type nobody checked."""
        STATE["mixed_types"] = True
        async with connector(server) as source:
            schema = await source.describe(("orders",))
        amount = schema.column("amount")
        assert amount is not None
        assert "arrives as" in amount.comment

    async def test_a_nested_value_becomes_json_text(self, server: str) -> None:
        """Flattening would invent columns the API never promised; dropping it
        would lose a field a control might be about."""
        async with connector(server) as source:
            rows = await read_all(source)
        assert rows[0]["tags"] == '["a"]'


class TestHonestyAboutSnapshots:
    async def test_a_rest_snapshot_is_never_exact(self, server: str) -> None:
        """Evidence carries this flag and replay depends on it: a control
        replayed against a snapshot the API cannot reproduce would give a
        different verdict and blame the data."""
        async with connector(server) as source:
            snapshot = await source.snapshot(("orders",))
        assert snapshot.exact is False
        assert "not a point in time" in snapshot.detail["why_inexact"]

    async def test_it_declares_no_pushdown(self, server: str) -> None:
        async with connector(server) as source:
            assert source.pushdown_capabilities() == ()
            assert source.can_run_controls is False

    async def test_a_predicate_is_refused_not_ignored(self, server: str) -> None:
        """Reading everything and calling it a segment would state one slice's
        rates as the dataset's."""
        plan = SamplePlan(strategy=SamplingStrategy.FULL, predicate="currency = 'GBP'")
        async with connector(server) as source:
            with pytest.raises(ConnectorError, match="cannot apply a predicate"):
                await read_all(source, plan=plan)


class TestTheServerBehavingBadly:
    async def test_a_429_is_honoured_rather_than_failing(self, server: str) -> None:
        """An API saying "slow down" is working correctly."""
        STATE["rate_limit_once"] = True
        async with connector(server) as source:
            rows = await read_all(source)
        assert len(rows) == 6

    async def test_a_401_names_the_scope_not_the_spelling(self, server: str) -> None:
        STATE["require_token"] = True
        async with connector(server) as source:
            with pytest.raises(UnauthorisedError) as caught:
                await read_all(source)
        assert "scope, not its spelling" in caught.value.remedy

    async def test_a_valid_token_is_accepted(self, server: str) -> None:
        STATE["require_token"] = True
        async with connector(server, token="s3cret") as source:
            assert len(await read_all(source)) == 6

    async def test_the_token_goes_in_a_header_not_the_url(self, server: str) -> None:
        """A token in a URL is a token in every access log between here and the
        server."""
        source = connector(server, token="s3cret")
        async with source:
            assert source._headers()["Authorization"] == "Bearer s3cret"

    async def test_a_non_json_response_says_so(self, server: str) -> None:
        async with connector(server, endpoints=["notjson"]) as source:
            with pytest.raises(ConnectorError, match="did not return JSON"):
                await read_all(source, path=("notjson",))


class TestHealthAndDiscovery:
    async def test_a_reachable_api_is_healthy(self, server: str) -> None:
        async with connector(server) as source:
            assert (await source.health()).state is HealthState.HEALTHY

    async def test_an_unreachable_api_says_so(self) -> None:
        async with connector("http://127.0.0.1:1") as source:
            assert (await source.health()).state is HealthState.UNREACHABLE

    async def test_no_base_url_is_misconfiguration_not_unreachability(self) -> None:
        """Different findings: one is the network's problem, one is the form's."""
        async with RestConnector({"endpoints": ["x"]}) as source:
            assert (await source.health()).state is HealthState.MISCONFIGURED

    async def test_a_declined_credential_is_unauthorised_not_unreachable(self, server: str) -> None:
        STATE["require_token"] = True
        async with connector(server) as source:
            assert (await source.health()).state is HealthState.UNAUTHORISED

    async def test_discovery_returns_what_was_configured_and_guesses_nothing(
        self, server: str
    ) -> None:
        """An API does not enumerate itself, and guessing paths would produce
        datasets nobody declared."""
        async with connector(server, endpoints=["orders", "trades"]) as source:
            found = await source.discover()
        assert [o.qualified_name for o in found] == ["orders", "trades"]

    async def test_using_it_unopened_is_a_clear_error(self, server: str) -> None:
        with pytest.raises(ConnectorError, match="before it was opened"):
            await connector(server).health()
