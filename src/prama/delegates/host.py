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
import os
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from prama.core.errors import ValidationError
from prama.delegates.registry import Admitted, DelegateRegistry, from_config
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

    def columns(self, detail: dict[str, Any]) -> tuple[str, ...]:
        """The columns to fetch for a plan: the delegate's own `requires`, if installed here."""
        try:
            return tuple(self.registry.get(str(detail.get("delegate", ""))).delegate.requires)
        except Exception:
            return ()

    def measure_plan(self, plan: Any, rows: Sequence[dict[str, Any]]) -> DelegateResult:
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
        if len(rows) > self.max_rows:
            raise ValidationError(
                f"{len(rows):,} rows exceed delegates.max_rows ({self.max_rows:,})",
                remedy=(
                    "Narrow the control with WHERE, or raise delegates.max_rows on this "
                    "host. A delegate never sees a silently truncated dataset."
                ),
            )
        payload = canonical(rows)
        measurement = (
            self._sandboxed(admitted, payload, params)
            if self.sandbox
            else delegate.measure(iter(payload), params)
        )
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
        self, admitted: Admitted, rows: list[dict[str, Any]], params: dict[str, Any]
    ) -> Measurement:
        from prama.codeintake.worker import limit_resources

        request = json.dumps(
            {"name": admitted.name, "origin": admitted.origin, "params": params, "rows": rows}
        )
        cpu, memory = self.timeout_s, self.memory_mb << 20

        def limits() -> None:
            limit_resources(cpu_seconds=cpu, memory_bytes=memory)

        try:
            completed = subprocess.run(
                [sys.executable, "-m", "prama.delegates.worker"],
                input=request.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout_s + 5,
                check=False,
                preexec_fn=limits if os.name == "posix" else None,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            raise ValidationError(
                f"{admitted.name} ran longer than {self.timeout_s}s",
                remedy="Narrow the control with WHERE, or raise delegates.timeout on this host.",
            ) from exc
        try:
            answer = json.loads(completed.stdout.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            answer = {}
        if completed.returncode != 0 or "measurement" not in answer:
            why = answer.get("error") or completed.stderr.decode("utf-8", "replace")[-400:]
            raise ValidationError(
                f"{admitted.name} failed in its sandbox: {why.strip() or completed.returncode}",
                remedy="Run `prama delegate test` against sample rows to reproduce it.",
            )
        return Measurement.from_dict(answer["measurement"])


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
    )
