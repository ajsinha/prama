"""Running a delegate for one control, the same way on the server and on an agent.

`DelegateHost.measure_plan` is the one path from a delegate plan and its rows to
the metrics `judge` reads. The control plane's run and an agent beside the data
both call it, so a delegate's result cannot mean one thing in one place and
something else in the other.

By default the delegate runs in a separate process (`prama.delegates.worker`)
with CPU, memory and open-file limits set before it starts: a delegate that
loops or allocates without bound exhausts its own worker, never the host. The
rows it sees are JSON values in both modes, so switching the sandbox off for a
test changes where it runs, not what it sees.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
import json
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from prama.core.errors import ValidationError
from prama.delegates.registry import Admitted, DelegateRegistry, from_config
from prama.delegates.sandbox import isolation_in_force, run_isolated
from prama.delegates.spi import Measurement

#: Metric names a delegate observation may not take: the two the threshold reads.
_RESERVED = frozenset({"scanned_rows", "violating_rows"})


def _jsonable(value: Any) -> Any:
    if isinstance(value, _dt.datetime | _dt.date | _dt.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    return str(value)


def canonical(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows as JSON values: what every engine's answer looks like to a delegate."""
    return list(json.loads(json.dumps(list(rows), default=_jsonable)))


@dataclasses.dataclass(frozen=True, slots=True)
class DelegateResult:
    """What one delegate run contributes to an evidence record."""

    metrics: dict[str, float]
    samples: list[dict[str, Any]]
    #: Recorded on the evidence: which delegate, which version, which source hash.
    parameters: dict[str, str]
    note: str = ""


@dataclasses.dataclass
class DelegateHost:
    """The delegates this process may run, and how it runs them."""

    registry: DelegateRegistry = dataclasses.field(default_factory=DelegateRegistry)
    sandbox: bool = True
    timeout_s: int = 120
    memory_mb: int = 2048
    #: A dataset larger than this is refused, not truncated: a truncated scan
    #: reported as the whole would be a pass nobody earned.
    max_rows: int = 5_000_000
    #: Rows fetched from the engine's cursor at a time.
    batch_rows: int = 10_000
    #: Where approved uploads are written, content-addressed, before a run.
    upload_dir: str = "data/delegates"

    async def adopt_uploads(self, uow: Any, tenant_id: str) -> int:
        """Register the tenant's approved uploads (`prama.delegates.uploads.adopt`)."""
        from prama.delegates.uploads import adopt

        return await adopt(uow, tenant_id, self)

    def columns(self, detail: dict[str, Any]) -> tuple[str, ...]:
        """The columns to fetch for a plan: the delegate's own `requires`, if installed here."""
        try:
            return tuple(self.registry.get(str(detail.get("delegate", ""))).delegate.requires)
        except Exception:
            return ()

    def measure_plan(self, plan: Any, rows: Sequence[dict[str, Any]]) -> DelegateResult:
        """One delegate run over rows already in memory."""
        return self.measure_stream(plan, [rows])

    def measure_stream(
        self, plan: Any, batches: Iterable[Sequence[dict[str, Any]]]
    ) -> DelegateResult:
        """One delegate run over rows arriving in batches, never all held at once.

        The delegate receives a lazy iterator. Sandboxed, rows cross to the
        worker as JSON lines through a pipe, whose fixed buffer is the byte
        bound: the engine's cursor is not read faster than the delegate
        consumes. A delegate that materialises its input (`list(rows)`) still
        works, and uses the memory it asked for, inside its own limits.
        """
        detail = plan.detail
        admitted = self.registry.get(
            str(detail.get("delegate", "")), version=str(detail.get("version", ""))
        )
        delegate = admitted.delegate
        if delegate.unit == "findings" and plan.threshold.relative_to:
            raise ValidationError(
                f"{delegate.name} counts findings, so a rate threshold means nothing for it",
                remedy="Give the threshold as a number: AT MOST 0 ROWS.",
            )
        params = delegate.resolve(dict(detail.get("parameters") or {}))
        counter = _Counter(self.max_rows)
        from prama.telemetry import metrics

        sandboxed = self.sandbox or admitted.sandbox_only
        try:
            if sandboxed:
                measurement = self._sandboxed(admitted, counter.lines(batches), params)
            else:
                measurement = delegate.measure(counter.rows(batches), params)
        except ValidationError as exc:
            timed_out = "ran longer than" in str(exc)
            metrics.DELEGATES.inc(outcome="timeout" if timed_out else "failed")
            raise
        metrics.DELEGATES.inc(outcome="measured")
        # Checked after the run as well as during it: a delegate that swallowed
        # the stop and reported on a truncated input must not be believed.
        counter.check()
        result = self._result(plan, admitted, measurement)
        result.parameters["delegate_isolation"] = isolation_in_force(sandboxed)
        return result

    def _result(self, plan: Any, admitted: Admitted, measurement: Measurement) -> DelegateResult:
        delegate = admitted.delegate
        problems = measurement.problems(unit=delegate.unit)
        clash = sorted(_RESERVED & set(measurement.observations))
        if clash:
            problems.append(f"observations may not be named {', '.join(clash)}")
        if problems:
            raise ValidationError(
                f"{delegate.name} returned a measurement that cannot be judged: "
                + "; ".join(problems),
                remedy="Fix the delegate; the control is recorded as an error until then.",
            )
        metrics = {
            "scanned_rows": float(measurement.scanned),
            "violating_rows": float(measurement.violating),
            **{k: float(v) for k, v in sorted(measurement.observations.items())},
        }
        if not measurement.established:
            # Without the metric the threshold reads, `judge` answers
            # INDETERMINATE — the shared rule, not a delegate special case.
            del metrics["violating_rows"]
        keep = 0 if plan.evidence.level == "counts" else plan.evidence.max_samples
        return DelegateResult(
            metrics=metrics,
            samples=[dict(s) for s in measurement.samples[:keep]],
            parameters={
                "delegate": f"{delegate.name}@{admitted.version}",
                "delegate_hash": admitted.implementation_hash,
                "delegate_origin": admitted.origin,
                "delegate_unit": delegate.unit,
            },
            note=measurement.note,
        )

    def _sandboxed(
        self, admitted: Admitted, lines: Iterable[bytes], params: dict[str, Any]
    ) -> Measurement:
        header = {
            "name": admitted.name,
            "origin": admitted.origin,
            "params": params,
            "source_hash": admitted.source_hash,
        }
        first = [json.dumps(header).encode("utf-8") + b"\n"]
        try:
            finished = run_isolated(
                ["-m", "prama.delegates.worker"],
                chunks=[*first, *lines],
                timeout_s=self.timeout_s,
                memory_mb=self.memory_mb,
            )
        except TimeoutError as exc:
            raise ValidationError(
                f"{admitted.name} ran longer than {self.timeout_s}s",
                remedy="Narrow the control with WHERE, or raise delegates.timeout here.",
            ) from exc
        try:
            answer = json.loads(finished.output.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            answer = {}
        if finished.returncode != 0 or "measurement" not in answer:
            why = answer.get("error") or finished.errors
            raise ValidationError(
                f"{admitted.name} failed in its sandbox: {why.strip() or finished.returncode}",
                remedy="Run `prama delegate test` against sample rows to reproduce it.",
            )
        return Measurement.from_dict(answer["measurement"])


class _Counter:
    """Counts rows as they stream, and stops the stream past the ceiling."""

    def __init__(self, ceiling: int) -> None:
        self.ceiling = ceiling
        self.seen = 0
        self.exceeded = False

    def _admit(self) -> bool:
        self.seen += 1
        if self.seen > self.ceiling:
            self.exceeded = True
        return not self.exceeded

    def rows(self, batches: Iterable[Sequence[dict[str, Any]]]) -> Iterator[dict[str, Any]]:
        for batch in batches:
            for row in canonical(batch):
                if not self._admit():
                    return
                yield row

    def lines(self, batches: Iterable[Sequence[dict[str, Any]]]) -> Iterator[bytes]:
        for batch in batches:
            out = []
            for row in batch:
                if not self._admit():
                    break
                out.append(json.dumps(row, default=_jsonable).encode("utf-8"))
            if out:
                yield b"\n".join(out) + b"\n"
            if self.exceeded:
                return

    def check(self) -> None:
        if self.exceeded:
            raise ValidationError(
                f"more than {self.ceiling:,} rows exceed delegates.max_rows",
                remedy=(
                    "Narrow the control with WHERE, or raise delegates.max_rows on this "
                    "host. A delegate never sees a silently truncated dataset."
                ),
            )


def batches_of(execute: Any, sql: str, size: int) -> Iterable[Sequence[dict[str, Any]]]:
    """Rows for *sql* in batches: the executor's own cursor batching if it has
    one (`execute.batches`), otherwise its whole answer as one batch."""
    batched = getattr(execute, "batches", None)
    if callable(batched):
        return batched(sql, size)  # type: ignore[no-any-return]
    return [list(execute(sql))]


def host_from_config(config: Any) -> DelegateHost:
    """The host `delegates:` in configuration describes."""
    section = config.get("delegates", {}) if hasattr(config, "get") else {}
    section = section or {}
    return DelegateHost(
        registry=from_config(config),
        sandbox=bool(section.get("sandbox", True)),
        timeout_s=int(section.get("timeout", 120)),
        memory_mb=int(section.get("memory_mb", 2048)),
        max_rows=int(section.get("max_rows", 5_000_000)),
        batch_rows=int(section.get("batch_rows", 10_000)),
        upload_dir=str(section.get("upload_dir", "data/delegates")),
    )
