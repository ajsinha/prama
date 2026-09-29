"""The always-on scheduler: due controls run without anybody calling them.

Controls and evidence were stored, and nothing ran them on its own (docs/19,
Wave 9's "honest limit"); `prama control run` had to be invoked by cron or CI.
This runs inside `prama serve`, under the task supervisor, and every tick
executes what each control's schedule says is due — the same `ControlRun` the
CLI uses, so there is one definition of "run a control".

Three properties, each for a reason:

* **One server per tick.** A tick takes a lease in the database first and
  skips if another server holds it. Two servers running the same control
  would write two evidence records for one moment.
* **Off unless configured.** A scheduler that ran against a default source
  would produce evidence nobody asked for, about data nobody named.
* **A bounded history.** The last ticks are kept for the Schedule page in a
  fixed-size deque; an unbounded one is a leak with a timetable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import collections
import dataclasses
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from prama.core.log import get_logger
from prama.execute.run import ControlRun

_log = get_logger(__name__)

#: The lease every server competes for, once per tick.
LEASE = "scheduler:tick"

#: Ticks kept for the Schedule page.
HISTORY = 20


@dataclasses.dataclass(frozen=True, slots=True)
class Tick:
    """What one tick did."""

    started_at: str
    outcome: str  # ran | skipped | failed
    detail: str = ""
    executed: int = 0
    verdicts: dict[str, int] = dataclasses.field(default_factory=dict)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Scheduler:
    """Runs due controls for each tenant, one server at a time."""

    def __init__(
        self,
        database: Any,
        tenants: Sequence[str],
        *,
        against: str,
        dialect: str,
        interval: float = 60.0,
        holder: str = "prama",
        executor_for: Callable[[str, str], tuple[Any, Callable[[], None]]] | None = None,
        delegates: Any = None,
        config: Any = None,
    ) -> None:
        self._delegates = delegates
        #: For the evidence anchor, which runs after each tenant's run commits.
        self._config = config
        self._database = database
        self.tenants = tuple(tenants)
        self.against = against
        self.dialect = dialect
        self.interval = interval
        self._holder = holder
        if executor_for is None:
            from prama.connect.sources.query import executor_for as default

            executor_for = default
        self._executor_for = executor_for
        self.history: collections.deque[Tick] = collections.deque(maxlen=HISTORY)

    async def tick(self) -> Tick:
        """Run everything due, if this server wins the lease."""
        started = _now()
        leases = self._database.lease_provider()
        lease = await leases.acquire(LEASE, self._holder, max(self.interval * 2, 30.0))
        if lease is None:
            tick = Tick(started, "skipped", "another server holds the scheduler lease")
            from prama.telemetry import metrics

            metrics.SCHEDULER.inc(outcome="skipped")
            self.history.appendleft(tick)
            return tick
        try:
            execute, close = self._executor_for(self.against, self.dialect)
            executed, verdicts = 0, collections.Counter[str]()
            try:
                for tenant in self.tenants:
                    async with self._database.unit_of_work() as uow:
                        report = await ControlRun(
                            uow,
                            tenant,
                            execute=execute,
                            engine=self.dialect,
                            triggered_by="schedule",
                            respect_schedule=True,
                            delegates=self._delegates,
                        ).execute_all()
                    if self._config is not None:
                        from prama.evidence.anchor import anchor_after_run

                        await anchor_after_run(self._database, tenant, self._config)
                    executed += report.executed
                    verdicts.update(report.verdicts)
            finally:
                close()
            tick = Tick(started, "ran", "", executed, dict(verdicts))
        except Exception as exc:
            # A tick that fails is shown on the Schedule page and logged; the
            # next tick tries again. The supervisor restarts the loop itself
            # only if the loop dies, which this prevents for one bad tick.
            _log.warning("scheduler tick failed: %s", exc)
            tick = Tick(started, "failed", f"{type(exc).__name__}: {exc}"[:500])
        finally:
            await leases.release(lease)
        from prama.telemetry import metrics

        metrics.SCHEDULER.inc(outcome=tick.outcome)
        self.history.appendleft(tick)
        return tick

    async def loop(self) -> None:
        """Tick, then wait the interval, until cancelled by the supervisor."""
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)


def from_config(config: Any, database: Any) -> Scheduler | None:
    """The scheduler this configuration asks for, or ``None`` when it is off."""
    if not config.get_bool("scheduler.enabled", False):
        return None
    against = config.get_str("scheduler.against", "")
    tenants = [t for t in (config.get_str("tenancy.default_tenant", ""),) if t]
    if not against or not tenants:
        _log.warning(
            "scheduler.enabled is set but scheduler.against or tenancy.default_tenant is "
            "empty; the scheduler is not started"
        )
        return None
    return Scheduler(
        database,
        tenants,
        against=against,
        dialect=config.get_str("scheduler.dialect", "duckdb"),
        interval=float(config.get_duration("scheduler.interval", 60.0)),
        holder=config.get_str("app.instance_id", "prama"),
        delegates=_delegates(config),
        config=config,
    )


def _delegates(config: Any) -> Any:
    from prama.delegates.host import host_from_config

    return host_from_config(config)
