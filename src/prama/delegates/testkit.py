"""The conformance kit a delegate author runs in their own CI, before Prama ever sees it.

Everything Prama will check at admission and at run time, checked here first,
plus the author's own expected answers::

    from prama.delegates.testkit import Case, check_delegate

    def test_settlement_cycle_conforms():
        report = check_delegate(
            "delegates/settlement_cycle.py",
            cases=[Case("one late US trade", rows=[...], violating=1, scanned=1)],
        )
        assert report.ok, report.render()

or, without writing Python: ``prama delegate check delegates/ --cases cases.json``
(exit 0 when every check passes, 1 otherwise).

What it checks, per delegate in the file:

1. **Vetting before import** — the same source scan admission applies. A file
   that fails it is not imported, here either.
2. **Admission** — shape, determinism and robustness on Prama's probe rows.
3. **Parameters** — every default is of its declared kind.
4. **One pass** — the answer over a one-shot iterator equals the answer over a
   list. A delegate that iterates its rows twice works in a test and silently
   sees nothing the second time when Prama streams to it.
5. **Streaming at scale** — synthetic rows sent through the real host in
   batches, sandboxed as in production, within the time limit.
6. **Your cases** — expected scanned, violating, established and observations,
   run through the real host path (JSON values, sandbox, measurement checks).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from prama.delegates.registry import Admitted, DelegateRegistry
from prama.delegates.spi import DqDelegate


@dataclasses.dataclass(frozen=True)
class Case:
    """Rows, parameters, and what the delegate should say about them."""

    name: str
    rows: Sequence[Mapping[str, Any]]
    params: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    scanned: int | None = None
    violating: int | None = None
    established: bool | None = None
    #: A subset: only the observations named here are compared.
    observations: Mapping[str, float] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Case:
        expect = payload.get("expect") or {}
        return cls(
            name=str(payload.get("name", "case")),
            rows=list(payload.get("rows") or []),
            params=dict(payload.get("params") or {}),
            scanned=expect.get("scanned"),
            violating=expect.get("violating"),
            established=expect.get("established"),
            observations=dict(expect.get("observations") or {}),
        )


@dataclasses.dataclass
class Check:
    delegate: str
    name: str
    passed: bool
    detail: str = ""


@dataclasses.dataclass
class Report:
    checks: list[Check] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def add(self, delegate: str, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append(Check(delegate, name, passed, detail))
        return passed

    def render(self) -> str:
        lines = [
            f"{'PASS' if c.passed else 'FAIL'}  {c.delegate}  {c.name}"
            + (f" — {c.detail}" if c.detail else "")
            for c in self.checks
        ]
        verdict = "conforms" if self.ok else "does NOT conform"
        return "\n".join([*lines, f"{len(self.checks)} check(s): {verdict}"])

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checks": [dataclasses.asdict(c) for c in self.checks]}


def control_for(
    name: str, params: Mapping[str, Any] | None = None, *, dataset: str = "rows"
) -> str:
    """The PQL that names *name* with *params*: what a control would say."""
    from prama.pql.ast import Literal, quote_dataset

    kinds = {bool: "boolean", int: "number", float: "number"}
    rendered = [
        f"{key} = {Literal(value=value, literal_type=kinds.get(type(value), 'text')).render()}"
        for key, value in (params or {}).items()
    ]
    source = f"CHECK {quote_dataset(dataset)} USING DELEGATE {Literal(value=name).render()}"
    return source + (f" ({', '.join(rendered)})" if rendered else "")


def _synthetic(delegate: DqDelegate, count: int) -> Iterator[list[dict[str, Any]]]:
    columns = list(delegate.requires) or ["value"]
    batch: list[dict[str, Any]] = []
    for index in range(count):
        batch.append({c: (index * 7919 + j) % 100_003 for j, c in enumerate(columns)})
        if len(batch) == 10_000:
            yield batch
            batch = []
    if batch:
        yield batch


def check_delegate(
    target: str | Path,
    *,
    cases: Sequence[Case] = (),
    sandbox: bool = True,
    large_rows: int = 50_000,
    time_limit_s: float = 60.0,
) -> Report:
    """Run every conformance check against the delegates in *target* (a file or directory)."""
    from prama.classify.plugins import scan_source

    report = Report()
    path = Path(target).resolve()
    files = sorted(path.glob("*.py")) if path.is_dir() else [path]
    for file in files:
        banned = sorted(set(scan_source(str(file))))
        report.add(
            file.name,
            "vetted before import",
            not banned,
            "; ".join(f"{m} — {why}" for m, why in banned),
        )
    registry = DelegateRegistry()
    for directory in {f.parent for f in files}:
        registry.load_paths([str(directory)])
    for name, why in sorted(registry.refused.items()):
        if name.endswith(".py") and "not imported" in why:
            continue  # already reported above
        report.add(name, "admitted", False, why)
    wanted = {f.resolve() for f in files}
    admitted = [a for a in registry.all() if Path(a.origin.partition(":")[2]).resolve() in wanted]
    if not admitted and not report.checks:
        report.add(str(target), "contains a delegate", False, "no DqDelegate subclass found")
    for entry in admitted:
        report.add(entry.name, "admitted", True, f"source {entry.implementation_hash[:12]}")
        _conformance(report, registry, entry, cases, sandbox, large_rows, time_limit_s)
    return report


def _conformance(
    report: Report,
    registry: DelegateRegistry,
    entry: Admitted,
    cases: Sequence[Case],
    sandbox: bool,
    large_rows: int,
    time_limit_s: float,
) -> None:
    from prama.delegates.host import DelegateHost, canonical
    from prama.ir.resolve import resolved
    from prama.pql import parse_control

    delegate, name = entry.delegate, entry.name
    wrong = [
        p.name for p in delegate.parameters if p.default is not None and not p.accepts(p.default)
    ]
    report.add(name, "parameter defaults match their kinds", not wrong, ", ".join(wrong))

    probe = canonical([dict(r) for r in cases[0].rows]) if cases else []
    params = delegate.resolve(dict(cases[0].params) if cases else {})
    once = delegate.measure(iter(probe), params).to_dict()
    listed = delegate.measure(list(probe), params).to_dict()
    report.add(
        name,
        "reads its rows in one pass",
        once == listed,
        "" if once == listed else "a one-shot iterator gave a different answer from a list",
    )

    host = DelegateHost(registry=registry, sandbox=sandbox)
    plan = resolved(parse_control(control_for(name)))
    started = time.monotonic()
    try:
        host.measure_stream(plan, _synthetic(delegate, large_rows))
        took = time.monotonic() - started
        report.add(
            name,
            f"streams {large_rows:,} rows in batches",
            took <= time_limit_s,
            f"{took:.1f}s" + ("" if took <= time_limit_s else f", over {time_limit_s:g}s"),
        )
    except Exception as exc:
        report.add(name, f"streams {large_rows:,} rows in batches", False, str(exc)[:200])

    for case in cases:
        try:
            plan = resolved(parse_control(control_for(name, case.params)))
            result = host.measure_plan(plan, [dict(r) for r in case.rows])
        except Exception as exc:
            report.add(name, f"case: {case.name}", False, str(exc)[:200])
            continue
        metrics = result.metrics
        misses = []
        if case.scanned is not None and metrics["scanned_rows"] != case.scanned:
            misses.append(f"scanned {metrics['scanned_rows']:g}, expected {case.scanned}")
        if case.established is not None and ("violating_rows" in metrics) != case.established:
            misses.append(f"established {'violating_rows' in metrics}, expected {case.established}")
        if case.violating is not None and metrics.get("violating_rows") != case.violating:
            misses.append(f"violating {metrics.get('violating_rows')}, expected {case.violating}")
        for key, value in case.observations.items():
            if key not in metrics:
                misses.append(f"{key} was not observed, expected {value}")
            elif abs(float(metrics[key]) - float(value)) > 1e-9:
                misses.append(f"{key} {metrics[key]:g}, expected {value}")
        report.add(name, f"case: {case.name}", not misses, "; ".join(misses))
