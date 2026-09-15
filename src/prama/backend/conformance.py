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

#: The name reserved for the reference interpreter. It is not a SQL engine and
#: is never compiled for; it evaluates the plan directly, which is what makes
#: it an independent check rather than a fourth opinion from the same compiler.
REFERENCE = "reference"


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

    def __init__(self, table: str = "corpus", *, rows: list[dict[str, Any]] | None = None) -> None:
        self._table = table
        self._plans: dict[str, ControlPlan] = {}
        #: The corpus as data, so the reference interpreter can be run beside
        #: the engines rather than instead of them.
        self._rows = rows

    def plan_for(self, case: Case) -> ControlPlan:
        if case.name not in self._plans:
            self._plans[case.name] = Lowerer().control(parse_control(case.pql))
        return self._plans[case.name]

    def run_case(self, case: Case, engine: str, runner: Runner) -> EngineOutcome:
        plan = self.plan_for(case)
        if engine == REFERENCE:
            return self._run_reference(plan, case)
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

    def _run_reference(self, plan: ControlPlan, case: Case) -> EngineOutcome:
        """Evaluate the plan directly, sharing nothing with the compiler.

        Three SQL backends agreeing proves agreement about the compiler they
        share. This is the independent voice: if it differs from all three, the
        interpreter is wrong; if all three differ from it, the compiler is.
        """
        from prama.backend.reference import ReferenceEvaluator

        if self._rows is None:
            return EngineOutcome(
                engine=REFERENCE,
                case=case.name,
                status="failed",
                detail="the reference interpreter needs the corpus rows",
            )
        try:
            result = ReferenceEvaluator().run(plan, self._rows)
        except PqlUnsupportedError as exc:
            # The same rule the compiled path already follows fifteen lines
            # above: a refusal is a conforming outcome, it is the promise being
            # kept. The interpreter refuses an approximation because it cannot
            # reproduce an engine's algorithm or its error bound.
            return EngineOutcome(
                engine=REFERENCE, case=case.name, status="refused", detail=str(exc.args[0])
            )
        except Exception as exc:
            return EngineOutcome(
                engine=REFERENCE,
                case=case.name,
                status="failed",
                detail=f"{type(exc).__name__}: {exc}",
            )
        return EngineOutcome(engine=REFERENCE, case=case.name, status="ran", result=result)

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
            plan = self.plan_for(case)
            if plan.is_two_stage:
                disagreements.extend(self._compare_two_stage(case, ran))
                continue
            if len(ran) < 2:
                # A set of one answer is trivially unanimous, and `len(distinct)
                # > 1` can never fire — so a case only one engine could run was
                # counted as agreement. `summarise` printed `cases_compared: 0`
                # directly beside `conforming: True` and the verdict did not
                # consult it. QA round 4, `BE-135`.
                #
                # This is the harness the whole release gate rests on. Absence of
                # evidence has to be reportable here or nowhere.
                disagreements.append(
                    Disagreement(
                        case=case.name,
                        outcomes={
                            **{e: f"{o.status}: {o.detail}" for e, o in outcomes.items()},
                            "comparison": (
                                f"{len(ran)} engine(s) answered. Agreement needs two. "
                                "A refusal is a conforming outcome for one engine and "
                                "is not an answer to compare against."
                            ),
                        },
                    )
                )
                continue
            distinct = {_freeze(a) for a in answers.values()}
            if len(distinct) > 1:
                disagreements.append(Disagreement(case=case.name, outcomes=answers))
        return disagreements

    @staticmethod
    def _compare_two_stage(case: Case, ran: dict[str, EngineOutcome]) -> list[Disagreement]:
        """Agreement for a control an engine can only half-answer.

        Requiring identical counts here would be wrong, and quietly excusing the
        case would be worse. A two-stage control's SQL predicate is a *screen*:
        a necessary condition every valid value satisfies. So the engines are
        required to differ in exactly one direction —

        * an engine may find **fewer** violations than the exact check, because
          a value with the right shape and a wrong check digit passes the
          screen. That is the whole reason the second stage exists;
        * an engine may never find **more**, because that would mean the screen
          rejected a value the standard accepts, and the control would be
          reporting a violation on good reference data.

        That much was true and was all this checked, and it left the gate open
        at the bottom. "Fewer" includes **none**: a screen that rejects nothing
        is excused unconditionally, so a neutered predicate and a working one
        produce the same green report. Neutering the ``FILTER (WHERE …)``
        clause of every two-stage plan left all 119 backend tests passing while
        DuckDB reported PASS on data the reference reports three violations for
        (finding T4).

        So the case now declares what the screen alone must find
        (:attr:`Case.screen_violations`) and that number is required exactly.
        It is the one figure a screen cannot fake: too low and it is not
        screening, too high and it rejects values the standard accepts.
        """
        reference = ran.get("reference")
        if reference is None or reference.result is None:
            # Returning [] here excused the two-stage comparison — which is the
            # product's actual thesis, a screen plus an exact check — from ever
            # running, silently, whenever the interpreter did not answer. The
            # one comparison most worth making was the one that could be skipped
            # without a word. QA round 4, `BE-139`.
            return [
                Disagreement(
                    case=case.name,
                    outcomes={
                        "reference": (
                            "did not answer, so the screen could not be checked against "
                            "the exact result. A two-stage case with no reference answer "
                            "is uncompared, not conforming."
                        )
                    },
                )
            ]
        exact = reference.result.violating_rows
        found: list[Disagreement] = []

        if case.screen_violations is None:
            found.append(
                Disagreement(
                    case=case.name,
                    outcomes={
                        "corpus": (
                            "this is a two-stage control and declares no screen_violations, "
                            "so an engine finding nothing would be excused. Declare what the "
                            "SQL screen alone must find."
                        )
                    },
                )
            )
            return found

        expected = case.screen_violations
        wrong = {
            engine: (
                f"{outcome.result.violating_rows:g} from the screen, expected {expected:g}"
                if outcome.result is not None
                else outcome.comparable
            )
            for engine, outcome in ran.items()
            if engine != "reference"
            and (outcome.result is None or outcome.result.violating_rows != expected)
        }
        if wrong:
            found.append(
                Disagreement(
                    case=case.name,
                    outcomes={
                        **wrong,
                        "reference": (
                            f"{exact:g} violations exactly. The screen must find "
                            f"{expected:g}: fewer means it is not screening, more means it "
                            f"rejects a value the standard accepts"
                        ),
                    },
                )
            )
        if expected > exact:
            found.append(
                Disagreement(
                    case=case.name,
                    outcomes={
                        "corpus": (
                            f"the declared screen count {expected:g} exceeds the exact check's "
                            f"{exact:g}; a screen is a necessary condition and cannot reject "
                            "more than the standard does"
                        )
                    },
                )
            )
        return found

    def summarise(self, runners: dict[str, Runner]) -> dict[str, Any]:
        """A report worth putting in front of somebody, pass or fail.

        ``engines`` is who was *offered* the corpus; ``engines_that_ran`` is who
        actually executed a case, and ``cases_compared`` is how many cases at
        least two of them answered. The difference is the whole value of the
        report — finding T7. An engine that refuses every control is filtered
        out before comparison, so a compiler change that made SQLite refuse
        everything left the gate green while it compared one SQL engine against
        the interpreter, and the tests asserted `len(engines) >= 2` against a
        dict built from three hard-coded keys and `len(CASES) == len(CASES)`.
        """
        rows: list[dict[str, Any]] = []
        ran_at_least_once: set[str] = set()
        compared = 0
        for case in CASES:
            entry: dict[str, Any] = {"case": case.name, "catches": case.catches}
            answered = 0
            for engine, runner in runners.items():
                outcome = self.run_case(case, engine, runner)
                entry[engine] = outcome.result.verdict.value if outcome.result else outcome.status
                if outcome.status == "ran":
                    ran_at_least_once.add(engine)
                    answered += 1
            if answered >= 2:
                compared += 1
            rows.append(entry)
        disagreements = self.compare(runners)
        return {
            "engines": sorted(runners),
            "engines_that_ran": sorted(ran_at_least_once),
            "cases": len(CASES),
            "cases_compared": compared,
            "disagreements": [d.render() for d in disagreements],
            "conforming": not disagreements,
            "rows": rows,
        }


def _freeze(value: Any) -> str:
    from prama.core.pjson import dumps

    return dumps(value, sort_keys=True)
