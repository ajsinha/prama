"""One pass over the estate's live controls.

This is the join that turns a stored control estate and a stored evidence
ledger into a system that operates. Everything it needs already existed —
controls persist, plans lower, SQL compiles, ``judge`` decides, the ledger
appends — and none of it was connected, so every screen read evidence that had
to arrive some other way.

Four properties decide whether such a runner is trustworthy, and each is a way
the obvious implementation is wrong:

* **A source that will not answer is a finding, not a crash.** A run that
  stopped on the first unreadable table would take the rest of the estate down
  with it, and the estate would go unchecked for a reason nobody can see. Every
  failure becomes an ``error`` record naming the cause.
* **A run is opened before it does anything.** If the process dies mid-run the
  row stays ``running``, and ``unfinished()`` surfaces it — because a run that
  vanished silently means every screen quietly under-reports.
* **An incomplete screen cannot report a pass.** When the compiled SQL is a
  necessary condition rather than the exact test, its violation count is a
  lower bound. Zero violations from a lower bound is not "clean"; it is "not
  established", and the residual has to run before it can be.
* **Only ``active`` controls run.** Proposals and suppressed controls are
  excluded, so a coverage figure cannot count protection the estate has not
  agreed to.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from prama.backend import compile_for, judge, judge_segments
from prama.classify.validators import ValidatorRegistry, default_registry
from prama.core.clock import Clock, SystemClock
from prama.core.errors import PramaError
from prama.core.log import get_logger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.ir.resolve import resolved
from prama.pql import parse_control
from prama.schedule import Schedule

_log = get_logger(__name__)

#: Runs a query and returns its rows as dictionaries. Deliberately the whole
#: interface: the runner does not open connections, hold credentials or know
#: which engine it is talking to, so the same code serves a warehouse, a test
#: with a dictionary, and an agent forwarding to a zone it cannot reach into.
Executor = Callable[[str], Sequence[dict[str, Any]]]

#: Reads the failing rows for a control, when the compiled plan offers a way.
#: Separate from the executor because sampling is a privacy decision: a
#: deployment that must not move rows supplies no sampler and still gets
#: verdicts.
Sampler = Callable[[str], Sequence[dict[str, Any]]]


@dataclasses.dataclass(frozen=True, slots=True)
class _Elsewhere:
    """A control this pass could not reach, because its data is elsewhere.

    Shaped like a scheduler skip so the report has one list of "not run" rather
    than two the reader has to add up. It is not a defect: an estate with four
    sources runs four passes, and each one legitimately leaves the other three
    alone.
    """

    control_id: str
    dataset: str
    reason: str = "another_source"
    detail: str = ""

    @property
    def is_a_defect(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one control."""

    control_id: str
    record: EvidenceRecord
    error: str = ""

    @property
    def ran(self) -> bool:
        return not self.error


@dataclasses.dataclass(frozen=True, slots=True)
class RunReport:
    """What happened to the estate."""

    run_id: str
    outcomes: tuple[Outcome, ...] = ()
    #: Live controls the schedule left out, with the reason for each. Reported
    #: because a control that silently stops being scheduled is
    #: indistinguishable from one that is passing.
    skipped: tuple[Any, ...] = ()

    @property
    def executed(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.ran)

    @property
    def failed_to_run(self) -> int:
        return sum(1 for outcome in self.outcomes if not outcome.ran)

    @property
    def verdicts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for outcome in self.outcomes:
            counts[outcome.record.verdict] = counts.get(outcome.record.verdict, 0) + 1
        return counts

    @property
    def unschedulable(self) -> tuple[Any, ...]:
        """Controls whose schedule cannot be read.

        They will never run again and have no verdict to say so, which is the
        one skip reason that is a defect rather than the scheduler working.
        """
        return tuple(item for item in self.skipped if getattr(item, "is_a_defect", False))

    def describe(self) -> str:
        """A sentence naming what did *not* happen as well as what did.

        A run summary that reports only verdicts reads as complete whatever
        proportion of the estate refused to execute — or was never asked.
        """
        parts: list[str] = []
        if self.outcomes:
            parts.append(f"{len(self.outcomes)} control(s)")
            parts += [f"{count} {verdict}" for verdict, count in sorted(self.verdicts.items())]
            if self.failed_to_run:
                parts.append(f"{self.failed_to_run} could not be executed at all")
        elif not self.skipped:
            return "no controls were live, so nothing ran"
        else:
            parts.append("nothing was due")
        if self.skipped:
            parts.append(f"{len(self.skipped)} not due")
        if self.unschedulable:
            parts.append(
                f"{len(self.unschedulable)} with a schedule that cannot be read, "
                "which will never run until it is fixed"
            )
        return ", ".join(parts)


class ControlRun:
    """Executes the live controls for one tenant and writes the evidence.

    Takes a unit of work rather than a database: the records and samples are
    one transaction, so a control result recorded without its samples cannot
    happen. A control result recorded without the run it belongs to — or a run
    recorded without its results — is worse than neither, because both look
    complete.

    **The run row is the deliberate exception**, and it has to be. It is opened
    and closed in transactions of their own, because a marker written inside
    the run's transaction does not survive the process dying: the database
    rolls it back, and there is no `running` row for `unfinished()` to find.
    The module docstring promised exactly that recovery and this class promised
    one transaction; they were mutually exclusive as implemented, and the
    marker is the half that has to outlive a crash.

    A run row with no records does not "look complete" — it looks unfinished,
    which is what it is, and what an operator reading "0 unfinished runs"
    needed to be told.
    """

    def __init__(
        self,
        uow: Any,
        tenant_id: str,
        *,
        execute: Executor,
        sample: Sampler | None = None,
        engine: str = "postgresql",
        clock: Clock | None = None,
        triggered_by: str = "schedule",
        actor_id: str | None = None,
        validators: ValidatorRegistry | None = None,
        respect_schedule: bool = False,
        datasets: set[str] | None = None,
    ) -> None:
        self._uow = uow
        self._tenant = tenant_id
        self._execute = execute
        self._sample = sample
        self._engine = engine
        self._clock = clock or SystemClock()
        self._triggered_by = triggered_by
        self._actor = actor_id
        self._validators = validators or default_registry()
        #: Off by default, so ``prama control run`` means "run them now" —
        #: which is what somebody typing it at a terminal means. A timer sets
        #: it, and then only what is due runs.
        self._respect_schedule = respect_schedule
        #: Which datasets this pass can reach. A real estate has more than one
        #: source — a warehouse, a landing zone, a file share — and one
        #: executor speaks to one of them. Running every control against every
        #: source would produce a table-not-found error for each control that
        #: lives somewhere else, and bury the real findings under them.
        #:
        #: ``None`` means "everything", which is right for a single-source
        #: estate and for somebody running by hand.
        self._datasets = datasets

    async def execute_all(self) -> RunReport:
        """Run every live control, recording each outcome as it goes."""
        started = self._clock.now()
        # Committed on its own, before anything else happens. Written inside
        # this run's transaction the row would not survive the process dying —
        # the database rolls the transaction back, so there is no `running` row
        # to find and `unfinished()` returns nothing (finding X5). The module
        # docstring promises the opposite, and the class docstring promises one
        # transaction; both cannot be true, and the marker is the half that has
        # to outlive a crash.
        run = await self._uow.evidence_runs.start(
            tenant_id=self._tenant,
            triggered_by=self._triggered_by,
            actor_id=self._actor,
            engine=self._engine,
            started_at=started.isoformat(),
        )
        run_id = str(run.id)
        # Committed here, before any control runs. A row written and left
        # pending does not survive the process dying — the database rolls the
        # transaction back, so there is no `running` row and `unfinished()`
        # returns nothing (finding X5).
        #
        # On the same session rather than a second one: SQLite permits a single
        # writer, and a second connection trying to write while this
        # transaction holds the lock deadlocks rather than helping. The cost is
        # that a caller with pending work of its own has it committed here too,
        # which is why this is the first thing `execute_all` does.
        await self._uow.commit()

        live = await self._uow.controls.live(self._tenant)
        elsewhere: list[Any] = []
        if self._datasets is not None:
            reachable = [c for c in live if c.dataset in self._datasets]
            # Counted, not silently dropped. "This pass covered 12 of the
            # estate's 40 controls" is a fact the reader needs; a run that
            # reported 12 controls and said nothing about the other 28 reads
            # as an estate of 12.
            elsewhere = [
                _Elsewhere(control_id=str(c.control_id), dataset=c.dataset)
                for c in live
                if c.dataset not in self._datasets
            ]
            live = reachable
        controls, skipped = await self._select(live)
        skipped = (*skipped, *elsewhere)
        _log.info("run %s: %d of %d live control(s) selected", run_id, len(controls), len(live))

        outcomes: list[Outcome] = []
        for version in controls:
            outcome = await self._run_one(version, run_id)
            outcomes.append(outcome)

        report = RunReport(run_id=run_id, outcomes=tuple(outcomes), skipped=skipped)
        finished = self._clock.now()
        # Closed in its own transaction too, for the same reason the opening
        # was: a run marked complete inside a transaction that then fails to
        # commit is a run that looks finished and wrote nothing.
        await self._uow.evidence_runs.finish(
            run_id,
            finished_at=finished.isoformat(),
            # 'complete' means the run finished, not that everything passed. A
            # run in which every control errored still completed; the verdicts
            # say what happened, and conflating the two would hide a total
            # outage behind a green run.
            status="complete",
            detail=report.describe(),
        )
        return report

    async def _select(self, live: list[Any]) -> tuple[list[Any], tuple[Any, ...]]:
        """Which of the live controls this pass will run.

        When the schedule is not being respected — somebody typed the command —
        everything live runs and nothing is skipped, because a person asking
        for a run means now.
        """
        if not self._respect_schedule:
            return live, ()
        history = await self._uow.evidence.last_run_at(self._tenant)
        plan = Schedule().plan(
            live,
            now=self._clock.now(),
            last_run={control_id: _parse_instant(stamp) for control_id, stamp in history.items()},
        )
        selected = {item.control_id for item in plan.due}
        return [c for c in live if str(c.control_id) in selected], plan.skipped

    async def _run_one(self, version: Any, run_id: str) -> Outcome:
        started = self._clock.now()
        control_id = str(version.control_id)

        try:
            control = parse_control(version.pql)
            plan = resolved(control)
            compiled = compile_for(plan, self._engine, table=plan.scope.dataset)
        except (PramaError, Exception) as exc:
            # A control that will not compile today is a finding about the
            # estate, recorded like any other. Raising would take every control
            # after it down with it.
            return await self._record_error(
                version, run_id, started, f"could not be compiled: {exc}"
            )

        try:
            rows = list(self._execute(compiled.metric_query))
        except Exception as exc:
            return await self._record_error(
                version, run_id, started, f"{type(exc).__name__}: {exc}"
            )

        # A segmented control returns one row per segment, and judging only the
        # first is judging one desk and reporting the trading floor. `rows[0]`
        # was all `_metrics_from` ever looked at, so 1 segment of 5 decided the
        # verdict, the totals came from that segment alone, and the samples in
        # the same record contradicted its own metrics (QA finding Q-11).
        # `judge_segments` has been in the backend all along: the control fails
        # if *any* segment does, because aggregating them back into one number
        # restores exactly the averaging segmentation exists to avoid.
        if plan.scope.segment_by and len(rows) > 1:
            result = judge_segments(
                plan, _segments_from(rows, plan.scope.segment_by), engine=self._engine
            )
            metrics = dict(result.metrics)
        else:
            metrics = _metrics_from(rows)
            result = judge(plan, metrics, engine=self._engine)
            # The *derived* metrics, not the raw ones. `judge` enriches a copy,
            # so `violating_rows` for a uniqueness or functional-dependency
            # control — which no engine returns and Prama computes from the two
            # counts — existed only inside the result and never reached the
            # ledger (QA finding Q-13). The verdict was right and the evidence
            # supporting it was missing the number it was based on.
            metrics = dict(result.metrics)
        verdict = result.verdict.value
        detail = ""

        if not compiled.is_complete:
            residuals = ", ".join(
                f"{name} on {column}" for name, column in compiled.residual_validators
            )
            if verdict == "pass":
                # The whole reason the two-stage design exists. A lower bound of
                # zero is not "clean" — it is "not established" — and reporting
                # it as a pass is a false assurance about exactly the columns
                # whose validation SQL cannot express.
                verdict = "indeterminate"
                detail = (
                    "the query applied a screen rather than the exact test, so the "
                    f"violation count is a lower bound; the residual ({residuals}) has "
                    "not been run, and a pass cannot be reported from a screen alone"
                )
            else:
                # A *failing* count from a screen is understated too, and this
                # caveat used to be attached only when the verdict would have
                # been a pass — so 11-of-23 and 3-of-9 were recorded as
                # completed measurements with nothing said (QA finding Q-10).
                # Disclosed exactly when the understatement was zero, and
                # silent whenever it was not.
                detail = (
                    "the query applied a screen rather than the exact test, so "
                    f"{metrics.get('violating_rows', 0):g} is a LOWER BOUND on the "
                    f"violations; the residual ({residuals}) has not been run and "
                    "the true count may be higher"
                )

        digest, sample_count = await self._store_samples(compiled, verdict)
        finished = self._clock.now()
        record = await self._uow.evidence.append(
            EvidenceRecord(
                plan_id=plan.plan_id,
                control_id=control_id,
                control_version=version.version,
                dataset=plan.scope.dataset,
                binding=plan.scope.binding,
                snapshot=SnapshotRef(kind="wall_clock", identifier=started.isoformat()),
                engine=self._engine,
                coverage="full",
                verdict=verdict,
                metrics=metrics,
                # The threshold the verdict was measured against. Without it,
                # four records can carry identical metrics and opposite
                # verdicts, distinguishable only by `plan_id` — a hash, so
                # answering "why did this fail?" means resolving the plan
                # (QA finding Q-15). It sits inside `content()`, so the record
                # hash covers it like everything else.
                parameters={
                    "threshold": ", ".join(
                        f"{key}={value}" for key, value in sorted(plan.threshold.to_dict().items())
                    )
                },
                samples_digest=digest,
                sample_count=sample_count,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
                triggered_by=self._triggered_by,
                tenant_id=self._tenant,
                detail=detail,
                dimensions=tuple(plan.dimensions),
                criticality=version.criticality,
            ),
            tenant_id=self._tenant,
            run_id=run_id,
        )
        return Outcome(control_id=control_id, record=record)

    async def _store_samples(self, compiled: Any, verdict: str) -> tuple[str, int]:
        """Collect failing rows, if there are any and a sampler was given.

        Only for a control that did not pass: sampling a passing control reads
        rows nobody needs and puts personal data on a retention clock for no
        reason.
        """
        if self._sample is None or verdict == "pass" or not compiled.sample_query:
            return "", 0
        try:
            rows = list(self._sample(compiled.sample_query))
        except Exception as exc:
            # A sampling failure must not turn a real verdict into an error.
            # The verdict was established by the metric query; what is lost is
            # the ability to show which rows, and that is a smaller loss than
            # discarding the finding.
            _log.warning("samples could not be collected: %s", exc)
            return "", 0
        if not rows:
            return "", 0
        from prama.evidence.recorder import SampleStore

        sample = SampleStore().put(rows)
        await self._uow.samples.put(
            tenant_id=self._tenant,
            digest=sample.digest,
            rows=list(rows),
            masked=sample.masked,
            created_at=self._clock.now().isoformat(),
        )
        return sample.digest, sample.count

    async def _record_error(self, version: Any, run_id: str, started: Any, detail: str) -> Outcome:
        finished = self._clock.now()
        record = await self._uow.evidence.append(
            EvidenceRecord(
                control_id=str(version.control_id),
                control_version=version.version,
                dataset=version.dataset,
                engine=self._engine,
                verdict="error",
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
                triggered_by=self._triggered_by,
                tenant_id=self._tenant,
                detail=detail,
                dimensions=tuple(version.dimensions_json or ()),
                criticality=version.criticality,
            ),
            tenant_id=self._tenant,
            run_id=run_id,
        )
        _log.warning("control %s did not run: %s", version.control_id, detail)
        return Outcome(control_id=str(version.control_id), record=record, error=detail)


def _segments_from(
    rows: Sequence[dict[str, Any]], segment_by: Sequence[str]
) -> list[tuple[str, dict[str, float]]]:
    """One (label, metrics) pair per segment, from the grouped metric query.

    The label is the segment's own key values joined, because that is what a
    reader needs to act: "EMEA failed" is a finding and "segment 3 failed" is a
    lookup.
    """
    pairs: list[tuple[str, dict[str, float]]] = []
    for row in rows:
        key = " / ".join(str(row.get(column, "")) for column in segment_by)
        numbers = {
            str(name): float(value)
            for name, value in row.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        pairs.append((key or "(unlabelled)", numbers))
    return pairs


def _metrics_from(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """The metric query's single row, as numbers.

    An empty result is an empty metric set rather than zeros. Zeros would be
    judged — as a pass, since nothing violated — and "the query returned no
    rows" is not a measurement of anything.
    """
    if not rows:
        return {}
    return {
        str(key): float(value)
        for key, value in rows[0].items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _parse_instant(stamp: str) -> datetime:
    """An ISO-8601 timestamp from the ledger, as an aware datetime.

    Aware, always. A naive one compared against an aware ``now`` raises, and it
    would raise inside the scheduler — where the failure is a run that does
    nothing rather than an obvious error.
    """
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
