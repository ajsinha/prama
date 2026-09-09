"""Live preview and backtest: what this control will actually do to us.

The studio can already tell an author whether a control is sound. These two
endpoints answer the question that decides whether it gets approved — and, three
weeks later, whether it gets muted:

* **preview** — run it against real data now, and say what it finds.
* **backtest** — run it once per business day over the last month, streaming
  each day as it lands, and say how often it would have fired.

Streamed over Server-Sent Events rather than returned as one response, because
a thirty-day backtest is thirty round trips to a warehouse, and a screen that
shows nothing for forty seconds is a screen people stop waiting for. SSE and
not a WebSocket: the traffic is one-directional, it survives a proxy that has
never heard of an upgrade handshake, and the browser reconnects on its own.

Two properties this file exists to keep:

* **Nothing here writes.** ``prama.execute.preview`` holds no unit of work and
  imports nothing that persists; these routes pass it an executor and a
  generator and never touch the ledger. A preview runs an unapproved control,
  frequently over a bounded scan, and evidence a regulator may read has to be
  the record of a control the estate agreed to, run in full.
* **A stream that stops must say why.** A backtest whose connection dropped and
  one that finished cleanly look identical to a reader watching rows appear, so
  every stream ends with an explicit terminal event carrying the summary — and
  a failure mid-stream arrives as an event, not as a truncated response.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from fastapi import Form, Query, Request
from fastapi.responses import StreamingResponse

from prama.core.clock import utc_now
from prama.core.errors import PramaError
from prama.core.log import get_logger
from prama.execute.preview import Backtest, Preview, Trial, business_dates
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes

_log = get_logger(__name__)

#: The longest backtest the console will run in one go. Not a performance
#: figure: past about a quarter the answer stops being about the control and
#: starts being about how the business changed, and an author reading "4% of
#: days" over eighteen months is reading an average of two different estates.
MAX_PERIODS = 120


class PreviewRoutes(UiRoutes):
    """The two endpoints the studio's preview panel calls."""

    def register(self) -> None:
        self.page(
            "/controls/preview",
            self.control_preview,
            name="control_preview",
            methods=["POST"],
        )
        self.page("/controls/backtest", self.control_backtest, name="control_backtest")

    # -- the source of data -------------------------------------------------

    def _source(self, request: Request) -> tuple[str, str]:
        config = request.app.state.config
        return (
            config.get_str("web.preview.source", ""),
            config.get_str("web.preview.dialect", "duckdb"),
        )

    def _executor(self, request: Request) -> tuple[Callable[[str], Any], Callable[[], None], str]:
        """A query callable over the configured preview source.

        Opened per request and closed after it. A long-lived connection shared
        between requests would be faster and would also mean one author's
        runaway preview blocks everybody else's, which on a screen people use
        while thinking is the worse trade.
        """
        from prama.connect.sources.query import executor_for

        path, dialect = self._source(request)
        execute, close = executor_for(path, dialect)
        return execute, close, dialect

    def _preview(self, request: Request, dialect: str, execute: Callable[[str], Any]) -> Preview:
        return Preview(
            execute=execute,
            engine=dialect,
            max_rows=request.app.state.config.get_int("web.preview.max_rows", 0),
        )

    # -- preview ------------------------------------------------------------

    async def control_preview(
        self,
        request: Request,
        source: Annotated[str, Form()] = "",
    ) -> Any:
        """Run the control against real data now. Returns a fragment."""
        path, _ = self._source(request)
        if not path:
            return render(request, "controls/_preview.html", trial=None, unconfigured=True)

        try:
            execute, close, dialect = self._executor(request)
        except PramaError as exc:
            return render(
                request,
                "controls/_preview.html",
                trial=None,
                unconfigured=False,
                error=str(exc),
                remedy=getattr(exc, "remedy", ""),
            )
        try:
            # In a thread: the driver is synchronous, and running it on the
            # event loop would stall every other request on this worker for as
            # long as the query takes — which for a preview is exactly the
            # cases somebody most wants to see.
            trial = await asyncio.to_thread(self._preview(request, dialect, execute).once, source)
        finally:
            close()
        return render(
            request,
            "controls/_preview.html",
            trial=trial,
            unconfigured=False,
            error="",
            source_path=path,
        )

    # -- backtest -----------------------------------------------------------

    async def control_backtest(
        self,
        request: Request,
        source: Annotated[str, Query()] = "",
        period_column: Annotated[str, Query()] = "",
        days: Annotated[int, Query()] = 0,
    ) -> Any:
        """One event per business day, then a summary. Server-Sent Events.

        A GET because that is what ``EventSource`` speaks, which means the PQL
        arrives in the query string. It is bounded by the server rather than
        trusted: a source too long to be a control is refused before anything
        is opened.
        """
        config = request.app.state.config
        requested = days or config.get_int("web.preview.backtest_days", 30)
        periods = min(max(requested, 1), MAX_PERIODS)
        path, _ = self._source(request)

        if not path:
            return _stream_of(
                _single_error(
                    "no preview source is configured, so a backtest cannot run",
                    "Set web.preview.source to a local .duckdb or .sqlite file.",
                )
            )
        if not period_column.strip():
            return _stream_of(
                _single_error(
                    "a backtest needs the column that carries the business date",
                    "Name it in the studio — as_of_date, business_date, cob_date.",
                )
            )
        if len(source) > 20_000:
            return _stream_of(
                _single_error(
                    "that control is too long to backtest through the browser",
                    "Save it first, then backtest the saved control.",
                )
            )

        return _stream_of(self._backtest_events(request, source, period_column, periods))

    async def _backtest_events(
        self, request: Request, source: str, period_column: str, periods: int
    ) -> AsyncIterator[str]:
        try:
            execute, close, dialect = self._executor(request)
        except PramaError as exc:
            async for event in _single_error(str(exc), getattr(exc, "remedy", "")):
                yield event
            return

        dates = business_dates(utc_now().date(), days=periods)
        trials: list[Trial] = []
        try:
            yield _event(
                "start",
                {
                    "periods": len(dates),
                    "first": dates[0].isoformat(),
                    "last": dates[-1].isoformat(),
                    "engine": dialect,
                },
            )
            preview = self._preview(request, dialect, execute)
            stream = preview.over(source, period_column=period_column, periods=dates)
            abandoned = False
            for index in range(len(dates)):
                if await request.is_disconnected():
                    # The reader left. Stop querying rather than finishing a
                    # backtest into a closed socket — on a warehouse those are
                    # real money, and a preview nobody is watching is the
                    # easiest thing in the system to spend it on.
                    _log.info("backtest abandoned after %d of %d periods", index, len(dates))
                    abandoned = True
                    break
                trial = await asyncio.to_thread(_next_or_none, stream)
                if trial is None:
                    break
                trials.append(trial)
                yield _event("trial", {**trial.to_dict(), "index": index})
            if not abandoned:
                yield _event("summary", Backtest(trials=tuple(trials)).to_dict())
        except PramaError as exc:
            # An event, not a dropped connection. A stream that simply stops
            # and one that finished look the same to somebody watching rows
            # appear, and the first must not be mistaken for the second.
            yield _event("failed", {"message": str(exc), "remedy": getattr(exc, "remedy", "")})
        except Exception as exc:  # pragma: no cover - defensive
            _log.exception("backtest failed")
            yield _event("failed", {"message": f"{type(exc).__name__}: {exc}", "remedy": ""})
        finally:
            close()
        # Outside the finally, deliberately. A yield in a generator's finally
        # runs during close() as well, and a generator that yields while being
        # closed raises rather than tidying up — so the terminal event is sent
        # on the paths that reach the end and the connection simply ends on the
        # path where the reader has already gone.
        yield _event("done", {"completed": len(trials)})


def _next_or_none(stream: Any) -> Trial | None:
    return next(stream, None)


def _event(name: str, payload: dict[str, Any]) -> str:
    """One SSE frame.

    ``json.dumps`` with no newlines in the output, because a raw newline inside
    an SSE data field silently ends the event and the browser receives half a
    payload — the kind of bug that only appears once a control's remedy text
    grows a line break.
    """
    body = json.dumps(payload, default=str).replace("\n", " ")
    return f"event: {name}\ndata: {body}\n\n"


async def _single_error(message: str, remedy: str) -> AsyncIterator[str]:
    yield _event("failed", {"message": message, "remedy": remedy})
    yield _event("done", {"completed": 0})


def _stream_of(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            # Without this a reverse proxy buffers the whole stream and
            # delivers it as one response at the end, which is precisely the
            # experience streaming exists to avoid — and it looks like a bug in
            # the application rather than in the proxy.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


__all__ = ["MAX_PERIODS", "PreviewRoutes"]
