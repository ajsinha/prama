"""In-flight enforcement: acting on a message before it reaches a consumer.

Batch validation tells you a bad record is in the warehouse. In-flight
enforcement stops it arriving — and that is a different kind of promise, because
the moment a control can *drop* something, the control's own correctness becomes
a data-loss risk rather than an alerting one.

Four rules follow, and each of them is the difference between enforcement and
destruction:

* **Nothing is dropped without being kept.** A rejected message goes to the dead
  letter first and is only then removed from the stream. A pipeline that drops
  and *then* fails to record has destroyed data to enforce a rule about data
  quality, which is the worst trade in the product.
* **Back-pressure beats a silent discard.** If the dead letter will not accept a
  message, the pipeline stops. A full dead letter that silently falls back to
  dropping converts a storage problem into permanent loss, and the storage
  problem is the one somebody can fix.
* **A message that cannot be read is dead-lettered, not dropped.** An
  unparseable message is a finding about the sender. Discarding it removes the
  only evidence of what they sent.
* **The cost of enforcing is measured, not assumed.** docs/15 §7 sets a budget of
  five milliseconds added at p99, and a pipeline that cannot say what it costs
  is one nobody will put in front of a payment system. Every batch reports its
  own added latency.

**Actions come from ``prama.execute.actions``.** ALERT, TAG, QUARANTINE and
BLOCK already exist with an override path; this applies them per message rather
than per run, and does not invent a second vocabulary for the same four things.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from prama.core.errors import PramaError
from prama.execute.actions import Action

#: What a dead letter is handed. Returning False means it would not accept the
#: message, which stops the pipeline rather than dropping it.
DeadLetter = Callable[[dict[str, Any], str], bool]


class DeadLetterFull(PramaError):
    """The dead letter refused a message, so the pipeline must stop.

    Deliberately an exception rather than a return value. A caller that could
    ignore this would ignore it under load, which is exactly when the dead
    letter fills up.
    """


@dataclasses.dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one message."""

    #: ``passed`` · ``tagged`` · ``quarantined`` · ``blocked`` · ``unreadable``
    disposition: str
    message: dict[str, Any]
    #: Controls this message violated, by plan id. Named rather than counted:
    #: a message quarantined by one control out of forty needs to say which.
    violated: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    reason: str = ""

    @property
    def reaches_the_consumer(self) -> bool:
        """Whether a downstream reader sees this message.

        Tagged messages do. That is the point of tagging: the consumer decides,
        and a control that silently removed them would be making a business
        decision on a data quality signal.
        """
        return self.disposition in ("passed", "tagged")

    @property
    def was_kept(self) -> bool:
        """Whether the message survives somewhere a person can reach it."""
        return self.reaches_the_consumer or self.disposition in (
            "quarantined",
            "blocked",
            "unreadable",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Throughput:
    """What a pass cost, so the budget can be argued with."""

    messages: int = 0
    elapsed_seconds: float = 0.0
    #: Per-message latencies in milliseconds, sorted. Kept so percentiles are
    #: computed rather than estimated from a mean, which hides exactly the tail
    #: the budget is about.
    latencies_ms: tuple[float, ...] = ()

    @property
    def per_second(self) -> float | None:
        """Messages per second, or ``None`` when nothing was measured.

        Guarded on the message count as well as the clock. An empty pass still
        takes a few `perf_counter` ticks, so the elapsed-time guard never fired
        and the answer came out as `0.0` — a *measured* throughput of zero,
        which is a claim about performance rather than the absence of one
        (QA finding EXE-081). Its sibling `percentile` returns None for exactly
        this case, with a docstring saying why; this one did not.
        """
        if self.messages <= 0 or self.elapsed_seconds <= 0:
            return None
        return self.messages / self.elapsed_seconds

    def percentile(self, share: float) -> float | None:
        """A latency percentile, or ``None`` when nothing was measured.

        ``None`` rather than zero: a pass over no messages has not demonstrated
        a fast pipeline, and reporting 0 ms would say it had.
        """
        if not self.latencies_ms:
            return None
        index = min(len(self.latencies_ms) - 1, int(share * len(self.latencies_ms)))
        return self.latencies_ms[index]

    @property
    def p99_ms(self) -> float | None:
        return self.percentile(0.99)

    def within(self, budget_ms: float) -> bool | None:
        """Whether p99 fits the budget. ``None`` when nothing was measured."""
        p99 = self.p99_ms
        return None if p99 is None else p99 <= budget_ms

    def describe(self) -> str:
        if not self.messages:
            return "no messages passed through, so nothing was measured"
        rate = self.per_second
        p99 = self.p99_ms
        parts = [f"{self.messages:,} message(s)"]
        if rate is not None:
            parts.append(f"{rate:,.0f}/s")
        if p99 is not None:
            parts.append(f"p99 {p99:.3f} ms added")
        return ", ".join(parts)


@dataclasses.dataclass(frozen=True, slots=True)
class Report:
    """A pass over a stream."""

    outcomes: tuple[Outcome, ...] = ()
    throughput: Throughput = dataclasses.field(default_factory=Throughput)
    #: Set when the pass stopped early. A partial pass reported as a whole one
    #: is the failure this field exists to prevent.
    halted_because: str = ""

    @property
    def delivered(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.reaches_the_consumer)

    @property
    def withheld(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if not o.reaches_the_consumer)

    @property
    def completed(self) -> bool:
        return not self.halted_because

    def count(self, disposition: str) -> int:
        return sum(1 for o in self.outcomes if o.disposition == disposition)

    def describe(self) -> str:
        if self.halted_because:
            # First, and unambiguous. A pass that stopped and one that finished
            # look identical in their counts.
            return (
                f"HALTED after {len(self.outcomes)} message(s): {self.halted_because}. "
                "The rest of the stream was not examined."
            )
        parts = [f"{len(self.delivered)} delivered"]
        for disposition in ("tagged", "quarantined", "blocked", "unreadable"):
            found = self.count(disposition)
            if found:
                parts.append(f"{found} {disposition}")
        return ", ".join(parts) + f"; {self.throughput.describe()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": len(self.outcomes),
            "delivered": len(self.delivered),
            "withheld": len(self.withheld),
            "tagged": self.count("tagged"),
            "quarantined": self.count("quarantined"),
            "blocked": self.count("blocked"),
            "unreadable": self.count("unreadable"),
            "completed": self.completed,
            "halted_because": self.halted_because,
            "throughput": {
                "messages": self.throughput.messages,
                "per_second": self.throughput.per_second,
                "p99_ms": self.throughput.p99_ms,
            },
            "message": self.describe(),
        }


class Pipeline:
    """Applies stream assertions to messages and enforces the outcome.

    Holds the assertions and the dead letter and nothing else: a pipeline that
    also owned the transport would be untestable without one, and the transport
    is the part that differs between every deployment.
    """

    def __init__(
        self,
        assertions: Sequence[Any],
        *,
        action: Action = Action.TAG,
        dead_letter: DeadLetter | None = None,
        tag_field: str = "_prama",
    ) -> None:
        if action.touches_the_data and action is not Action.TAG and dead_letter is None:
            # Refused at construction rather than at the first bad message.
            # A quarantining pipeline with nowhere to put anything is a
            # deleting pipeline, and discovering that at runtime means it has
            # already deleted something.
            raise PramaError(
                f"a pipeline that {action.value}s needs a dead letter",
                code="STREAM.NO_DEAD_LETTER",
                remedy=(
                    "Give one. Without somewhere to put a rejected message, "
                    f"{action.value} means delete — and a control that destroys "
                    "data to enforce a rule about data quality is the worst "
                    "trade in the product."
                ),
                context={"action": action.value},
            )
        self._assertions = list(assertions)
        self._action = action
        self._dead_letter = dead_letter
        self._tag_field = tag_field

    @property
    def action(self) -> Action:
        return self._action

    def run(self, messages: Iterable[Any]) -> Report:
        """One pass. Stops on a full dead letter rather than discarding."""
        outcomes: list[Outcome] = []
        latencies: list[float] = []
        halted = ""
        started = time.perf_counter()

        for message in messages:
            began = time.perf_counter()
            try:
                outcome = self._judge(message)
            except DeadLetterFull as exc:
                halted = str(exc)
                break
            latencies.append((time.perf_counter() - began) * 1000.0)
            outcomes.append(outcome)

        elapsed = time.perf_counter() - started
        return Report(
            outcomes=tuple(outcomes),
            throughput=Throughput(
                messages=len(outcomes),
                elapsed_seconds=elapsed,
                latencies_ms=tuple(sorted(latencies)),
            ),
            halted_because=halted,
        )

    def _judge(self, message: Any) -> Outcome:
        payload = getattr(message, "payload", None)
        if payload is None and isinstance(message, dict):
            payload = message
        if not isinstance(payload, dict):
            # Unreadable. Dead-lettered rather than dropped: an unparseable
            # message is a finding about the sender, and discarding it removes
            # the only evidence of what they sent.
            self._to_dead_letter({"raw": repr(message)[:2000]}, "unreadable")
            return Outcome(
                disposition="unreadable",
                message={},
                reason="the message carries no readable payload",
            )

        violated: list[str] = []
        unknown: list[str] = []
        for assertion in self._assertions:
            verdict = assertion.judge(message)
            identity = getattr(getattr(assertion, "plan", None), "plan_id", "") or ""
            if getattr(verdict, "unknown", False):
                unknown.append(identity)
            if verdict.is_violation:
                violated.append(identity)

        if not violated:
            return Outcome(disposition="passed", message=payload, unknown=tuple(unknown))

        reason = f"violated {len(violated)} control(s)"
        if self._action is Action.ALERT:
            # Alerting does not touch the data. The message goes through and
            # the violation is reported; anything else would make ALERT a
            # different action from the one the estate approved.
            return Outcome(
                disposition="passed",
                message=payload,
                violated=tuple(violated),
                unknown=tuple(unknown),
                reason=reason,
            )
        if self._action is Action.TAG:
            tagged = {
                **payload,
                self._tag_field: {"violated": list(violated), "unknown": list(unknown)},
            }
            return Outcome(
                disposition="tagged",
                message=tagged,
                violated=tuple(violated),
                unknown=tuple(unknown),
                reason=reason,
            )

        # QUARANTINE and BLOCK both remove the message from the stream, and
        # both write it away *first*. The order is the whole safety property.
        self._to_dead_letter(payload, reason)
        return Outcome(
            disposition="quarantined" if self._action is Action.QUARANTINE else "blocked",
            message=payload,
            violated=tuple(violated),
            unknown=tuple(unknown),
            reason=reason,
        )

    def _to_dead_letter(self, payload: dict[str, Any], reason: str) -> None:
        if self._dead_letter is None:
            return
        if not self._dead_letter(payload, reason):
            raise DeadLetterFull(
                "the dead letter would not accept a message, so the pipeline stopped",
                code="STREAM.DEAD_LETTER_FULL",
                remedy=(
                    "Drain or resize it. Continuing would mean discarding the "
                    "message, which converts a storage problem into permanent "
                    "loss — and the storage problem is the one somebody can fix."
                ),
            )


__all__ = [
    "DeadLetter",
    "DeadLetterFull",
    "Outcome",
    "Pipeline",
    "Report",
    "Throughput",
]
