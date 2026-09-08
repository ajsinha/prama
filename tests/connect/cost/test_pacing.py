"""Occupying a production source politely.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from prama.connect.pacing import MAX_PAUSE_SECONDS, LoadPacer
from prama.core.clock import Clock


class TickingClock(Clock):
    """Monotonic time that advances by a fixed step on every reading."""

    def __init__(self, step: float) -> None:
        self._t = 0.0
        self._step = step

    def monotonic(self) -> float:
        value = self._t
        self._t += self._step
        return value

    def now(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def epoch_millis(self) -> int:
        return 0


async def batches(count: int) -> AsyncIterator[int]:
    for n in range(count):
        yield n


class TestTheArithmetic:
    def test_a_five_percent_ceiling_waits_nineteen_times_the_work(self) -> None:
        # To spend a twentieth of the time working, each unit of work is
        # followed by nineteen of waiting.
        assert LoadPacer(0.05).pause_after(1.0) == pytest.approx(19.0)

    def test_a_fifty_percent_ceiling_waits_as_long_as_it_worked(self) -> None:
        assert LoadPacer(0.5).pause_after(2.0) == pytest.approx(2.0)

    def test_a_slow_source_is_backed_off_from_automatically(self) -> None:
        # The property a fixed rate limit does not have: when the database is
        # struggling, batches take longer and Prama waits proportionally longer,
        # rather than continuing to demand the same rows per second.
        pacer = LoadPacer(0.05)
        assert pacer.pause_after(10.0) == 10 * pacer.pause_after(1.0)

    def test_no_ceiling_means_no_waiting(self) -> None:
        assert not LoadPacer(1.0).is_active
        assert not LoadPacer(0.0).is_active
        assert LoadPacer(1.0).pause_after(5.0) == 0.0


class TestPacingAStream:
    @pytest.mark.asyncio
    async def test_every_batch_still_arrives(self) -> None:
        # Pacing slows a read; it must never drop or reorder one.
        pacer = LoadPacer(1.0)
        assert [b async for b in pacer.pace(batches(5))] == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_an_empty_stream_is_not_a_problem(self) -> None:
        assert [b async for b in LoadPacer(0.05).pace(batches(0))] == []

    @pytest.mark.asyncio
    async def test_the_report_says_what_the_pacing_actually_did(self) -> None:
        pacer = LoadPacer(0.5, clock=TickingClock(0.01))
        async for _ in pacer.pace(batches(4)):
            pass
        assert pacer.report.batches == 4
        assert pacer.report.working_seconds > 0
        assert pacer.report.waiting_seconds > 0
        assert 0.4 < pacer.report.achieved_duty_cycle < 0.6

    @pytest.mark.asyncio
    async def test_an_unpaced_read_reports_a_full_duty_cycle(self) -> None:
        pacer = LoadPacer(1.0, clock=TickingClock(0.01))
        async for _ in pacer.pace(batches(3)):
            pass
        assert pacer.report.waiting_seconds == 0.0
        assert pacer.report.achieved_duty_cycle == 1.0

    @pytest.mark.asyncio
    async def test_the_report_serialises_for_the_evidence_record(self) -> None:
        pacer = LoadPacer(0.5, clock=TickingClock(0.01))
        async for _ in pacer.pace(batches(2)):
            pass
        payload = pacer.report.to_dict()
        assert set(payload) == {
            "batches",
            "working_seconds",
            "waiting_seconds",
            "achieved_duty_cycle",
            "capped_pauses",
        }


class TestTheCap:
    def test_one_very_slow_batch_cannot_stall_a_read_for_hours(self) -> None:
        # A 60-second batch under a 1% ceiling implies a 99-minute pause. A read
        # that never finishes is not a polite read — it is a connection held
        # open against production all night.
        pacer = LoadPacer(0.01)
        assert pacer.pause_after(60.0) > MAX_PAUSE_SECONDS

    @pytest.mark.asyncio
    async def test_a_capped_pause_is_recorded_rather_than_hidden(self) -> None:
        # The read then exceeds its declared share, and that fact belongs in
        # the evidence rather than in nobody's knowledge.
        pacer = LoadPacer(0.001, clock=TickingClock(1.0), max_pause_seconds=0.001)
        async for _ in pacer.pace(batches(2)):
            pass
        assert pacer.report.capped_pauses == 2
