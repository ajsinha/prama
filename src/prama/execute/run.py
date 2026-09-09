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
from typing import Any

from prama.backend import compile_for, judge
from prama.classify.validators import ValidatorRegistry, default_registry
from prama.core.clock import Clock, SystemClock
from prama.core.errors import PramaError
from prama.core.log import get_logger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.ir import lower
from prama.pql import parse_control

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

    def describe(self) -> str:
        """A sentence naming what did *not* happen as well as what did.

        A run summary that reports only verdicts reads as complete whatever
        proportion of the estate refused to execute.
        """
        if not self.outcomes:
            return "no controls were live, so nothing ran"
        parts = [f"{len(self.outcomes)} control(s)"]
        parts += [f"{count} {verdict}" for verdict, count in sorted(self.verdicts.items())]
        if self.failed_to_run:
            parts.append(f"{self.failed_to_run} could not be executed at all")
        return ", ".join(parts)


class ControlRun:
    """Executes the live controls for one tenant and writes the evidence.

    Takes a unit of work rather than a database: a run is one transaction, so
    the run row, its records and its samples commit together. A control result
    recorded without the run it belongs to — or a run recorded without its
    results — is worse than neither, because both look complete.
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

    async def execute_all(self) -> RunReport:
        """Run every live control, recording each outcome as it goes."""
        started = self._clock.now()
        run = await self._uow.evidence_runs.start(
            tenant_id=self._tenant,
            triggered_by=self._triggered_by,
            actor_id=self._actor,
            engine=self._engine,
            started_at=started.isoformat(),
        )
        run_id = str(run.id)

        controls = await self._uow.controls.live(self._tenant)
        _log.info("run %s: %d live control(s)", run_id, len(controls))

        outcomes: list[Outcome] = []
        for version in controls:
            outcome = await self._run_one(version, run_id)
            outcomes.append(outcome)

        finished = self._clock.now()
        await self._uow.evidence_runs.finish(
            run_id,
            finished_at=finished.isoformat(),
            # 'complete' means the run finished, not that everything passed.
            # A run in which every control errored still completed; the
            # verdicts say what happened, and conflating the two would hide a
            # total outage behind a green run.
            status="complete",
            detail=RunReport(run_id=run_id, outcomes=tuple(outcomes)).describe(),
        )
        return RunReport(run_id=run_id, outcomes=tuple(outcomes))

    async def _run_one(self, version: Any, run_id: str) -> Outcome:
        started = self._clock.now()
        control_id = str(version.control_id)

        try:
            control = parse_control(version.pql)
            plan = lower(control)
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

        metrics = _metrics_from(rows)
        result = judge(plan, metrics, engine=self._engine)
        verdict = result.verdict.value
        detail = ""

        if not compiled.is_complete and verdict == "pass":
            # The whole reason the two-stage design exists. A lower bound of
            # zero is not "clean" — it is "not established" — and reporting it
            # as a pass is a false assurance about exactly the columns whose
            # validation SQL cannot express.
            verdict = "indeterminate"
            residuals = ", ".join(
                f"{name} on {column}" for name, column in compiled.residual_validators
            )
            detail = (
                "the query applied a screen rather than the exact test, so the "
                f"violation count is a lower bound; the residual ({residuals}) has "
                "not been run, and a pass cannot be reported from a screen alone"
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
