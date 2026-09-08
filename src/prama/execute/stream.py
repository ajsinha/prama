"""Evaluating a control against a stream, one message at a time.

Batch and stream are usually two implementations of the same rules, and the two
drift. Prama avoids that by evaluating the *same IR* against a message that it
would evaluate against a row — the expression semantics are the reference
interpreter's, imported rather than reimplemented, so a control that means one
thing in a nightly batch cannot mean something else in flight.

What genuinely differs is not the predicate but the *scope*.

**A row predicate is answerable per message.** ``notional IS NOT NULL`` needs
nothing but the message, and its verdict is immediate. This is the case
in-flight enforcement actually wants, because a message can be rejected before
it is committed.

**An aggregate needs a window.** ``HAS ROW COUNT BETWEEN …`` or a rate threshold
is a claim about a set, and a stream has no sets until somebody draws a boundary.
So a windowed assertion accumulates and produces a verdict per window, and the
window is declared — a control that silently chose its own would report a
different thing at a different message rate.

**Backpressure is reported, never absorbed.** A streaming quality check that
drops messages under load is worse than none: it reports green because it
stopped looking, exactly when the volume that broke it is the thing worth
looking at. The seam says how far behind it is and lets the caller decide.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from prama.backend.reference import UNKNOWN, Bindings, ReferenceEvaluator
from prama.core.errors import ValidationError
from prama.ir.model import ControlPlan, Verdict

#: A message, as the stream hands it over.
Message = Mapping[str, Any]


class WindowKind(enum.Enum):
    """How a stream is cut into sets a claim can be made about."""

    #: Fixed, non-overlapping. Each message belongs to exactly one, which is
    #: what makes a count reconcilable with a batch run over the same period.
    TUMBLING = "tumbling"
    #: Fixed count rather than fixed time. For a source whose rate varies so
    #: much that a time window is empty half the day and unmanageable the rest.
    COUNT = "count"

    @property
    def is_temporal(self) -> bool:
        return self is WindowKind.TUMBLING


@dataclasses.dataclass(frozen=True, slots=True)
class Window:
    """The boundary a windowed assertion is judged over."""

    kind: WindowKind = WindowKind.TUMBLING
    duration: timedelta = timedelta(minutes=1)
    size: int = 1000

    def __post_init__(self) -> None:
        if self.kind.is_temporal and self.duration <= timedelta(0):
            raise ValidationError(
                "a tumbling window needs a positive duration",
                remedy="Give the period each verdict covers, for example one minute.",
            )
        if not self.kind.is_temporal and self.size <= 0:
            raise ValidationError(
                "a count window needs a positive size",
                remedy="Give how many messages each verdict covers.",
            )

    def describe(self) -> str:
        if self.kind.is_temporal:
            return f"every {int(self.duration.total_seconds())} seconds"
        return f"every {self.size:,} messages"


@dataclasses.dataclass(frozen=True, slots=True)
class MessageVerdict:
    """One message, judged on its own."""

    passed: bool
    #: True when the predicate could not be evaluated. Kept distinct from a
    #: failure so the stream's unknown rate is visible: a source that starts
    #: sending a field as null shows up here before it shows up anywhere else.
    unknown: bool = False

    @property
    def is_violation(self) -> bool:
        return not self.passed


@dataclasses.dataclass(frozen=True, slots=True)
class WindowVerdict:
    """One window's outcome."""

    verdict: Verdict
    messages: int
    violations: int
    unknowns: int
    opened_at: datetime | None = None
    closed_at: datetime | None = None

    @property
    def violation_rate(self) -> float:
        return self.violations / self.messages if self.messages else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "messages": self.messages,
            "violations": self.violations,
            "unknowns": self.unknowns,
            "violation_rate": round(self.violation_rate, 6),
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Lag:
    """How far behind the assertion is, and whether that is a problem.

    Reported rather than absorbed. A streaming check that quietly dropped
    messages would report green because it stopped looking, exactly when the
    volume that broke it is the thing worth looking at.
    """

    messages_behind: int
    seconds_behind: float = 0.0
    #: The point at which the caller should shed load or scale out, declared by
    #: whoever deployed it rather than guessed here.
    threshold: int = 10_000

    @property
    def is_falling_behind(self) -> bool:
        return self.messages_behind > self.threshold

    def render(self) -> str:
        if not self.is_falling_behind:
            return f"{self.messages_behind:,} message(s) behind, within tolerance."
        return (
            f"{self.messages_behind:,} message(s) behind, past the declared tolerance of "
            f"{self.threshold:,}. Messages are not being dropped; the assertion is "
            f"asking the caller to shed load or add capacity."
        )


class StreamAssertion:
    """One control, evaluated against a stream.

    Holds only what a window needs — three counters — so a fleet of these costs
    nothing per control beyond the predicate itself. That is what makes running
    a whole suite in flight plausible rather than a demonstration.
    """

    def __init__(
        self,
        plan: ControlPlan,
        *,
        window: Window | None = None,
        bindings: Bindings | None = None,
    ) -> None:
        self._plan = plan
        self._window = window or Window()
        self._evaluator = ReferenceEvaluator(bindings)
        # Read once. An attribute lookup through two objects, per message, per
        # assertion, is not free at this rate.
        self._unknown_is_violation = plan.unknown_is_violation
        self._messages = 0
        self._violations = 0
        self._unknowns = 0
        self._opened_at: datetime | None = None

    @property
    def plan(self) -> ControlPlan:
        return self._plan

    @property
    def window(self) -> Window:
        return self._window

    @property
    def open_messages(self) -> int:
        return self._messages

    # -- per message -------------------------------------------------------

    def judge(self, message: Message) -> MessageVerdict:
        """Judge one message. No allocation beyond the evaluation itself.

        The same semantics the reference interpreter uses, imported rather than
        reimplemented — so an unknown counts as a violation here for the same
        reason and by the same code as in a nightly batch.
        """
        predicate = self._plan.predicate
        if predicate is None:
            return MessageVerdict(passed=True)
        outcome = self._evaluator.evaluate(predicate, message)
        if outcome is UNKNOWN:
            return MessageVerdict(passed=not self._plan.unknown_is_violation, unknown=True)
        return MessageVerdict(passed=bool(outcome))

    def offer(self, message: Message, *, at: datetime | None = None) -> WindowVerdict | None:
        """Accept one message; return a verdict when the window closes.

        Deliberately does not call :meth:`judge`. Allocating a MessageVerdict
        per message per assertion cost twice as much as the evaluation it
        described — measured at 7.07 µs for five controls, of which 4.7 µs was
        bookkeeping. On a hot path the object that reports the work is not
        allowed to outweigh the work.

        :meth:`judge` remains for per-message enforcement, where the caller
        needs the answer for that message and one allocation is the point.
        """
        if self._opened_at is None:
            self._opened_at = at
        self._messages += 1
        predicate = self._plan.predicate
        if predicate is not None:
            outcome = self._evaluator.evaluate(predicate, message)
            if outcome is UNKNOWN:
                self._unknowns += 1
                if self._unknown_is_violation:
                    self._violations += 1
            elif not outcome:
                self._violations += 1
        if self._should_close(at):
            return self.close(at=at)
        return None

    def _should_close(self, at: datetime | None) -> bool:
        if self._window.kind is WindowKind.COUNT:
            return self._messages >= self._window.size
        if at is None or self._opened_at is None:
            return False
        return at - self._opened_at >= self._window.duration

    def close(self, *, at: datetime | None = None) -> WindowVerdict:
        """Close the window and judge it, using the plan's own threshold.

        The same threshold the batch path applies, so a control that fails at
        0.1% in a nightly run fails at 0.1% in flight — which is the whole
        reason both go through the IR.
        """
        metrics = {
            "scanned_rows": float(self._messages),
            "violating_rows": float(self._violations),
        }
        verdict = (
            Verdict.INDETERMINATE if self._messages == 0 else self._plan.threshold.evaluate(metrics)
        )
        closed = WindowVerdict(
            verdict=verdict,
            messages=self._messages,
            violations=self._violations,
            unknowns=self._unknowns,
            opened_at=self._opened_at,
            closed_at=at,
        )
        self._messages = self._violations = self._unknowns = 0
        self._opened_at = None
        return closed


class StreamSuite:
    """Several assertions over one stream, evaluated in a single pass.

    The streaming equivalent of fusion: a message is deserialised once and
    every predicate sees the same object. Evaluating each control against its
    own copy would multiply the only cost that matters here.
    """

    def __init__(self, assertions: list[StreamAssertion], *, lag_threshold: int = 10_000) -> None:
        self._assertions = assertions
        self._lag_threshold = lag_threshold
        self._seen = 0

    def __len__(self) -> int:
        return len(self._assertions)

    @property
    def seen(self) -> int:
        return self._seen

    def offer(
        self, message: Message, *, at: datetime | None = None
    ) -> list[tuple[ControlPlan, WindowVerdict]]:
        self._seen += 1
        closed: list[tuple[ControlPlan, WindowVerdict]] = []
        for assertion in self._assertions:
            verdict = assertion.offer(message, at=at)
            if verdict is not None:
                closed.append((assertion.plan, verdict))
        return closed

    def close_all(self, *, at: datetime | None = None) -> list[tuple[ControlPlan, WindowVerdict]]:
        return [(a.plan, a.close(at=at)) for a in self._assertions if a.open_messages]

    def lag(self, produced: int) -> Lag:
        return Lag(messages_behind=max(0, produced - self._seen), threshold=self._lag_threshold)
