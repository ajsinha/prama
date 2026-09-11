"""A worker pinned to one thread.

The one place this codebase allows a raw thread outside its original
concurrency primitives, so the properties that make it safe are asserted rather
than assumed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import threading

import pytest

from prama.core.concurrency import DedicatedThread
from prama.core.errors import PramaError


class TestItIsOneThread:
    async def test_every_call_runs_on_the_same_thread(self) -> None:
        """The whole point. A library that is thread-*bound* rather than merely
        thread-unsafe deadlocks when used from a second thread, and does not
        raise."""
        worker = DedicatedThread(name="probe")
        try:
            seen = {await worker.call(threading.get_ident) for _ in range(25)}
        finally:
            await worker.close()
        assert len(seen) == 1

    async def test_it_is_not_the_caller_s_thread(self) -> None:
        worker = DedicatedThread(name="probe")
        try:
            assert await worker.call(threading.get_ident) != threading.get_ident()
        finally:
            await worker.close()

    async def test_two_workers_do_not_share_a_thread(self) -> None:
        """One thread per resource. Sharing would reintroduce exactly the
        problem — two JDBC connections on one JVM-attached thread."""
        first, second = DedicatedThread(name="a"), DedicatedThread(name="b")
        try:
            assert await first.call(threading.get_ident) != await second.call(threading.get_ident)
        finally:
            await first.close()
            await second.close()


class TestTeardownRunsOnTheWorker:
    async def test_the_teardown_hook_runs_on_the_worker_thread(self) -> None:
        """Finalising from the caller's thread is the bug this class exists to
        prevent, and it surfaces at interpreter exit rather than anywhere a
        stack trace would help."""
        worker = DedicatedThread(name="probe")
        worker_thread = await worker.call(threading.get_ident)
        finalised: list[int] = []
        await worker.close(teardown=lambda: finalised.append(threading.get_ident()))
        assert finalised == [worker_thread]

    async def test_close_without_a_teardown_is_fine(self) -> None:
        worker = DedicatedThread(name="probe")
        await worker.close()
        assert not worker.is_open

    async def test_close_is_idempotent(self) -> None:
        """A second close must not run teardown again — detaching twice from a
        JVM is not harmless."""
        worker = DedicatedThread(name="probe")
        calls: list[int] = []
        await worker.close(teardown=lambda: calls.append(1))
        await worker.close(teardown=lambda: calls.append(1))
        assert calls == [1]


class TestAfterClose:
    async def test_calling_a_closed_worker_is_refused_clearly(self) -> None:
        """Its thread is gone and so is whatever it had initialised, so a
        silent restart would hand back a connection to nothing."""
        worker = DedicatedThread(name="probe")
        await worker.close()
        with pytest.raises(PramaError, match="has been closed"):
            await worker.call(threading.get_ident)

    async def test_the_refusal_says_it_cannot_be_reopened(self) -> None:
        worker = DedicatedThread(name="probe")
        await worker.close()
        with pytest.raises(PramaError) as caught:
            await worker.call(threading.get_ident)
        assert "cannot be reopened" in caught.value.remedy


class TestOrdinaryUse:
    async def test_it_returns_what_the_function_returns(self) -> None:
        async with DedicatedThread(name="probe") as worker:
            assert await worker.call(sum, [1, 2, 3]) == 6

    async def test_an_exception_propagates_rather_than_being_swallowed(self) -> None:
        """A worker that ate exceptions would turn a driver error into a hang."""

        def boom() -> None:
            raise ValueError("from the worker")

        async with DedicatedThread(name="probe") as worker:
            with pytest.raises(ValueError, match="from the worker"):
                await worker.call(boom)

    async def test_it_still_works_after_a_failed_call(self) -> None:
        def boom() -> None:
            raise ValueError("x")

        async with DedicatedThread(name="probe") as worker:
            with pytest.raises(ValueError):
                await worker.call(boom)
            assert await worker.call(sum, [1, 1]) == 2

    async def test_the_context_manager_closes_it(self) -> None:
        async with DedicatedThread(name="probe") as worker:
            assert worker.is_open
        assert not worker.is_open
