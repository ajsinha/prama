"""Occupying a production source politely.

A read policy can declare a ``load_ceiling``: the fraction of wall-clock time
Prama is permitted to keep a source busy. 0.05 means that after a batch which
took 100ms, the reader waits until roughly two seconds have passed before asking
for the next one. Over any window, Prama is working the source about five
percent of the time.

Duty cycle rather than a rate limit, deliberately. A rate limit in rows or bytes
per second requires knowing what the source can do, which nobody knows and which
changes with the hour and the query. A duty cycle needs no such knowledge: it is
measured against the source's own demonstrated speed. If the database is fast,
Prama reads fast and waits proportionally; if the database is struggling,
batches take longer and Prama automatically backs further off — which is exactly
the behaviour wanted, and the opposite of what a fixed rate limit does.

The alternative is what most tools do: read as fast as the source allows, and
rely on somebody noticing. That works until the one morning it does not, and
after that the tool is banned from production.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from typing import TypeVar

from prama.core.clock import Clock, SystemClock
from prama.core.log import get_logger

_log = get_logger(__name__)

T = TypeVar("T")

#: Never sleep longer than this between batches, whatever the arithmetic says.
#: A single very slow batch under a tight ceiling would otherwise stall a read
#: for hours, and a read that never finishes is not a polite read — it is a
#: connection held open against a production database all night.
MAX_PAUSE_SECONDS = 30.0

#: Below this, the pause costs more in scheduling than it saves in load.
MIN_PAUSE_SECONDS = 0.001


@dataclasses.dataclass(slots=True)
class PacingReport:
    """What the pacing actually did. Recorded with the read's evidence."""

    batches: int = 0
    working_seconds: float = 0.0
    waiting_seconds: float = 0.0
    capped_pauses: int = 0

    @property
    def elapsed_seconds(self) -> float:
        return self.working_seconds + self.waiting_seconds

    @property
    def achieved_duty_cycle(self) -> float:
        """The fraction of time actually spent working the source."""
        return self.working_seconds / self.elapsed_seconds if self.elapsed_seconds else 0.0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "batches": self.batches,
            "working_seconds": round(self.working_seconds, 3),
            "waiting_seconds": round(self.waiting_seconds, 3),
            "achieved_duty_cycle": round(self.achieved_duty_cycle, 4),
            "capped_pauses": self.capped_pauses,
        }


class LoadPacer:
    """Keeps a read within its declared share of a source's time."""

    def __init__(
        self,
        ceiling: float,
        *,
        clock: Clock | None = None,
        max_pause_seconds: float = MAX_PAUSE_SECONDS,
    ) -> None:
        #: 0 or >= 1 means no pacing. A ceiling of 1.0 is "read as fast as the
        #: source allows", which is a legitimate choice for a replica or an
        #: extract and a poor one for a production primary.
        self._ceiling = ceiling
        self._clock = clock or SystemClock()
        self._max_pause = max_pause_seconds
        self.report = PacingReport()

    @property
    def is_active(self) -> bool:
        return 0.0 < self._ceiling < 1.0

    def pause_after(self, working_seconds: float) -> float:
        """How long to wait after a batch that took *working_seconds*.

        To spend a fraction ``c`` of the time working, each unit of work is
        followed by ``work * (1/c - 1)`` of waiting.
        """
        if not self.is_active or working_seconds <= 0:
            return 0.0
        return working_seconds * (1.0 / self._ceiling - 1.0)

    async def pace(self, batches: AsyncIterator[T]) -> AsyncIterator[T]:
        """Yield from *batches*, waiting between them to hold the duty cycle.

        The wait happens *after* a batch is handed to the caller, so a consumer
        that is itself slow is not punished twice — its own processing time is
        time the source is not being worked.
        """
        while True:
            started = self._clock.monotonic()
            try:
                item = await anext(batches)
            except StopAsyncIteration:
                return
            working = self._clock.monotonic() - started
            self.report.batches += 1
            self.report.working_seconds += working
            yield item
            await self._wait(working)

    async def _wait(self, working_seconds: float) -> None:
        pause = self.pause_after(working_seconds)
        if pause < MIN_PAUSE_SECONDS:
            return
        if pause > self._max_pause:
            self.report.capped_pauses += 1
            _log.debug(
                "pacing pause of %.1fs capped at %.1fs; a batch took %.1fs against a "
                "%.0f%% ceiling, so the read will exceed its share",
                pause,
                self._max_pause,
                working_seconds,
                self._ceiling * 100,
            )
            pause = self._max_pause
        self.report.waiting_seconds += pause
        await asyncio.sleep(pause)
