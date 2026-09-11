"""A worker pinned to one thread, for libraries that insist on it.

Most of this package is about not spawning threads. This is the exception, and
it exists so the exception lives in one reviewed place rather than being
open-coded wherever somebody meets a library with thread affinity.

Some native libraries are not merely thread-*unsafe* but thread-*bound*: they
must be used from the thread that initialised them, and using them from another
does not raise — it deadlocks. JPype is the case that forced this. A JVM thread
must be *attached* before it may touch Java, an unattached pool thread hangs
rather than failing, and a JDBC ``Connection`` is not thread-safe either, so a
pool would be wrong twice over.

Two properties make this safe to have in a codebase that otherwise forbids raw
threads:

**One thread, owned by one object, shut down explicitly.** There is no pool and
no sharing. The owner closes it, and closing waits — a worker that outlives its
owner is the leak this package exists to prevent.

**Teardown runs on the worker itself.** A library that must be finalised from
the thread that initialised it — detaching from a JVM, closing a driver handle —
gets a hook that runs there. Doing it from the caller's thread is the bug this
would otherwise cause, and it surfaces at interpreter exit rather than anywhere
a stack trace would help.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Callable
from typing import Any

from prama.core.errors import PramaError

__all__ = ["DedicatedThread"]


class DedicatedThread:
    """A single worker thread that every call for one resource runs on.

    Use it as an async context manager, or call :meth:`close` yourself::

        worker = DedicatedThread(name="jdbc")
        connection = await worker.call(connect, url)
        ...
        await worker.close(teardown=detach_from_jvm)
    """

    def __init__(self, *, name: str) -> None:
        self._name = name
        self._pool: concurrent.futures.ThreadPoolExecutor | None = (
            concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        )

    @property
    def is_open(self) -> bool:
        return self._pool is not None

    async def call(self, function: Callable[..., Any], *arguments: Any, **keywords: Any) -> Any:
        """Run one piece of work on this worker's thread.

        Keywords as well as positionals. Without them every caller with a
        keyword-taking function has to wrap it in a lambda, and the one that
        forgot — Snowflake's ``open()`` — raised ``DedicatedThread.call() got an
        unexpected keyword argument 'account'``, which blames the concurrency
        primitive for a connector bug and could never have worked.
        """
        if self._pool is None:
            raise PramaError(
                f"the {self._name} worker has been closed",
                code="CONCURRENCY.WORKER_CLOSED",
                remedy=(
                    "A closed worker cannot be reopened; its thread is gone and so "
                    "is whatever it had initialised. Open a new one."
                ),
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, lambda: function(*arguments, **keywords))

    async def close(self, *, teardown: Callable[[], Any] | None = None) -> None:
        """Stop the worker, running ``teardown`` on it first.

        Idempotent. ``teardown`` runs on the worker's own thread because that is
        the whole reason this class exists — a library finalised from the wrong
        thread fails at interpreter exit, a long way from anything explanatory.
        """
        pool = self._pool
        if pool is None:
            return
        if teardown is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(pool, teardown)
        self._pool = None
        pool.shutdown(wait=True)

    async def __aenter__(self) -> DedicatedThread:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()
