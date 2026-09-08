"""Running the corpus on every engine and insisting they agree.

The claim Wave 4 makes is that a control written once means the same thing
wherever it runs. This is where that claim is either true or found out.

What "agree" means is defined narrowly and on purpose: the same verdict, the
same metrics to nine decimal places, the same per-segment breakdown. Not the
same SQL — the whole point is that the SQL differs. Not the same sample rows —
row order is not part of a control's meaning, and comparing it would produce
failures that mean nothing and train everyone to ignore the suite.

An engine that legitimately cannot express a case must *refuse* it. A refusal
is a conforming outcome; a wrong answer is not. That distinction is the entire
value of the exercise.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from prama.backend.corpus import CASES, Case
from prama.backend.execute import ControlResult, judge, judge_segments
from prama.backend.sql import SqlCompiler
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan
from prama.pql.errors import PqlUnsupportedError
from prama.pql.parser import parse_control

#: A function that runs one SQL statement and returns rows as dictionaries.
Runner = Callable[[str], list[dict[str, Any]]]


@dataclasses.dataclass(frozen=True, slots=True)
class EngineOutcome:
    """What one engine did with one case."""

    engine: str
    case: str
    #: ``ran``, ``refused`` or ``failed``.
    status: str
    result: ControlResult | None = None
    detail: str = ""

    @property
    def comparable(self) -> Any:
        return self.result.comparable() if self.result else {"status": self.status}


@dataclasses.dataclass(frozen=True, slots=True)
class Disagreement:
    """Two engines that answered differently. The only interesting output."""

    case: str
    outcomes: dict[str, Any]

    def render(self) -> str:
        lines = [f"{self.case}: engines disagree"]
        for engine, answer in sorted(self.outcomes.items()):
            lines.append(f"  {engine}: {answer}")
        return "\n".join(lines)


class ConformanceRun:
    """Runs the corpus across engines and reports where they part company."""

    def __init__(self, table: str = "corpus") -> None:
        self._table = table
        self._plans: dict[str, ControlPlan] = {}

    def plan_for(self, case: Case) -> ControlPlan:
        if case.name not in self._plans:
            self._plans[case.name] = Lowerer().control(parse_control(case.pql))
        return self._plans[case.name]

    def run_case(self, case: Case, engine: str, runner: Runner) -> EngineOutcome:
        plan = self.plan_for(case)
        try:
            compiled = SqlCompiler(engine).compile(plan, table=self._table)
        except PqlUnsupportedError as exc:
            # A refusal is a conforming outcome. It is the promise being kept.
            return EngineOutcome(
                engine=engine, case=case.name, status="refused", detail=str(exc.args[0])
            )
        try:
            rows = runner(compiled.metric_query)
        except Exception as exc:  # a driver error is a conformance failure
            return EngineOutcome(
                engine=engine,
                case=case.name,
                status="failed",
                detail=f"{type(exc).__name__}: {exc}",
            )
        return EngineOutcome(
            engine=engine,
            case=case.name,
            status="ran",
            result=self._judge(plan, rows, engine),
        )

    def _judge(self, plan: ControlPlan, rows: list[dict[str, Any]], engine: str) -> ControlResult:
        names = [m.name for m in plan.metrics]
        if plan.scope.segment_by:
            segmented = [
                (
                    "|".join(str(row[c]) for c in plan.scope.segment_by),
                    {n: float(row[n]) for n in names if row.get(n) is not None},
                )
                for row in rows
            ]
            return judge_segments(plan, segmented, engine=engine)
        first = rows[0] if rows else {}
        return judge(
            plan,
            {n: float(first[n]) for n in names if first.get(n) is not None},
            engine=engine,
        )

    def compare(
        self, runners: dict[str, Runner], cases: tuple[Case, ...] = CASES
    ) -> list[Disagreement]:
        """Every case on every engine; the cases where answers differ."""
        disagreements: list[Disagreement] = []
        for case in cases:
            outcomes = {
                engine: self.run_case(case, engine, runner) for engine, runner in runners.items()
            }
            ran = {e: o for e, o in outcomes.items() if o.status == "ran"}
            broken = {e: o for e, o in outcomes.items() if o.status == "failed"}
            if broken:
                disagreements.append(
                    Disagreement(
                        case=case.name,
                        outcomes={e: f"error: {o.detail}" for e, o in broken.items()},
                    )
                )
                continue
            answers = {engine: outcome.comparable for engine, outcome in ran.items()}
            distinct = {_freeze(a) for a in answers.values()}
            if len(distinct) > 1:
                disagreements.append(Disagreement(case=case.name, outcomes=answers))
        return disagreements

    def summarise(self, runners: dict[str, Runner]) -> dict[str, Any]:
        """A report worth putting in front of somebody, pass or fail."""
        rows: list[dict[str, Any]] = []
        for case in CASES:
            entry: dict[str, Any] = {"case": case.name, "catches": case.catches}
            for engine, runner in runners.items():
                outcome = self.run_case(case, engine, runner)
                entry[engine] = outcome.result.verdict.value if outcome.result else outcome.status
            rows.append(entry)
        disagreements = self.compare(runners)
        return {
            "engines": sorted(runners),
            "cases": len(CASES),
            "disagreements": [d.render() for d in disagreements],
            "conforming": not disagreements,
            "rows": rows,
        }


def _freeze(value: Any) -> str:
    from prama.core.pjson import dumps

    return dumps(value, sort_keys=True)
