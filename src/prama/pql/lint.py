"""Finding the controls that are not doing anything.

A control estate rots quietly. Someone adds a null check beside a range check
that already catches nulls; someone sets a rate threshold of 100%; a suite is
copied between datasets and half of it now duplicates the other half. None of
this breaks. The suite goes green, the estate grows, and confidence in it falls
until people stop reading the alerts — which is the actual failure, and it
arrives years after the cause.

So the linter looks for controls that cannot fire, controls that always fire,
and controls that say nothing the estate does not already say. Every finding
names the other control involved where there is one, because "this is redundant"
is not actionable and "this is already covered by the unique key on line 12" is.

Nothing here guesses. Where subsumption cannot be decided by the rules below,
the linter says nothing rather than raising a doubt somebody has to disprove.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.ir.lower import Lowerer
from prama.pql import ast

#: Predicates that already fail on a null, because an unknown counts as a
#: violation. This is why a separate IS NOT NULL beside them adds nothing — a
#: consequence of the language's central decision, and not obvious until stated.
NULL_SENSITIVE: frozenset[str] = frozenset(
    {"in", "between", "matches", "is_valid", "has_format", "has_length_between", "in_codelist"}
    | set(ast.COMPARISONS)
)


@dataclasses.dataclass(frozen=True, slots=True)
class LintFinding:
    """One thing worth changing, and why."""

    rule: str
    message: str
    remedy: str
    control: str
    #: The other control involved, for redundancy and subsumption.
    related: str = ""
    severity: str = "warning"
    position: Any = None

    def render(self) -> str:
        lines = [f"[{self.severity}] {self.rule}: {self.message}"]
        if self.related:
            lines.append(f"  related: {self.related}")
        lines.append(f"  → {self.remedy}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "remedy": self.remedy,
            "control": self.control,
            "related": self.related,
            "position": self.position.to_dict() if self.position else None,
        }


class Linter:
    """Checks a control, and a suite of controls against each other."""

    def check(self, control: ast.Control) -> list[LintFinding]:
        findings: list[LintFinding] = []
        findings.extend(self._never_fires(control))
        findings.extend(self._always_fires(control))
        findings.extend(self._missing_justification(control))
        return findings

    def check_all(self, controls: list[ast.Control]) -> list[LintFinding]:
        """Every control on its own, then all of them against each other."""
        findings = [f for control in controls for f in self.check(control)]
        findings.extend(self._duplicates(controls))
        findings.extend(self._subsumed(controls))
        return findings

    # -- controls that cannot fire ----------------------------------------

    def _never_fires(self, control: ast.Control) -> list[LintFinding]:
        threshold = control.threshold
        if threshold.unit in ("rate", "percent") and threshold.value >= 1.0:
            return [
                LintFinding(
                    rule="never-fires",
                    message=(
                        f"a threshold of {threshold.value * 100:g}% cannot be exceeded, so "
                        f"this control can never fail"
                    ),
                    remedy=(
                        "Set a rate the data could realistically breach, or remove the "
                        "control. A control that cannot fail is worse than none: it "
                        "appears on the coverage report and covers nothing."
                    ),
                    control=control.render().splitlines()[0],
                    severity="error",
                    position=control.position,
                )
            ]
        assertion = control.assertion
        if isinstance(assertion, ast.RowCountAssertion):
            if assertion.minimum is None and assertion.maximum is None:
                return [self._vacuous(control, "a row count with no bounds asserts nothing")]
            if assertion.minimum == 0 and assertion.maximum is None:
                return [self._vacuous(control, "every dataset has at least zero rows")]
        return []

    def _always_fires(self, control: ast.Control) -> list[LintFinding]:
        assertion = control.assertion
        if isinstance(assertion, ast.PredicateAssertion) and assertion.operator == "between":
            lower, upper = assertion.argument, assertion.upper
            if (
                isinstance(lower, ast.Literal)
                and isinstance(upper, ast.Literal)
                and isinstance(lower.value, int | float)
                and isinstance(upper.value, int | float)
                and lower.value > upper.value
            ):
                return [
                    LintFinding(
                        rule="always-fires",
                        message=(
                            f"BETWEEN {lower.render()} AND {upper.render()} is empty, so "
                            f"every row violates it"
                        ),
                        remedy="The bounds are the wrong way round.",
                        control=control.render().splitlines()[0],
                        severity="error",
                        position=assertion.position,
                    )
                ]
        if (
            isinstance(assertion, ast.RowCountAssertion)
            and assertion.minimum is not None
            and assertion.maximum is not None
            and assertion.minimum > assertion.maximum
        ):
            return [
                LintFinding(
                    rule="always-fires",
                    message="the row count range is empty, so this can never pass",
                    remedy="The bounds are the wrong way round.",
                    control=control.render().splitlines()[0],
                    severity="error",
                    position=assertion.position,
                )
            ]
        return []

    def _missing_justification(self, control: ast.Control) -> list[LintFinding]:
        if control.because:
            return []
        return [
            LintFinding(
                rule="no-justification",
                message="this control does not say why it exists",
                remedy=(
                    "Add BECAUSE '…'. When it fires at three in the morning, the sentence "
                    "explaining what the business declared is the most useful thing on the "
                    "screen — and a control nobody can justify is one nobody will maintain."
                ),
                control=control.render().splitlines()[0],
                severity="info",
                position=control.position,
            )
        ]

    # -- controls against each other --------------------------------------

    def _duplicates(self, controls: list[ast.Control]) -> list[LintFinding]:
        """Exact duplicates, found by plan identity rather than by text.

        Content addressing makes this exact and free: two controls that compute
        the same thing have the same plan id however differently they are
        written, so a copied suite with reordered clauses is still caught.
        """
        seen: dict[str, ast.Control] = {}
        findings: list[LintFinding] = []
        lowerer = Lowerer()
        for control in controls:
            try:
                plan_id = lowerer.control(control).plan_id
            except Exception:  # an assertion with no plan yet cannot be compared
                continue
            if plan_id in seen:
                findings.append(
                    LintFinding(
                        rule="duplicate",
                        message="this control computes exactly what another already computes",
                        remedy=(
                            "Remove one. Both will read the same data, produce the same "
                            "finding and page the same person twice."
                        ),
                        control=control.render().splitlines()[0],
                        related=seen[plan_id].render().splitlines()[0],
                        position=control.position,
                    )
                )
            else:
                seen[plan_id] = control
        return findings

    def _subsumed(self, controls: list[ast.Control]) -> list[LintFinding]:
        findings: list[LintFinding] = []
        for candidate in controls:
            for other in controls:
                if candidate is other:
                    continue
                reason = self._implies(other, candidate)
                if reason:
                    findings.append(
                        LintFinding(
                            rule="subsumed",
                            message=f"this control adds nothing: {reason}",
                            remedy=(
                                "Remove it, or make it say something the other does not. "
                                "Two controls firing on the same rows produce two alerts "
                                "about one problem."
                            ),
                            control=candidate.render().splitlines()[0],
                            related=other.render().splitlines()[0],
                            position=candidate.position,
                        )
                    )
                    break
        return findings

    def _implies(self, stronger: ast.Control, weaker: ast.Control) -> str:
        """Whether *stronger* passing guarantees *weaker* passes.

        Deliberately a short list of decidable cases rather than a solver. A
        linter that reported a maybe would cost more attention than it saved.
        """
        if stronger.target != weaker.target:
            return ""
        if stronger.where != weaker.where or stronger.segmentation != weaker.segmentation:
            # Different scopes are not comparable without reasoning about the
            # filters, which is where a solver would be needed and a wrong
            # answer would be expensive.
            return ""
        if not (
            isinstance(stronger.assertion, ast.PredicateAssertion)
            and isinstance(weaker.assertion, ast.PredicateAssertion)
        ):
            return ""
        first, second = stronger.assertion, weaker.assertion
        if first.subject != second.subject:
            return ""
        if not (stronger.threshold.is_strict and weaker.threshold.is_strict):
            # A tolerance changes what "passing" means, and a stricter
            # predicate under a looser tolerance implies nothing.
            return ""
        if (
            second.operator == "is_not_null"
            and first.operator in NULL_SENSITIVE
            and weaker.unknown_policy is ast.UnknownPolicy.VIOLATION
        ):
            return (
                f"{stronger.assertion.render()} already fails on a null, because an "
                f"unknown counts as a violation"
            )
        if first.operator == "in" and second.operator == "in":
            narrow = _literal_set(first.argument)
            wide = _literal_set(second.argument)
            if narrow and wide and narrow < wide and second.argument is not None:
                return f"the permitted values are a subset of {second.argument.render()}"
        return ""

    @staticmethod
    def _vacuous(control: ast.Control, message: str) -> LintFinding:
        return LintFinding(
            rule="never-fires",
            message=message,
            remedy="State a bound the data could breach, or remove the control.",
            control=control.render().splitlines()[0],
            severity="error",
            position=control.position,
        )


def _literal_set(node: ast.Expression | None) -> frozenset[Any]:
    if not isinstance(node, ast.ListExpression):
        return frozenset()
    if not all(isinstance(item, ast.Literal) for item in node.items):
        return frozenset()
    return frozenset(item.value for item in node.items if isinstance(item, ast.Literal))


def lint(controls: list[ast.Control]) -> list[LintFinding]:
    return Linter().check_all(controls)
