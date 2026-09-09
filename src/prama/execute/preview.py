"""Running a control before it exists, against real data.

The studio can already tell an author whether a control is *sound* — it parses,
it type-checks, it compiles to SQL you can read. It cannot tell them the thing
they actually want to know, which is **what this will do to us**: how many rows
it flags today, and how often it would have fired over the last month. Those
two questions decide whether a control gets approved and, more importantly,
whether it gets muted three weeks later.

Everything here is deliberately kept apart from ``run.py``, in one specific way:

    **A trial is not evidence and cannot become evidence.**

``ControlRun`` opens a run, appends to the hash-chained ledger and finishes the
run. This module writes nothing, holds no unit of work, and returns a ``Trial``
rather than an ``EvidenceRecord`` — a type that no ledger method will accept.
That is not squeamishness. A preview runs against a control that has not been
approved, often against a bounded sample, and frequently while the author is
still editing it; evidence that a regulator may later read must be the record
of a control the estate agreed to, run in full. Making the two convertible
would be one refactor away from a ledger nobody can vouch for.

Three things the obvious implementation gets wrong, each of which turns a
preview into a false reassurance:

* **A period with no rows in it is not a passing period.** A control over an
  empty slice violates nothing and would be judged a pass. Averaged into a
  backtest over thirty days, ten empty days quietly cut the expected alert rate
  by a third — and the ten empty days are usually a retention window, meaning
  the backtest is most wrong exactly where the author trusts it most. An empty
  slice is reported as ``no_data`` and is excluded from the rate, with the
  count of excluded periods stated.
* **An incomplete screen still cannot report a pass.** The same rule as the
  real runner, and it matters more here: this is the number somebody is about
  to approve a control on.
* **A bounded preview must say it was bounded.** A row cap that silently
  truncated the scan produces a violation count that is a floor, and a floor
  presented as a count is the single most dangerous number this system can
  emit.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
import time
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from typing import Any

from prama.backend import compile_for, judge
from prama.core.errors import ValidationError
from prama.ir.resolve import resolved
from prama.pql import parse_control
from prama.pql.ast import BinaryOp, ColumnRef, Control, Literal

#: Same shape as the runner's. One interface to a source, whatever it is.
Executor = Any

#: A column name a period filter may be built from.
#:
#: Not the barrier against injection — the dialect quotes every identifier, so
#: ``as_of_date; DROP TABLE positions --`` compiles to a column of that name
#: and finds nothing. This is the second line, and its job is the error
#: message: without it the author gets "no column named
#: as_of_date; DROP TABLE positions --" from the engine, which tells them
#: nothing about what to type instead.
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclasses.dataclass(frozen=True, slots=True)
class Trial:
    """What a control would have found, once.

    Deliberately not an ``EvidenceRecord``: it carries no plan lineage, no
    snapshot reference and no chain position, because it is not going into the
    ledger and a type that looked like it could would eventually be put there.
    """

    #: What was tried — ``"now"``, or the business date of a backtest period.
    label: str
    verdict: str = ""
    scanned_rows: float = 0.0
    violating_rows: float = 0.0
    #: Why the verdict reads as it does, when it needs saying.
    detail: str = ""
    #: Set when the trial could not be run at all. Never conflated with a
    #: verdict: "we could not look" and "we looked and found nothing" are
    #: different answers, and only one of them is reassuring.
    error: str = ""
    elapsed_ms: int = 0
    screen_is_complete: bool = True
    residual_validators: tuple[tuple[str, str], ...] = ()
    #: The SQL that ran, so the author can read what was actually asked.
    query: str = ""
    #: True when a row cap bound the scan, making the counts a floor.
    was_bounded: bool = False

    @property
    def ran(self) -> bool:
        return not self.error

    @property
    def has_data(self) -> bool:
        return self.ran and self.scanned_rows > 0

    @property
    def would_alert(self) -> bool:
        """Whether this period would have produced an alert.

        ``indeterminate`` counts. A control that could not establish a pass is
        one somebody has to look at, and a backtest that treated it as quiet
        would understate the workload the author is signing up for.
        """
        return self.verdict in {"fail", "indeterminate"}

    @property
    def rate(self) -> float | None:
        """Violating rows as a proportion, or ``None`` when nothing was scanned.

        ``None`` rather than zero, and the distinction is the whole point: zero
        means "we looked at rows and none were bad".
        """
        if self.scanned_rows <= 0:
            return None
        return self.violating_rows / self.scanned_rows

    def describe(self) -> str:
        if self.error:
            return f"{self.label}: could not be evaluated — {self.error}"
        if not self.has_data:
            return f"{self.label}: no rows in scope, so nothing was tested"
        rate = self.rate
        assert rate is not None
        floor = "at least " if self.was_bounded or not self.screen_is_complete else ""
        return (
            f"{self.label}: {self.verdict} — {floor}{self.violating_rows:,.0f} of "
            f"{self.scanned_rows:,.0f} rows ({rate:.2%})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "verdict": self.verdict,
            "scanned_rows": self.scanned_rows,
            "violating_rows": self.violating_rows,
            "rate": self.rate,
            "detail": self.detail,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "screen_is_complete": self.screen_is_complete,
            "residual_validators": [list(pair) for pair in self.residual_validators],
            "query": self.query,
            "was_bounded": self.was_bounded,
            "would_alert": self.would_alert,
            "has_data": self.has_data,
            "message": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Backtest:
    """What a control would have done over a stretch of history.

    The number the author is looking for is the last one — how many alerts a
    month — and every honest qualification of it lives on this object rather
    than in a comment beside it.
    """

    trials: tuple[Trial, ...] = ()

    @property
    def evaluated(self) -> tuple[Trial, ...]:
        """Periods that produced a verdict on actual rows.

        Both exclusions matter. A period that errored was not evidence of
        quiet, and a period with no rows was not evidence of anything.
        """
        return tuple(t for t in self.trials if t.has_data)

    @property
    def errored(self) -> tuple[Trial, ...]:
        return tuple(t for t in self.trials if t.error)

    @property
    def empty(self) -> tuple[Trial, ...]:
        return tuple(t for t in self.trials if t.ran and not t.has_data)

    @property
    def alerting(self) -> tuple[Trial, ...]:
        return tuple(t for t in self.evaluated if t.would_alert)

    @property
    def is_a_lower_bound(self) -> bool:
        """Whether the alert count could only be higher than reported.

        True as soon as any period was bounded or screened, because both make a
        violation count a floor — and a floor that fired is still a fire, while
        a floor that did not may yet.
        """
        return any(t.was_bounded or not t.screen_is_complete for t in self.evaluated)

    @property
    def alert_rate(self) -> float | None:
        """Alerting periods over evaluated periods, or ``None``.

        ``None`` when nothing could be evaluated. A backtest that could not
        read a single period must not report ``0.0``; that is the number that
        gets a control approved on the strength of an outage.
        """
        if not self.evaluated:
            return None
        return len(self.alerting) / len(self.evaluated)

    def per_period(self, periods: int) -> float | None:
        """Expected alerts over ``periods`` future periods, if the past holds."""
        rate = self.alert_rate
        return None if rate is None else rate * periods

    @property
    def is_trustworthy(self) -> bool:
        """Whether the rate rests on enough periods to be worth quoting.

        Five is not a statistical threshold and does not pretend to be; it is
        the point below which a single noisy day dominates the answer, and
        quoting "20% of days" from one alert in five is how a control gets
        approved on a coin flip.
        """
        return len(self.evaluated) >= 5

    def describe(self) -> str:
        """A sentence that names what was *not* evaluated before what was."""
        if not self.trials:
            return "no periods were requested, so nothing was backtested"
        parts: list[str] = []
        if not self.evaluated:
            parts.append(f"none of the {len(self.trials)} period(s) could be evaluated")
        else:
            bound = "at least " if self.is_a_lower_bound else ""
            parts.append(
                f"{bound}{len(self.alerting)} alert(s) over "
                f"{len(self.evaluated)} evaluated period(s)"
            )
        if self.empty:
            parts.append(
                f"{len(self.empty)} period(s) had no rows in scope and are excluded "
                "from the rate rather than counted as quiet"
            )
        if self.errored:
            parts.append(f"{len(self.errored)} period(s) could not be read at all")
        if self.evaluated and not self.is_trustworthy:
            parts.append(f"{len(self.evaluated)} period(s) is too few to quote a rate from")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trials": [t.to_dict() for t in self.trials],
            "requested": len(self.trials),
            "evaluated": len(self.evaluated),
            "empty": len(self.empty),
            "errored": len(self.errored),
            "alerting": len(self.alerting),
            "alert_rate": self.alert_rate,
            "per_30_periods": self.per_period(30),
            "is_a_lower_bound": self.is_a_lower_bound,
            "is_trustworthy": self.is_trustworthy,
            "message": self.describe(),
        }


class Preview:
    """Runs a control against real data without recording anything.

    Holds an executor and an engine name and nothing else — in particular, no
    unit of work, so there is no ledger within reach even by accident.
    """

    def __init__(
        self,
        *,
        execute: Executor,
        engine: str = "duckdb",
        max_rows: int = 0,
    ) -> None:
        self._execute = execute
        self._engine = engine
        #: A scan ceiling, when the caller wants one. Zero means unbounded,
        #: which is right for a preview an author explicitly asked for and
        #: wrong for one that fires on every keystroke. Applied by the compiler,
        #: which wraps the source: the metric query aggregates, so a LIMIT on
        #: the query would bound the one row of output and leave the scan
        #: exactly as expensive.
        self._max_rows = max_rows

    def once(self, source: str | Control, *, label: str = "now") -> Trial:
        """Run one control once, as written."""
        try:
            control = source if isinstance(source, Control) else parse_control(source)
        except Exception as exc:
            return Trial(label=label, error=f"{type(exc).__name__}: {exc}")
        return self._trial(control, label=label)

    def over(
        self,
        source: str | Control,
        *,
        period_column: str,
        periods: Sequence[date | str],
    ) -> Iterator[Trial]:
        """Run one control once per period, yielding each as it completes.

        A generator, not a list, because a thirty-day backtest is thirty round
        trips to a warehouse and a screen that shows nothing until the last one
        lands is a screen people stop using. The caller decides whether to
        collect them or stream them.
        """
        try:
            control = source if isinstance(source, Control) else parse_control(source)
        except Exception as exc:
            for period in periods:
                yield Trial(label=str(period), error=f"{type(exc).__name__}: {exc}")
            return

        column = plain_identifier(period_column)
        for period in periods:
            label = period.isoformat() if isinstance(period, date) else str(period)
            yield self._trial(_restricted(control, column, label), label=label)

    def backtest(
        self,
        source: str | Control,
        *,
        period_column: str,
        periods: Sequence[date | str],
    ) -> Backtest:
        """The whole backtest, collected. ``over`` is the streaming form."""
        return Backtest(
            trials=tuple(self.over(source, period_column=period_column, periods=periods))
        )

    def _trial(self, control: Control, *, label: str) -> Trial:
        started = time.monotonic()
        try:
            plan = resolved(control)
            compiled = compile_for(
                plan, self._engine, table=plan.scope.dataset, scan_limit=self._max_rows
            )
        except Exception as exc:
            return Trial(
                label=label,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=_since(started),
            )

        query = compiled.metric_query
        try:
            rows = list(self._execute(query))
        except Exception as exc:
            return Trial(
                label=label,
                error=f"{type(exc).__name__}: {exc}",
                query=query,
                elapsed_ms=_since(started),
            )

        metrics = {
            str(k): float(v)
            for k, v in (rows[0].items() if rows else [])
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        scanned = metrics.get("scanned_rows", 0.0)
        if not rows or scanned <= 0:
            # Not a pass. Nothing was tested, and a period reported as passing
            # because it was empty is the single easiest way to make a backtest
            # flatter than the truth.
            return Trial(
                label=label,
                verdict="no_data",
                detail="no rows were in scope, so the control tested nothing",
                query=query,
                elapsed_ms=_since(started),
                screen_is_complete=compiled.is_complete,
                residual_validators=compiled.residual_validators,
            )

        result = judge(plan, metrics, engine=self._engine)
        verdict = result.verdict.value
        detail = ""
        if not compiled.is_complete and verdict == "pass":
            verdict = "indeterminate"
            residuals = ", ".join(f"{name} on {col}" for name, col in compiled.residual_validators)
            detail = (
                "the query applied a screen rather than the exact test, so this count "
                f"is a lower bound; the residual ({residuals}) has not been run, and a "
                "pass cannot be reported from a screen alone"
            )
        bounded = bool(self._max_rows) and scanned >= self._max_rows
        if bounded:
            detail = (
                f"{detail}; " if detail else ""
            ) + f"the scan stopped at {self._max_rows:,} rows, so these counts are a floor"
        return Trial(
            label=label,
            verdict=verdict,
            scanned_rows=scanned,
            violating_rows=result.violating_rows,
            detail=detail,
            query=query,
            elapsed_ms=_since(started),
            screen_is_complete=compiled.is_complete,
            residual_validators=compiled.residual_validators,
            was_bounded=bounded,
        )


def business_dates(end: date, *, days: int, weekdays_only: bool = True) -> list[date]:
    """The last ``days`` business dates up to and including ``end``.

    Weekdays by default. A backtest that includes weekends on a feed that does
    not deliver at weekends reports two empty periods in every seven, and while
    those are excluded from the rate rather than counted as quiet, they still
    cost two queries each week and clutter the answer.
    """
    dates: list[date] = []
    cursor = end
    while len(dates) < days:
        if not weekdays_only or cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(dates))


def _restricted(control: Control, column: str, period: str) -> Control:
    """The same control, scoped to one business date.

    Built as an AST node rather than spliced into SQL: the period reaches the
    compiler as a ``Literal`` and the column as a ``ColumnRef``, and the
    dialect escapes both. Nothing here concatenates a caller's text into a
    statement, which is why a period containing a quote finds nothing rather
    than doing something.
    """
    predicate = BinaryOp(
        operator="=",
        left=ColumnRef(name=column),
        right=Literal(value=period, literal_type="text"),
    )
    combined = (
        predicate
        if control.where is None
        else BinaryOp(operator="AND", left=control.where, right=predicate)
    )
    return dataclasses.replace(control, where=combined)


def plain_identifier(name: str, *, kind: str = "column") -> str:
    """A plain identifier, or a refusal that says what to type.

    See ``IDENTIFIER``: the dialect's quoting is what makes anything else
    harmless, and this is what makes it legible. Public because the console
    validates a table name the same way and a second copy of the rule is how
    one of them ends up looser.
    """
    candidate = name.strip()
    if not IDENTIFIER.match(candidate):
        raise ValidationError(
            f"{name!r} is not a {kind} name",
            remedy=(
                f"Give a plain identifier such as as_of_date. Quoted, qualified "
                f"and schema-prefixed {kind} names are not accepted here."
            ),
            context={kind: name},
        )
    return candidate


def _since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
