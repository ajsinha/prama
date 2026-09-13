"""A success banner must describe what happened, not what was intended.

QA round 2, `CLI-270` to `CLI-276` and `API-006`. Two shapes of the same
mistake: announcing an outcome before establishing it, and reporting an outcome
somewhere the reader cannot see.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import os
import signal
import socket
import subprocess
import time

import pytest

from prama.cli.base import EXIT_OK, Application
from prama.cli.commands import all_commands


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    try:
        return Application(all_commands()).run(argv, out=out), out.getvalue()
    except Exception:
        return 1, out.getvalue()


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


class TestServeDoesNotAnnounceASuccessItHasNotHad:
    """`CLI-270`, `CLI-271`, `CLI-272`. The banner printed, then the bind failed.

    `--port 99999`, a busy port and an unroutable host each produced a full
    success message — console URL, API URL, docs URL — and then an error. The
    banner was a statement about intent.
    """

    def test_a_port_outside_the_range_is_refused(self) -> None:
        code, output = _run(["serve", "--port", "99999"])
        assert code != EXIT_OK
        assert "Console" not in output, "a success banner for a port that cannot exist"

    def test_a_busy_port_is_refused_before_the_banner(self) -> None:
        holder = socket.socket()
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        try:
            code, output = _run(["serve", "--port", str(holder.getsockname()[1])])
            assert code != EXIT_OK
            assert "Console" not in output
        finally:
            holder.close()

    def test_an_address_this_host_does_not_have_is_refused(self) -> None:
        code, output = _run(["serve", "--host", "10.255.255.1", "--port", str(_free_port())])
        assert code != EXIT_OK
        assert "Console" not in output


@pytest.mark.slow
class TestTheBannerSurvivesARedirect:
    """`CLI-276`. Under any non-tty the banner never appeared at all.

    stdout is line-buffered to a terminal and block-buffered to anything else,
    and the server blocks forever — so under systemd, Docker or
    `prama serve > log`, the banner sat in a buffer nothing ever emptied. That
    is every real production invocation, and the one case nobody had run.
    """

    def test_it_reaches_a_pipe(self) -> None:
        port = _free_port()
        environment = dict(os.environ, PRAMA_SECURITY__SESSION_SECRET="test-only")
        process = subprocess.Popen(
            ["prama", "serve", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=environment,
        )
        try:
            time.sleep(4)
            process.send_signal(signal.SIGINT)
            output, _ = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover - a hung server
            process.kill()
            output, _ = process.communicate()
        assert "Prama" in output
        assert "Console" in output or "API" in output


class TestAnUnhandledExceptionStillCarriesItsCorrelationId:
    """`API-006` (and `Q-24` before it). The one case a user needs to quote.

    `add_exception_handler(Exception, …)` registers on Starlette's outermost
    ServerErrorMiddleware, which sits *outside* the correlating middleware. So
    an unhandled exception propagated out through `call_next`, the header line
    never ran, and the 500 was built beyond the header's reach. Every
    deliberate status — 401, 403, 404, 409, 422 — carried an id, and the one
    that meant "something we did not anticipate" did not.
    """

    async def test_a_route_that_explodes_returns_a_problem_document(
        self, qa_config, estate
    ) -> None:
        import httpx
        from httpx import ASGITransport

        from prama.api import create_app

        app = create_app(qa_config, database=estate)

        @app.get("/api/v1/_regression_boom")
        async def boom() -> None:
            raise RuntimeError("a customer name that must not be echoed")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
            app.router.lifespan_context(app),
        ):
            response = await client.get("/api/v1/_regression_boom")

        assert response.status_code == 500
        assert response.headers.get("X-Correlation-Id")
        assert response.headers["content-type"].startswith("application/problem+json")
        # And the exception's own text stays in the log, where it belongs: an
        # unanticipated message may contain anything, including customer data.
        assert "customer name" not in response.text
