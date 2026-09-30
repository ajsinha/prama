"""The daemon: hello, run what the zone was given, report, wait, and again.

One worker, one loop, no threads. An agent runs a handful of statements a
minute against sources that are usually the bottleneck themselves; parallelism
here would buy little and cost the one property that matters most in a daemon
nobody watches — that what it is doing at any moment is obvious.

Each cycle:

1. **hello** — announce, with the capabilities derived from ``agent.yaml``, and
   be handed the zone's work. The receipt also acknowledges whatever the server
   already holds, so a report whose answer was lost is not sent a third time.
2. **run** each assignment with the kernel-backed `Agent`, which judges with the
   plan's own threshold, redacts under the zone's residency policy, and spools
   the finding durably before anything is sent.
3. **report** — deliver the spool, in batches, until it is empty or the server
   stops accepting. Delivery is at-least-once; the server deduplicates by
   sequence.
4. **wait** ``poll_after_seconds`` (bounded by ``poll:``), or, if the server
   could not be reached, an exponentially growing, jittered delay. The findings
   stay in the spool and go with the next report that gets through.

It stops cleanly on SIGTERM or SIGINT after the assignment in hand, and delivers
what it can on the way out. It stops **for good** on a permanent refusal — a
revoked agent that kept calling would be a revoked agent generating load for as
long as somebody left it running — and remembers that, so a restart by the
service manager does not undo it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import random
import signal
import threading
from collections.abc import Callable, Iterator
from typing import Any

from prama_kernel.agent.capability import AgentCapabilities
from prama_kernel.agent.protocol import Receipt, Refusal, Response, response_from_dict
from prama_kernel.agent.spool import Spool
from prama_kernel.clock import Clock, SystemClock
from prama_kernel.errors import ConfigError
from prama_kernel.log import get_logger, log_fields

from prama_agent.config import AgentConfig
from prama_agent.executors import Executors
from prama_agent.link import FleetLink, LinkUnavailable
from prama_agent.runner import Agent
from prama_agent.state import SPOOL, Contact, Identity, load_contact, prepare, save_contact
from prama_agent.version import VERSION

_log = get_logger(__name__)

EXIT_OK = 0
#: The server refused this agent permanently. A service manager should not
#: restart it (``RestartPreventExitStatus=3`` in the unit file).
EXIT_REFUSED = 3


@dataclasses.dataclass(frozen=True, slots=True)
class CycleResult:
    """What one hello-run-report cycle did, and how long to wait before the next."""

    ran: int = 0
    delivered: int = 0
    contacted: bool = False
    refusal: Refusal | None = None
    wait_seconds: float = 0.0

    @property
    def refused_for_good(self) -> bool:
        return self.refusal is not None and self.refusal.permanent


def capabilities_for(config: AgentConfig, delegates: Any = None) -> AgentCapabilities:
    """What this agent can run, derived from what it was configured with.

    Never typed by hand: an agent advertising an engine it has no source for
    would be handed work it can only fail.
    """
    return AgentCapabilities(
        engines=config.engines,
        datasets=config.datasets,
        max_concurrency=1,  # one worker; see the module docstring
        delegates=delegates.registry.pinned() if delegates is not None else (),
    )


class Daemon:
    """The long-running agent. Construct, then `run`."""

    def __init__(
        self,
        config: AgentConfig,
        identity: Identity,
        link: FleetLink,
        *,
        executors: Executors | None = None,
        clock: Clock | None = None,
        rng: random.Random | None = None,
        delegates: Any = None,
    ) -> None:
        self.config = config
        self.identity = identity
        self._link = link
        self._clock = clock or SystemClock()
        self._rng = rng or random.Random()
        self._stop = threading.Event()
        self._failures = 0
        prepare(config.state_dir)
        self._contact = load_contact(config.state_dir)
        residency = config.residency
        if config.zone_declared and residency.zone != identity.zone:
            raise ConfigError(
                f"agent.yaml's residency policy is for zone {residency.zone}, and this agent "
                f"is enrolled in {identity.zone}",
                remedy=(
                    "The zone is fixed at enrolment. Correct residency.zone, or remove it so "
                    "the enrolled zone is used."
                ),
                context={"declared": residency.zone, "enrolled": identity.zone},
            )
        residency = dataclasses.replace(residency, zone=identity.zone)
        if delegates is None and config.delegates:
            from prama_kernel.delegates.host import host_from_config

            delegates = host_from_config({"delegates": config.delegates})
        self.spool = Spool(
            capacity=config.spool_capacity,
            path=config.state_dir / SPOOL,
            clock=self._clock,
        )
        self.agent = Agent(
            identity.agent_id,
            identity.key,
            executor_for=executors if executors is not None else Executors(config.sources),
            residency=residency,
            capabilities=capabilities_for(config, delegates),
            spool=self.spool,
            clock=self._clock,
            version=VERSION,
            delegates=delegates,
        )

    # -- lifecycle ------------------------------------------------------------

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def request_stop(self) -> None:
        """Finish the assignment in hand, deliver what can be delivered, then stop."""
        self._stop.set()

    def run(self, *, once: bool = False, handle_signals: bool = True) -> int:
        """Loop until stopped. Returns the process exit status."""
        if self._contact.refused:
            _log.error(
                "this agent was refused permanently and will not start: %s",
                self._contact.refused.get("reason", ""),
            )
            return EXIT_REFUSED
        log_fields(
            _log,
            logging.INFO,
            "agent starting",
            agent_id=self.identity.agent_id,
            zone=self.identity.zone,
            server=self.config.server.url,
            sources=[s.describe() for s in self.config.sources],
            pending=len(self.spool),
        )
        with self._signals(handle_signals):
            while not self.stopping:
                try:
                    result = self.cycle()
                except Exception as exc:  # the daemon outlives its own bugs, and says so
                    _log.exception("the cycle failed unexpectedly; backing off")
                    result = self._unreachable(exc)
                if result.refused_for_good:
                    return EXIT_REFUSED
                if once:
                    break
                self._stop.wait(result.wait_seconds)
        log_fields(_log, logging.INFO, "agent stopped", pending=len(self.spool))
        return EXIT_OK

    @contextlib.contextmanager
    def _signals(self, enabled: bool) -> Iterator[None]:
        if not enabled or threading.current_thread() is not threading.main_thread():
            yield
            return

        def stop(signum: int, _frame: Any) -> None:
            _log.info(
                "%s received: stopping after the assignment in hand", signal.Signals(signum).name
            )
            self.request_stop()

        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    # -- one cycle --------------------------------------------------------------

    def cycle(self) -> CycleResult:
        """hello, run, report. Never raises for an unreachable server."""
        try:
            response = self._exchange(self._link.hello, self.agent.hello()[0].to_dict())
        except LinkUnavailable as exc:
            return self._unreachable(exc)
        if isinstance(response, Refusal):
            return self._refused(response)
        self.agent.apply(response)
        ran = self._run(response)
        try:
            delivered, refusal = self._deliver()
        except LinkUnavailable as exc:
            return self._unreachable(exc, ran=ran)
        if refusal is not None:
            return self._refused(refusal, ran=ran, delivered=delivered)
        return self._succeeded(response, ran=ran, delivered=delivered)

    def _run(self, receipt: Receipt) -> int:
        ran = 0
        for index, assignment in enumerate(receipt.assignments):
            if self.stopping:
                # Not run and not reported: the server's claim on them lapses
                # and they return to the zone's queue for another agent.
                _log.info(
                    "stopping with %d assignment(s) not started; the server requeues them",
                    len(receipt.assignments) - index,
                )
                break
            outcome = self.agent.run(assignment)
            ran += 1
            record = outcome.record
            log_fields(
                _log,
                logging.WARNING if outcome.error else logging.INFO,
                "assignment ran",
                plan_id=assignment.plan_id,
                dataset=assignment.dataset,
                binding=assignment.binding,
                verdict=record.verdict if record else "",
                sequence=record.sequence if record else -1,
                error=outcome.error,
            )
        return ran

    def _deliver(self) -> tuple[int, Refusal | None]:
        """Report until the spool is empty or the server stops taking anything."""
        delivered = 0
        while len(self.spool) or self.spool.gaps:
            before = (len(self.spool), len(self.spool.gaps))
            message, _ = self.agent.report(self.config.report_batch)
            response = self._exchange(self._link.report, message.to_dict())
            if isinstance(response, Refusal):
                self.agent.apply(response)
                return delivered, response
            for sequence, reason in response.rejected:
                _log.warning("the server rejected finding %d: %s", sequence, reason)
            self.agent.apply(response)
            after = (len(self.spool), len(self.spool.gaps))
            delivered += before[0] - after[0]
            if after == before:
                # Nothing was taken. Sending the same batch again now would be
                # answered the same way; the next cycle tries again.
                _log.warning("the server accepted none of %d finding(s)", before[0])
                break
        return delivered, None

    def _exchange(self, call: Callable[..., dict[str, Any]], payload: dict[str, Any]) -> Response:
        answer = call(payload, key=self.identity.key)
        try:
            return response_from_dict(answer)
        except (KeyError, TypeError, ValueError) as exc:
            raise LinkUnavailable(
                "the server answered with something that is not a Receipt or a Refusal",
                remedy="Check that server.url names a Prama server with the fleet API.",
                context={"error": f"{type(exc).__name__}: {exc}"},
            ) from exc

    # -- outcomes -------------------------------------------------------------

    def _succeeded(self, receipt: Receipt, *, ran: int, delivered: int) -> CycleResult:
        self._failures = 0
        now = self._clock.now().isoformat()
        self._record(
            dataclasses.replace(
                self._contact,
                last_attempt_at=now,
                last_contact_at=now,
                consecutive_failures=0,
                last_error="",
            )
        )
        poll = self.config.poll
        wait = min(poll.max_seconds, max(poll.min_seconds, float(receipt.poll_after_seconds)))
        return CycleResult(ran=ran, delivered=delivered, contacted=True, wait_seconds=wait)

    def _unreachable(self, exc: Exception, *, ran: int = 0) -> CycleResult:
        self._failures += 1
        wait = self.backoff(self._failures)
        log_fields(
            _log,
            logging.WARNING,
            "server unreachable; findings stay in the spool",
            error=str(getattr(exc, "message", exc)),
            failures=self._failures,
            retry_in_seconds=round(wait, 1),
            pending=len(self.spool),
        )
        self._record(
            dataclasses.replace(
                self._contact,
                last_attempt_at=self._clock.now().isoformat(),
                consecutive_failures=self._failures,
                last_error=str(getattr(exc, "message", exc)),
            )
        )
        return CycleResult(ran=ran, wait_seconds=wait)

    def _refused(self, refusal: Refusal, *, ran: int = 0, delivered: int = 0) -> CycleResult:
        now = self._clock.now().isoformat()
        contact = dataclasses.replace(
            self._contact, last_attempt_at=now, last_contact_at=now, last_error=refusal.reason
        )
        if refusal.permanent:
            _log.error("refused permanently: %s. %s", refusal.reason, refusal.remedy)
            contact = dataclasses.replace(contact, refused=refusal.to_dict())
            self._record(contact)
            self._stop.set()
            return CycleResult(ran=ran, delivered=delivered, contacted=True, refusal=refusal)
        self._failures += 1
        wait = self.backoff(self._failures)
        _log.warning("refused for now: %s; trying again in %.0fs", refusal.reason, wait)
        self._record(dataclasses.replace(contact, consecutive_failures=self._failures))
        return CycleResult(
            ran=ran, delivered=delivered, contacted=True, refusal=refusal, wait_seconds=wait
        )

    def backoff(self, failures: int) -> float:
        """Exponential in the failures, capped, with jitter in its upper half.

        Jitter, because a fleet that lost its server together would otherwise
        return together, on the same second, every time.
        """
        poll = self.config.poll
        ceiling = min(
            poll.backoff_max_seconds,
            poll.backoff_initial_seconds * (2 ** min(max(failures - 1, 0), 30)),
        )
        return self._rng.uniform(ceiling / 2, ceiling)

    def _record(self, contact: Contact) -> None:
        self._contact = contact
        try:
            save_contact(self.config.state_dir, contact)
        except OSError as exc:  # a diary that cannot be written does not stop the work
            _log.error("could not record contact state: %s", exc)
