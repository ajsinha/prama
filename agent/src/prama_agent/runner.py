"""The agent: run the work here, send the findings, keep the data at home.

Everything an agent does is shaped by one fact — it is on the customer's
machine, inside their network, holding their credentials. So:

* It **executes** the assignment it was given, against a source only it can
  reach, using a query the control plane compiled. It does not compile its own:
  a second compiler in the estate is how the same control comes to mean two
  things on two machines.
* It **judges** with the plan's own threshold, so a verdict computed on an
  agent is the verdict the control plane would have computed. The judging code
  is shared rather than reimplemented, which is what makes that true rather
  than intended.
* It **redacts** before anything leaves, according to its zone's residency
  policy, and records what it withheld.
* It **spools** when the control plane is unreachable, and keeps working.

The agent never sends raw data it was not told it could, never receives a
credential it does not need, and never asks for work outside its zone. Each of
those is enforced somewhere else in this package rather than trusted here,
because an agent is the part of the system most likely to be running an old
version on a machine nobody has looked at for a year.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from prama_kernel.agent.capability import AgentCapabilities
from prama_kernel.agent.protocol import Assignment, Hello, Receipt, Refusal, Report, Response
from prama_kernel.agent.residency import Boundary, ResidencyPolicy
from prama_kernel.agent.signing import sign_payload
from prama_kernel.agent.spool import Gap, Spool
from prama_kernel.clock import Clock, SystemClock
from prama_kernel.delegates.host import batches_of
from prama_kernel.judge import as_number, judge, judge_segments
from prama_kernel.log import get_logger
from prama_kernel.plan import (
    Comparator,
    ControlPlan,
    Metric,
    MetricAggregate,
    Scope,
    Threshold,
)
from prama_kernel.recon.pql import measure
from prama_kernel.record import EvidenceRecord, SnapshotRef
from prama_kernel.samples import SampleStore

_log = get_logger(__name__)

#: Runs one SQL statement against a local source and returns rows.
Executor = Callable[[str], list[dict[str, Any]]]

#: Asks the local source for its current state identifier, if it has one.
Snapshotter = Callable[[str], Any]

#: Chooses the executor for one assignment — the source its binding names. The
#: daemon's, because an agent beside several sources has one executor per source.
ExecutorFor = Callable[[Assignment], Executor]


@dataclasses.dataclass(frozen=True, slots=True)
class AgentOutcome:
    """What one assignment produced, before anything crossed the boundary."""

    assignment: Assignment
    record: EvidenceRecord | None = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.record is not None


class Agent:
    """Runs assignments locally and reports findings outward."""

    def __init__(
        self,
        agent_id: str,
        key: bytes,
        *,
        executor: Executor | None = None,
        executor_for: ExecutorFor | None = None,
        residency: ResidencyPolicy,
        capabilities: AgentCapabilities | None = None,
        spool: Spool | None = None,
        snapshotter: Snapshotter | None = None,
        clock: Clock | None = None,
        version: str = "",
        delegates: Any = None,
    ) -> None:
        self.agent_id = agent_id
        self._key = key
        if (executor is None) == (executor_for is None):
            raise ValueError("an Agent needs exactly one of executor= or executor_for=")
        # `is None`, not `or`: `Executors` defines __len__, and a falsy router
        # must not be swapped for the absent single executor.
        self._executor_for: ExecutorFor = (
            _always(executor) if executor_for is None else executor_for
        )
        self._boundary = Boundary(residency)
        self._capabilities = capabilities or AgentCapabilities()
        #: A `prama_kernel.delegates.host.DelegateHost` built from this agent's own
        #: configuration (`host_from_config`). What it admitted is what the
        #: agent advertises, so the coordinator only sends it work it can run.
        self._delegates = delegates
        if delegates is not None and not self._capabilities.delegates:
            self._capabilities = dataclasses.replace(
                self._capabilities, delegates=delegates.registry.pinned()
            )
        # `if None`, not `or`: a Spool defines __len__, so an empty one is
        # falsy and `or` would discard the durable spool the caller configured
        # — the agent would buffer to memory and lose everything on restart.
        self._spool = Spool() if spool is None else spool
        #: Gaps handed to the control plane in the last report and not yet
        #: acknowledged. Tracked so a receipt clears exactly what was sent —
        #: see Spool.forget_gaps and finding X3.
        self._gaps_in_flight: tuple[Gap, ...] = ()
        self._snapshotter = snapshotter
        self._clock = clock or SystemClock()
        self._version = version
        #: Samples stay here. The control plane is told they exist and, unless
        #: residency permits, never what is in them.
        self._local_samples: dict[str, list[dict[str, Any]]] = {}

    @property
    def spool(self) -> Spool:
        return self._spool

    @property
    def residency(self) -> ResidencyPolicy:
        return self._boundary.policy

    def local_samples(self, digest: str) -> list[dict[str, Any]]:
        """Failing rows that never left. The reason 'investigate at' has an at."""
        return list(self._local_samples.get(digest, ()))

    # -- doing the work ----------------------------------------------------

    def run(self, assignment: Assignment) -> AgentOutcome:
        """Execute one assignment and spool the finding.

        An execution failure is recorded as an error verdict rather than
        raised. An agent that stopped on the first unreadable source would take
        the rest of its zone's controls down with it, and the estate would go
        unchecked for a reason nobody can see from the control plane.
        """
        started = self._clock.now()
        plan = _plan_stub(assignment)
        try:
            # Which source: chosen inside the try, so an assignment naming a
            # source this agent does not have is an error finding, not a crash.
            execute = self._executor_for(assignment)
            # A delegate's rows are streamed to it below, in batches, rather
            # than fetched whole here.
            rows = [] if plan.assertion_kind == "delegate" else execute(assignment.metric_query)
        except Exception as exc:  # a source that will not answer is a finding
            record = self._error_record(assignment, started, f"{type(exc).__name__}: {exc}")
            return AgentOutcome(
                assignment=assignment, record=self._spool.add(record), error=str(exc)
            )

        extra: dict[str, str] = {}
        note = ""
        if plan.assertion_kind == "reconcile":
            try:
                recon_metrics, recon = measure(
                    plan,
                    rows,
                    execute(assignment.counterpart_query),
                    business_date=started.date(),
                    rates=execute(assignment.rates_query) if assignment.rates_query else None,
                )
            except Exception as exc:  # a reconciliation that cannot run is a finding
                record = self._error_record(assignment, started, f"reconciliation: {exc}")
                return AgentOutcome(
                    assignment=assignment, record=self._spool.add(record), error=str(exc)
                )
            result = judge(plan, recon_metrics, engine=assignment.engine)
            # The breaks carry keys and amounts: samples, subject to residency.
            samples = [b.to_dict() for b in recon.population.needs_a_person][:50]
            note = recon.headline()
        elif plan.assertion_kind == "delegate":
            try:
                if self._delegates is None:
                    raise ValueError("this agent has no delegates configured")
                measured = self._delegates.measure_stream(
                    plan,
                    batches_of(execute, assignment.metric_query, self._delegates.batch_rows),
                )
            except Exception as exc:  # a delegate that cannot answer is a finding
                record = self._error_record(assignment, started, f"delegate: {exc}")
                return AgentOutcome(
                    assignment=assignment, record=self._spool.add(record), error=str(exc)
                )
            result = judge(plan, measured.metrics, engine=assignment.engine)
            samples = measured.samples if result.verdict.value != "pass" else []
            extra, note = measured.parameters, measured.note
        else:
            result = self._judge(assignment, plan, rows)
            samples = self._collect_samples(assignment, execute)
        redaction = self._boundary.apply(samples)
        digest = ""
        if samples:
            digest = SampleStore().put(samples).digest
            # Held here whatever the policy decided. Withholding from the
            # control plane is not the same as discarding, and an investigator
            # in the zone still needs the rows.
            self._local_samples[digest] = samples

        finished = self._clock.now()
        record = EvidenceRecord(
            plan_id=assignment.plan_id,
            control_id=assignment.plan.get("control_id", ""),
            dataset=assignment.dataset,
            binding=assignment.binding,
            snapshot=self._snapshot(assignment),
            parameters={**assignment.parameters, **extra},
            detail=note,
            engine=assignment.engine,
            verdict=result.verdict.value,
            metrics=dict(result.metrics),
            samples_digest=digest if redaction.carried_anything else "",
            sample_count=len(samples),
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
            triggered_by=f"agent:{self.agent_id}",
        )
        return AgentOutcome(assignment=assignment, record=self._spool.add(record))

    def _judge(self, assignment: Assignment, plan: ControlPlan, rows: list[dict[str, Any]]) -> Any:
        names = assignment.metric_names or tuple(m.name for m in plan.metrics)
        if plan.scope.segment_by:
            segmented = [
                (
                    "|".join(str(row[c]) for c in plan.scope.segment_by),
                    {n: v for n in names if (v := as_number(row.get(n))) is not None},
                )
                for row in rows
            ]
            return judge_segments(plan, segmented, engine=assignment.engine)
        first = rows[0] if rows else {}
        return judge(
            plan,
            {n: v for n in names if (v := as_number(first.get(n))) is not None},
            engine=assignment.engine,
        )

    def _collect_samples(self, assignment: Assignment, execute: Executor) -> list[dict[str, Any]]:
        if not assignment.sample_query:
            return []
        try:
            return execute(assignment.sample_query)
        except Exception as exc:  # samples are useful, not essential
            _log.info("samples unavailable for %s: %s", assignment.plan_id, exc)
            return []

    def _snapshot(self, assignment: Assignment) -> SnapshotRef:
        if self._snapshotter is None:
            return SnapshotRef(kind="none", identifier="", exact=False)
        try:
            snapshot = self._snapshotter(assignment.dataset)
        except Exception:  # a source that cannot name its state says so
            return SnapshotRef(kind="none", identifier="", exact=False)
        if snapshot is None:
            return SnapshotRef(kind="none", identifier="", exact=False)
        return SnapshotRef(
            kind=getattr(snapshot.kind, "value", str(snapshot.kind)),
            identifier=str(snapshot.identifier),
            exact=bool(snapshot.exact),
        )

    def _error_record(self, assignment: Assignment, started: Any, detail: str) -> EvidenceRecord:
        finished = self._clock.now()
        return EvidenceRecord(
            plan_id=assignment.plan_id,
            dataset=assignment.dataset,
            binding=assignment.binding,
            snapshot=SnapshotRef(kind="none", identifier="", exact=False),
            parameters=dict(assignment.parameters),
            engine=assignment.engine,
            verdict="error",
            metrics={},
            detail=detail,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            triggered_by=f"agent:{self.agent_id}",
        )

    # -- talking to the control plane --------------------------------------

    def hello(self) -> tuple[Hello, str]:
        message = Hello(
            agent_id=self.agent_id,
            version=self._version,
            capabilities=self._capabilities,
            pending_findings=len(self._spool),
            free_slots=self._capabilities.max_concurrency,
        )
        return message, self._sign(message.signable())

    def report(self, batch_size: int = 500) -> tuple[Report, str]:
        """Everything waiting to be sent, redacted by the zone's policy."""
        # Remembered, so the receipt clears exactly what this report carried
        # and not whatever the spool happens to hold when it arrives. See
        # Spool.forget_gaps and finding X3.
        self._gaps_in_flight = self._spool.gaps
        message = Report(
            agent_id=self.agent_id,
            records=tuple(self._spool.batch(batch_size)),
            gaps=self._gaps_in_flight,
            residency={
                "zone": self.residency.zone,
                "samples": self.residency.samples.value,
                "describes": self.residency.describe(),
            },
        )
        return message, self._sign(message.signable())

    def apply(self, response: Response) -> bool:
        """Act on what the control plane said. False means stop.

        A permanent refusal stops the agent. Retrying forever after revocation
        is a revoked agent generating load and log noise for as long as it is
        left running.
        """
        if isinstance(response, Refusal):
            _log.error("control plane refused this agent: %s", response.reason)
            if response.remedy:
                _log.error("  remedy: %s", response.remedy)
            return not response.permanent
        assert isinstance(response, Receipt)
        if response.accepted_through >= 0:
            self._spool.acknowledge(response.accepted_through)
            # Only what was actually sent. A `hello` receipt reaches this same
            # method and carries the previously accepted sequence, so clearing
            # unconditionally here deleted gaps that had never been reported —
            # a hole in the evidence, forgotten without anyone being told.
            if self._gaps_in_flight:
                self._spool.forget_gaps(self._gaps_in_flight)
                self._gaps_in_flight = ()
        for entry in response.unassignable:
            _log.warning(
                "no agent in this zone can run %s: %s",
                entry.get("dataset"),
                "; ".join(entry.get("reasons", ())),
            )
        return True

    def _sign(self, payload: str) -> str:
        return sign_payload(self._key, payload)


def _always(executor: Executor | None) -> ExecutorFor:
    """One executor for every assignment: an agent beside a single source."""
    assert executor is not None

    def choose(_assignment: Assignment) -> Executor:
        return executor

    return choose


def _plan_stub(assignment: Assignment) -> ControlPlan:
    """Rebuild the plan the control plane sent.

    Only the parts judging needs: the assertion kind, the metrics' shape, the
    threshold and the segmentation. The agent does not re-derive a plan from a
    control — it was given one — so this reads what arrived rather than
    recomputing anything.
    """
    payload = assignment.plan
    threshold = payload.get("threshold") or {}
    scope = payload.get("scope") or {}
    metrics = tuple(
        Metric(
            name=str(m.get("name", "")),
            aggregate=MetricAggregate(m.get("agg", "count")),
            applies_unknown_policy=bool(m.get("unknown_policy", False)),
        )
        for m in payload.get("metrics") or ()
    )
    return ControlPlan(
        scope=Scope(
            dataset=str(scope.get("dataset", assignment.dataset)),
            binding=str(scope.get("binding", assignment.binding)),
            segment_by=tuple(scope.get("segment_by") or ()),
        ),
        metrics=metrics,
        threshold=Threshold(
            metric=str(threshold.get("metric", "violating_rows")),
            comparator=Comparator(threshold.get("op", "<=")),
            value=float(threshold.get("value", 0.0)),
            relative_to=str(threshold.get("relative_to", "")),
        ),
        assertion_kind=str(payload.get("assertion_kind", "predicate")),
        detail=dict(payload.get("detail") or {}),
    )
