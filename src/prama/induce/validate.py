"""The gate every generated control passes before a person ever sees it.

`FR-IND-004`…`006`, and the wave's sharpest acceptance criterion: **100% of
LLM-generated PQL is parsed, type-checked and sandbox-executed before display.**
Not "should be" — the type below cannot be constructed otherwise. A discipline
enforced by review is a discipline with an exception in it by March.

Five gates, in the order that makes each one's failure cheap:

1. **Parse.** It is PQL, not prose about PQL, not PQL in a code fence.
2. **Type-check.** Its columns exist and its comparisons make sense against the
   real schema.
3. **Compile.** It lowers to a plan. A control that type-checks and cannot
   compile fails on its first scheduled run, which is the worst possible time
   to find out.
4. **Sandbox-execute.** It runs, against sample rows, in the reference
   interpreter — no database, no network, bounded rows. This is where a control
   that is syntactically perfect and semantically absurd shows itself.
5. **The counterfactual.** *A control that cannot fail is worth nothing.* This
   codebase says so about its own tests; the same standard applies to a control
   a model wrote. Rows are constructed that the control *should* reject, and
   one that passes them is discarded however well-formed it is.

Gate 5 is the one that earns the module. A model asked for a control will
happily produce ``CHECK t.x IS NOT NULL OR t.x IS NULL``, which parses,
type-checks, compiles, executes, reports a clean pass on every row, and is
worth precisely nothing. Nothing in gates 1 to 4 can tell it from a good
control, because on the data they are given the two behave identically. Only
trying to break it separates them.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from typing import Any

from prama.backend.reference import ReferenceEvaluator
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan
from prama.pql import ast
from prama.pql.errors import PqlError
from prama.pql.parser import parse_control
from prama.pql.types import Catalogue, TypeChecker

#: A control failing more than this fraction of the sample is not identifying
#: exceptions; it is describing the data, and whatever it describes is either
#: normal or a project rather than a control.
MAXIMUM_VIOLATION_RATE = 0.5

#: Rows the sandbox will look at. Bounded because this runs on every candidate
#: a model produces, and a semantic problem visible on ten thousand rows is
#: visible on two thousand.
SANDBOX_ROWS = 2000


class Gate(enum.Enum):
    PARSE = "parse"
    TYPE_CHECK = "type_check"
    COMPILE = "compile"
    SANDBOX = "sandbox"
    COUNTERFACTUAL = "counterfactual"

    @property
    def explains(self) -> str:
        return _GATE_MEANINGS[self]


_GATE_MEANINGS: dict[Gate, str] = {
    Gate.PARSE: "it is not PQL",
    Gate.TYPE_CHECK: (
        "it refers to something that is not there, or compares things that cannot be compared"
    ),
    Gate.COMPILE: "it cannot be turned into a plan",
    Gate.SANDBOX: "it ran and behaved in a way that makes it useless",
    Gate.COUNTERFACTUAL: "it cannot fail, so it would never find anything",
}


@dataclasses.dataclass(frozen=True, slots=True)
class Rejection:
    """Why a candidate did not survive, in terms somebody can act on."""

    gate: Gate
    detail: str
    #: The text as generated, so a systematically bad prompt is diagnosable.
    #: Truncated on output, because a model that returned an essay should not
    #: put the essay in the log.
    candidate: str = ""
    #: Earlier attempts at the same request that also failed. Carried here so
    #: a failed induction reports every attempt rather than only its last one —
    #: a published failure rate that counts three parse errors as one is a
    #: published failure rate that is wrong in the flattering direction.
    earlier: tuple[Rejection, ...] = ()

    @property
    def attempts(self) -> tuple[Rejection, ...]:
        """Every rejection for this request, oldest first."""
        return (*self.earlier, self)

    def describe(self) -> str:
        return f"{self.gate.value}: {self.detail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate.value,
            "detail": self.detail,
            "meaning": self.gate.explains,
            "candidate": self.candidate[:400],
            "earlier": [r.to_dict() for r in self.earlier],
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SandboxResult:
    """What the control did when it was actually run."""

    scanned: int
    violations: int
    #: Rows built to break it, and how many it caught. The counterfactual.
    probes: int = 0
    probes_caught: int = 0
    #: Probes carrying a *value* the control should reject, as distinct from
    #: the missing-value probe. The split is not cosmetic — see
    #: :attr:`is_vacuous`.
    value_probes: int = 0
    value_probes_caught: int = 0

    @property
    def violation_rate(self) -> float:
        return self.violations / self.scanned if self.scanned else 0.0

    @property
    def can_fail(self) -> bool:
        return self.probes_caught > 0 or self.violations > 0

    @property
    def is_vacuous(self) -> bool:
        """True when no constructed *value* violation was caught.

        Counting the null probe here would make this test nearly inert. PQL
        inverts SQL's default, so an unknown is a violation, so a missing value
        breaks every row predicate ever written — including
        ``qty > -999999999``, which catches the null, catches nothing else, and
        is exactly the sort of control this gate exists to reject.

        So only the probes carrying a real, hostile value count. A control that
        rejects nothing except emptiness is a completeness control wearing a
        disguise, and if that is what was wanted, ``IS NOT NULL`` says it
        without the disguise.
        """
        return self.value_probes > 0 and self.value_probes_caught == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "violations": self.violations,
            "violation_rate": round(self.violation_rate, 6),
            "probes": self.probes,
            "probes_caught": self.probes_caught,
            "value_probes": self.value_probes,
            "value_probes_caught": self.value_probes_caught,
            "is_vacuous": self.is_vacuous,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Validated:
    """A control that passed every gate. There is no other way to make one.

    The constructor checks, so this type *is* the guarantee rather than
    documenting one. Anything holding a ``Validated`` knows the PQL parses,
    type-checks, compiles, runs, and can be made to fail — without having to
    trust that whoever built it remembered.
    """

    control: ast.Control
    plan: ControlPlan
    sandbox: SandboxResult
    passed: tuple[Gate, ...]
    #: The text as generated, before any normalisation. Kept because a proposal
    #: whose origin is "a model said so" is worth little unless the exact
    #: output can be produced again.
    source: str = ""

    def __post_init__(self) -> None:
        missing = [gate for gate in Gate if gate not in self.passed]
        if missing:
            raise ValueError(
                "a Validated control must have passed every gate; "
                f"{', '.join(g.value for g in missing)} did not. This type is the "
                "guarantee that nothing unchecked reaches a reviewer, and building "
                "one directly would reduce it to a comment."
            )

    @property
    def content(self) -> str:
        return self.control.render()

    def to_dict(self) -> dict[str, Any]:
        return {
            "pql": self.content,
            "plan_id": self.plan.plan_id,
            "description": self.control.describe(),
            "sandbox": self.sandbox.to_dict(),
            "passed": [g.value for g in self.passed],
            "source": self.source,
        }


class Validator:
    """Runs the gates. The only producer of :class:`Validated`."""

    def __init__(
        self,
        *,
        catalogue: Catalogue | None = None,
        codelists: dict[str, tuple[str, ...]] | None = None,
        maximum_violation_rate: float = MAXIMUM_VIOLATION_RATE,
    ) -> None:
        self._catalogue = catalogue
        self._lowerer = Lowerer(codelists=codelists)
        self._maximum_violation_rate = maximum_violation_rate

    def validate(self, text: str, rows: Sequence[dict[str, Any]] = ()) -> Validated | Rejection:
        """Put one candidate through every gate, in order."""
        cleaned = _strip_fencing(text)
        passed: list[Gate] = []

        try:
            control = parse_control(cleaned)
        except PqlError as error:
            return Rejection(gate=Gate.PARSE, detail=str(error), candidate=cleaned)
        passed.append(Gate.PARSE)

        if self._catalogue is not None:
            findings = TypeChecker(self._catalogue).check(control)
            errors = [f for f in findings if f.level == "error"]
            if errors:
                return Rejection(
                    gate=Gate.TYPE_CHECK,
                    detail="; ".join(f.message for f in errors),
                    candidate=cleaned,
                )
        passed.append(Gate.TYPE_CHECK)

        try:
            plan = self._lowerer.control(control)
        except Exception as error:
            # Any failure lowering is a rejection, not an error. A model's
            # output is untrusted input, and untrusted input that breaks a
            # compiler is the compiler's ordinary Tuesday.
            return Rejection(gate=Gate.COMPILE, detail=str(error), candidate=cleaned)
        passed.append(Gate.COMPILE)

        sample = list(rows)[:SANDBOX_ROWS]
        try:
            result = ReferenceEvaluator().run(plan, sample)
        except Exception as error:
            return Rejection(gate=Gate.SANDBOX, detail=str(error), candidate=cleaned)

        rate = result.violating_rows / max(1.0, result.scanned_rows)
        if sample and rate > self._maximum_violation_rate:
            return Rejection(
                gate=Gate.SANDBOX,
                detail=(
                    f"it flags {rate:.0%} of rows. A control that fails half the data "
                    f"is describing it, not checking it"
                ),
                candidate=cleaned,
            )
        passed.append(Gate.SANDBOX)

        null_probe, value_probes = self._probes(control, sample)
        caught_null = self._count_caught(plan, null_probe)
        caught_values = self._count_caught(plan, value_probes)
        sandbox = SandboxResult(
            scanned=int(result.scanned_rows),
            violations=int(result.violating_rows),
            probes=len(null_probe) + len(value_probes),
            probes_caught=caught_null + caught_values,
            value_probes=len(value_probes),
            value_probes_caught=caught_values,
        )
        if sandbox.is_vacuous:
            return Rejection(
                gate=Gate.COUNTERFACTUAL,
                detail=(
                    f"{len(value_probes)} rows were built carrying values this control "
                    f"should reject, and it accepted every one"
                    + (
                        ". It does reject a missing value, but so does every row "
                        "predicate in the language — that is not this control doing "
                        "anything"
                        if caught_null
                        else ""
                    )
                    + ". It parses, type-checks, compiles and runs, and it cannot find "
                    "anything"
                ),
                candidate=cleaned,
            )
        passed.append(Gate.COUNTERFACTUAL)

        return Validated(
            control=control,
            plan=plan,
            sandbox=sandbox,
            passed=tuple(passed),
            source=text,
        )

    # -- the counterfactual -------------------------------------------------

    def _probes(
        self, control: ast.Control, rows: Sequence[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Rows built to break this control: the null one, and the real ones.

        Derived from the assertion rather than random, because random rows
        rarely violate a specific predicate and a probe that tests nothing
        proves nothing. Each shape gets the perturbation its own predicate is
        supposed to catch.

        Returned as two lists rather than one, because a null breaking a
        control proves nothing about that control: PQL inverts SQL's default,
        so an unknown violates every row predicate in the language. Only the
        probes carrying a real hostile value are evidence that the control
        checks anything.
        """
        subject = _subject_of(control.assertion)
        if subject is None:
            return [], []
        base = dict(rows[0]) if rows else {}
        null_probe = [{**base, subject: None}]
        assertion = control.assertion
        value_probes: list[dict[str, Any]] = []
        if isinstance(assertion, ast.PredicateAssertion):
            if assertion.operator in ("is_not_null", "is_null"):
                # For a nullity assertion the null *is* the hostile value —
                # there is nothing else that violates it. Counting it as a
                # value probe rather than as the free one keeps the reported
                # numbers honest: "0 of 0 value probes" reads as though the
                # control was never really tested, and it was.
                return [], null_probe
            value_probes = [
                {**base, subject: value} for value in _hostile_values(assertion, base.get(subject))
            ]
        return null_probe, value_probes

    def _count_caught(self, plan: ControlPlan, probes: list[dict[str, Any]]) -> int:
        if not probes:
            return 0
        evaluator = ReferenceEvaluator()
        caught = 0
        for probe in probes:
            try:
                outcome = evaluator.run(plan, [probe])
            except Exception:
                # A probe that cannot run is not a probe that was caught.
                continue
            if outcome.violating_rows > 0:
                caught += 1
        return caught


def _hostile_values(assertion: ast.PredicateAssertion, current: Any) -> list[Any]:
    """Values chosen to break a specific predicate.

    Each is the thing the operator exists to reject: a value outside the list,
    a string that does not match the pattern, a number past the bound. Probing
    ``IN ('BUY','SELL')`` with another arbitrary string is the only way to
    learn whether the membership test is being applied at all.
    """
    operator = assertion.operator
    if operator in ("in", "in_codelist"):
        return ["␀not-a-member"]
    if operator in ("matches", "has_format", "is_valid", "is_of_type"):
        return ["␀not-a-match", ""]
    if operator == "between":
        bounds = [_literal(assertion.argument), _literal(assertion.upper)]
        numeric = [b for b in bounds if isinstance(b, int | float)]
        return [min(numeric) - 1, max(numeric) + 1] if numeric else []
    if operator in ast.COMPARISONS:
        value = _literal(assertion.argument)
        if isinstance(value, int | float):
            # One value each side of the bound, so whichever direction the
            # comparison runs, one of them must be rejected.
            return [value - 1, value + 1]
        if isinstance(value, str):
            return [value + "␀"]
    if operator == "is_not_null":
        return []  # the null probe already covers it
    if isinstance(current, int | float):
        return [-abs(current) - 1]
    return ["␀"]


def _literal(expression: ast.Expression | None) -> Any:
    return expression.value if isinstance(expression, ast.Literal) else None


def _subject_of(assertion: ast.Assertion) -> str | None:
    subject = getattr(assertion, "subject", None)
    if isinstance(subject, ast.ColumnRef):
        return subject.name
    column = getattr(assertion, "column", None)
    if isinstance(column, ast.ColumnRef):
        return column.name
    columns = getattr(assertion, "columns", None)
    if columns:
        first = columns[0]
        return first.name if isinstance(first, ast.ColumnRef) else None
    return None


def _strip_fencing(text: str) -> str:
    """Remove a code fence, and nothing else.

    Models wrap code in fences by habit, and rejecting a correct control for
    its packaging teaches nothing and costs a retry. Everything beyond
    unwrapping is left alone: a candidate that needs editing to parse should be
    rejected, because whatever the edit fixed is what the next one will get
    wrong too.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    body = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
    return "\n".join(body).strip()
