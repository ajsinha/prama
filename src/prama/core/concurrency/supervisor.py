"""Structured task supervision.

``asyncio.create_task`` without keeping the handle is the most common source of
silent failure in async services: the task raises, the exception is attached to
a garbage-collected object, and the only symptom is that something stopped
happening. A supervisor owns its children, so a failure is either propagated or
deliberately absorbed by a named policy — never lost.

Three restart policies, chosen to match real workloads:

* ``NEVER`` — a one-shot job. Failure surfaces to the caller.
* ``ON_FAILURE`` — a worker loop. Restarted with exponential backoff and jitter,
  bounded by ``max_restarts`` within ``restart_window`` so a crash loop is
  eventually reported rather than hidden by infinite retrying.
* ``ALWAYS`` — a poller that is expected to return.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import random
from collections.abc import Awaitable, Callable
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.core.errors import ConcurrencyError
from prama.core.log import get_logger

_log = get_logger(__name__)


class RestartPolicy(enum.Enum):
    NEVER = "never"
    ON_FAILURE = "on_failure"
    ALWAYS = "always"


@dataclasses.dataclass(slots=True)
class TaskHandle:
    """A supervised task and its history."""

    name: str
    policy: RestartPolicy
    task: asyncio.Task[Any] | None = None
    restarts: int = 0
    last_error: BaseException | None = None
    started_at: float = 0.0
    stopped: bool = False

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()


class TaskSupervisor:
    """Owns a set of long-lived asyncio tasks.

    Use as an async context manager; leaving the block cancels and awaits every
    child, so a task cannot outlive the scope that created it.

        async with TaskSupervisor("scheduler") as sup:
            sup.spawn("dispatch", dispatch_loop, policy=RestartPolicy.ON_FAILURE)
            await sup.wait()
    """

    def __init__(
        self,
        name: str = "supervisor",
        *,
        clock: Clock | None = None,
        shutdown_grace: float = 30.0,
        max_restarts: int = 10,
        restart_window: float = 60.0,
        base_backoff: float = 0.2,
        max_backoff: float = 30.0,
    ) -> None:
        self.name = name
        self._clock = clock or SystemClock()
        self._shutdown_grace = shutdown_grace
        self._max_restarts = max_restarts
        self._restart_window = restart_window
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._handles: dict[str, TaskHandle] = {}
        self._stopping = asyncio.Event()
        self._failures: list[BaseException] = []

    # -- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> TaskSupervisor:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.shutdown()

    def spawn(
        self,
        name: str,
        factory: Callable[[], Awaitable[Any]],
        *,
        policy: RestartPolicy = RestartPolicy.NEVER,
    ) -> TaskHandle:
        """Start a supervised task.

        *factory* is a zero-argument callable returning a coroutine, not a
        coroutine object, because a restart needs to build a fresh one.
        """
        if name in self._handles and self._handles[name].running:
            raise ConcurrencyError(
                f"task {name!r} is already running under supervisor {self.name!r}",
                remedy="Use a distinct task name, or stop the existing task first.",
                context={"supervisor": self.name, "task": name},
            )
        handle = TaskHandle(name=name, policy=policy, started_at=self._clock.monotonic())
        self._handles[name] = handle
        handle.task = asyncio.create_task(self._run(handle, factory), name=f"{self.name}:{name}")
        return handle

    async def _run(self, handle: TaskHandle, factory: Callable[[], Awaitable[Any]]) -> None:
        window_start = self._clock.monotonic()
        restarts_in_window = 0
        while not self._stopping.is_set():
            try:
                await factory()
                if handle.policy is not RestartPolicy.ALWAYS:
                    return
                # A completed run is not a restart. This used to fall straight
                # into the accounting below, so an ALWAYS task that returned
                # normally — a poller finishing its pass, which is the whole
                # point of the policy — was counted as having crashed: its
                # restart total climbed, the backoff throttled it toward thirty
                # seconds between passes, and enough healthy passes inside the
                # window had it given up on as a crash loop (QA finding
                # CFG-205).
                #
                # The counters reset instead, so the give-up threshold means
                # what it says: this many *failures* in a row. Cadence belongs
                # to the task — a poller sleeps for its own interval — because
                # a supervisor that paces a healthy task is deciding something
                # it does not know.
                window_start, restarts_in_window = self._clock.monotonic(), 0
                await asyncio.sleep(0)
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                handle.last_error = exc
                if handle.policy is RestartPolicy.NEVER:
                    self._failures.append(exc)
                    _log.error("task %s:%s failed: %s", self.name, handle.name, exc, exc_info=exc)
                    return
                _log.warning("task %s:%s failed (%s); restarting", self.name, handle.name, exc)
            now = self._clock.monotonic()
            if now - window_start > self._restart_window:
                window_start, restarts_in_window = now, 0
            restarts_in_window += 1
            handle.restarts += 1
            if restarts_in_window > self._max_restarts:
                failure = ConcurrencyError(
                    f"task {handle.name!r} restarted {restarts_in_window} times in "
                    f"{self._restart_window:.0f}s and is being given up on",
                    remedy=(
                        "Read the last error above: a crash loop is a defect, not a "
                        "transient. The task is stopped, not silently retried forever."
                    ),
                    context={"supervisor": self.name, "task": handle.name},
                    cause=handle.last_error,
                )
                self._failures.append(failure)
                _log.error("%s", failure)
                return
            await asyncio.sleep(self._backoff(restarts_in_window))

    def _backoff(self, attempt: int) -> float:
        """Exponential with full jitter — avoids a synchronised retry storm."""
        ceiling = min(self._max_backoff, self._base_backoff * (2 ** min(attempt, 16)))
        return random.uniform(0, ceiling)

    # -- coordination ------------------------------------------------------

    async def wait(self) -> None:
        """Block until shutdown is requested."""
        await self._stopping.wait()

    def request_stop(self) -> None:
        self._stopping.set()

    async def shutdown(self) -> None:
        """Cancel every child, wait out the grace period, then report failures."""
        self._stopping.set()
        tasks = [h.task for h in self._handles.values() if h.task and not h.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=self._shutdown_grace)
            for task in pending:
                _log.error(
                    "task %s did not stop within %.0fs of cancellation",
                    task.get_name(),
                    self._shutdown_grace,
                )
            for task in done:
                exc = task.exception() if not task.cancelled() else None
                if exc is not None:
                    self._failures.append(exc)
        for handle in self._handles.values():
            handle.stopped = True

    # -- observation -------------------------------------------------------

    def handles(self) -> list[TaskHandle]:
        return list(self._handles.values())

    def failures(self) -> list[BaseException]:
        return list(self._failures)

    def healthy(self) -> bool:
        return not self._failures and all(
            h.running or h.stopped or h.policy is RestartPolicy.NEVER
            for h in self._handles.values()
        )

    def raise_for_failures(self) -> None:
        """Re-raise the first recorded failure, if any."""
        if self._failures:
            raise self._failures[0]


def run_sync(awaitable: Any) -> Any:
    """Run a coroutine from synchronous code, whatever loop state we are in.

    Lives here rather than beside its caller because it owns a thread, and a
    thread anywhere else is the beginning of a codebase with four different
    ways of doing this — which is what the architecture rule about bare threads
    exists to prevent.

    ``asyncio.run`` is correct when nothing is running and fatal when something
    is: a synchronous callback invoked from inside a request or a task raises
    "cannot be called from a running event loop" at the moment it is used,
    which is the worst place to find out. When a loop is already turning the
    coroutine goes to a thread of its own and the caller blocks — blocking is
    the point, because the caller's contract is synchronous and quietly making
    it otherwise would change that contract for everyone above it.
    """
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, awaitable).result()
