"""What is protected, what is not, and which gap to close first.

`W6.15`, and the measurement behind the wave's acceptance criterion: ≥ 80% of
columns and ≥ 95% of declared CDEs under a reviewed control after a week.

**Coverage counted by column is a number that flatters.** Eighty percent of
columns covered says nothing if the uncovered twenty percent are the CDEs, and
a single ``IS NOT NULL`` on a column makes it "covered" while its format,
its domain and its consistency go unchecked. Both failures push the number in
the same direction, and it is the direction that makes a report look finished.

So coverage is measured per **(attribute, dimension)** pair. A counterparty LEI
with a completeness control and no validity control is 1 of 2 covered, not 1 of
1, and the report says which half is missing — which is a sentence somebody can
act on, where "83% covered" is not.

**Only the dimensions that apply are counted.** Every attribute needs
completeness. Only one with a semantic type or a value domain can have a
validity control; only one in a relationship can have a consistency control.
Counting dimensions an attribute cannot have would make a well-covered estate
look sparse and would hide the real gaps in the noise — the same failure as
counting them all, from the other side.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from typing import Any

from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.pql import ast
from prama.semantic.values import Optionality

#: The dimensions coverage is measured over. Deliberately not all of
#: ``ast.Dimension``: timeliness and uniqueness are properties of a *dataset*
#: rather than of an attribute, and counting them per column would make every
#: column in a well-controlled table look 2/8 covered.
ATTRIBUTE_DIMENSIONS: tuple[ast.Dimension, ...] = (
    ast.Dimension.COMPLETENESS,
    ast.Dimension.VALIDITY,
    ast.Dimension.CONSISTENCY,
    ast.Dimension.ACCURACY,
)

DATASET_DIMENSIONS: tuple[ast.Dimension, ...] = (
    ast.Dimension.UNIQUENESS,
    ast.Dimension.TIMELINESS,
)

#: Risk weights. A declared CDE outweighs a tier, and a regulatory obligation
#: outweighs both — an uncontrolled CDE feeding a return is an attestation
#: problem before it is a data problem.
CDE_WEIGHT = 0.5
OBLIGATION_WEIGHT = 0.5
COMPLETENESS_WEIGHT = 0.3
MAXIMUM_RISK = 1.0 + CDE_WEIGHT + OBLIGATION_WEIGHT + COMPLETENESS_WEIGHT


@dataclasses.dataclass(frozen=True, slots=True)
class Gap:
    """One thing that is not checked, and what it would take to check it."""

    dataset: str
    attribute: str
    dimension: ast.Dimension
    #: 1 (regulatory) to 4 (informational), inherited from the dataset unless
    #: the attribute is a CDE.
    criticality: int
    is_cde: bool
    obligations: tuple[str, ...] = ()
    #: What would close it, in a sentence. A gap report that names the problem
    #: and not the fix is a list somebody reads once.
    remedy: str = ""

    @property
    def risk(self) -> float:
        """How much this gap matters, on a scale the report can sort by.

        Additive and normalised rather than clamped. An earlier version took
        ``min(1.0, ...)`` at each step, and on a Tier 1 dataset *every* gap
        scored exactly 1.00 — so "sort by risk" degenerated into alphabetical
        order, which is the one thing a ranked list must not silently become.
        The components have to stay separable all the way to the end for the
        ordering to mean anything.
        """
        tier = max(1, min(4, self.criticality))
        score = (5 - tier) / 4
        if self.is_cde:
            score += CDE_WEIGHT
        if self.obligations:
            # The question asked about an uncontrolled CDE feeding a return is
            # not "how bad is the data?" but "what did you attest to?".
            score += OBLIGATION_WEIGHT
        if self.dimension is ast.Dimension.COMPLETENESS:
            # The gap that hides the others: a column that is half empty makes
            # every other control on it a statement about the half that is
            # there.
            score += COMPLETENESS_WEIGHT
        return score / MAXIMUM_RISK

    def describe(self) -> str:
        what = f"{self.dataset}.{self.attribute}"
        marker = " (a declared CDE" + (
            f", feeding {', '.join(self.obligations)})" if self.obligations else ")"
        )
        return (
            f"{what}{marker if self.is_cde else ''} has no "
            f"{self.dimension.value} control. {self.remedy}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "attribute": self.attribute,
            "dimension": self.dimension.value,
            "criticality": self.criticality,
            "is_cde": self.is_cde,
            "obligations": list(self.obligations),
            "risk": round(self.risk, 4),
            "remedy": self.remedy,
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    """What a dataset's controls actually protect."""

    dataset: str
    #: (attribute, dimension) pairs that apply and are covered.
    covered: int
    #: (attribute, dimension) pairs that apply at all.
    applicable: int
    cde_covered: int
    cde_applicable: int
    gaps: tuple[Gap, ...] = ()
    #: Attributes with at least one control of any kind. The flattering
    #: number, kept beside the honest one so the difference is visible rather
    #: than a choice somebody made about which to report.
    attributes_touched: int = 0
    attributes: int = 0

    @property
    def fraction(self) -> float:
        return self.covered / self.applicable if self.applicable else 1.0

    @property
    def cde_fraction(self) -> float:
        return self.cde_covered / self.cde_applicable if self.cde_applicable else 1.0

    @property
    def touched_fraction(self) -> float:
        """The number a naive coverage report would print."""
        return self.attributes_touched / self.attributes if self.attributes else 1.0

    @property
    def meets_target(self) -> bool:
        """The wave's acceptance criterion, measured honestly."""
        return self.fraction >= 0.8 and self.cde_fraction >= 0.95

    def worst(self, limit: int = 10) -> tuple[Gap, ...]:
        return tuple(sorted(self.gaps, key=lambda g: (-g.risk, g.attribute))[:limit])

    def describe(self) -> str:
        head = (
            f"{self.dataset}: {self.covered} of {self.applicable} applicable "
            f"attribute-dimension pairs are under a control ({self.fraction:.0%})"
        )
        if self.cde_applicable:
            head += (
                f"; {self.cde_covered} of {self.cde_applicable} for declared CDEs "
                f"({self.cde_fraction:.0%})"
            )
        if self.attributes and self.touched_fraction > self.fraction + 0.1:
            head += (
                f". {self.touched_fraction:.0%} of attributes have *some* control, "
                f"which is the number that flatters"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "covered": self.covered,
            "applicable": self.applicable,
            "fraction": round(self.fraction, 4),
            "cde_covered": self.cde_covered,
            "cde_applicable": self.cde_applicable,
            "cde_fraction": round(self.cde_fraction, 4),
            "attributes_touched": self.attributes_touched,
            "attributes": self.attributes,
            "touched_fraction": round(self.touched_fraction, 4),
            "meets_target": self.meets_target,
            "gaps": [g.to_dict() for g in self.gaps],
            "summary": self.describe(),
        }


class CoverageAnalyser:
    """Measures coverage, and ranks what is missing by what it would cost."""

    def analyse(
        self,
        declaration: DatasetDeclaration,
        controls: Sequence[ast.Control],
    ) -> Coverage:
        protected = self._protected(controls)
        gaps: list[Gap] = []
        covered = applicable = 0
        cde_covered = cde_applicable = 0
        touched = 0

        for attribute in declaration.attributes:
            dimensions = self._applicable(attribute)
            if attribute.name in protected:
                touched += 1
            for dimension in dimensions:
                applicable += 1
                if attribute.is_cde:
                    cde_applicable += 1
                if self._is_covered(attribute, dimension, protected):
                    covered += 1
                    if attribute.is_cde:
                        cde_covered += 1
                    continue
                gaps.append(
                    Gap(
                        dataset=declaration.name,
                        attribute=attribute.name,
                        dimension=dimension,
                        criticality=int(declaration.criticality),
                        is_cde=attribute.is_cde,
                        obligations=attribute.obligations,
                        remedy=self._remedy(attribute, dimension),
                    )
                )

        return Coverage(
            dataset=declaration.name,
            covered=covered,
            applicable=applicable,
            cde_covered=cde_covered,
            cde_applicable=cde_applicable,
            gaps=tuple(gaps),
            attributes_touched=touched,
            attributes=len(declaration.attributes),
        )

    def analyse_estate(
        self,
        declarations: Iterable[DatasetDeclaration],
        controls_by_dataset: dict[str, Sequence[ast.Control]],
    ) -> tuple[Coverage, ...]:
        """Every dataset, worst-covered first.

        Ordered by how much is unprotected rather than by name, because the
        purpose of the list is to be worked from the top.
        """
        results = [
            self.analyse(declaration, controls_by_dataset.get(declaration.name, ()))
            for declaration in declarations
        ]
        results.sort(key=lambda c: (c.cde_fraction, c.fraction, c.dataset))
        return tuple(results)

    @staticmethod
    def _is_covered(
        attribute: AttributeDeclaration,
        dimension: ast.Dimension,
        protected: dict[str, set[ast.Dimension]],
    ) -> bool:
        """Whether something checks this attribute on this dimension.

        Usually a control on the attribute itself. The exception follows a
        declaration: an amount declared to be denominated in another column is
        made summable by the control on *that* column, so a currency-code check
        on ``exposure_ccy`` is what answers ``exposure_amount``'s consistency
        question. Requiring the control to sit on the amount would report a
        correctly controlled pair as a gap, and the remedy would be to write a
        second control that checks the same thing.
        """
        if dimension in protected.get(attribute.name, set()):
            return True
        if dimension is ast.Dimension.CONSISTENCY and attribute.currency_attribute:
            return dimension in protected.get(attribute.currency_attribute, set())
        return False

    # -- what applies, and what is protected -------------------------------

    @staticmethod
    def _applicable(attribute: AttributeDeclaration) -> tuple[ast.Dimension, ...]:
        """The dimensions this attribute could have a control for.

        Counting dimensions an attribute cannot have would make a well-covered
        estate look sparse and bury the real gaps — the same failure as
        counting only columns, approached from the other side.
        """
        dimensions = []
        if attribute.optionality is not Optionality.OPTIONAL:
            # A column declared optional has had its completeness question
            # answered — by the declaration, which said no control is wanted.
            # Counting it as a gap would mean an estate could only reach 100%
            # by declaring every column mandatory, which is a worse outcome
            # than an imperfect number: it pushes people into false
            # declarations to move a metric.
            #
            # The default *is* optional, so a column nobody has considered
            # looks answered here. That is chased by the maturity score
            # (`prama.semantic.maturity`), which measures how much has been
            # declared, and this measures how much of what was declared is
            # enforced. Conflating the two would hide both.
            dimensions.append(ast.Dimension.COMPLETENESS)
        if attribute.generates_a_domain_control:
            dimensions.append(ast.Dimension.VALIDITY)
        if attribute.currency_attribute or attribute.is_monetary:
            # An amount is only meaningful alongside its currency, so the two
            # have to agree — a consistency question rather than a validity
            # one.
            dimensions.append(ast.Dimension.CONSISTENCY)
        if attribute.is_cde:
            # A CDE is worth checking against something outside the row: a
            # master, a prior period, a reported total. Nothing else earns an
            # accuracy control, because for anything else there is nothing to
            # compare against that is not equally unverified.
            dimensions.append(ast.Dimension.ACCURACY)
        return tuple(dimensions)

    @staticmethod
    def _protected(controls: Sequence[ast.Control]) -> dict[str, set[ast.Dimension]]:
        """Which (attribute, dimension) pairs a suite actually covers.

        A control with no declared dimension covers nothing here, and that is
        deliberate rather than strict: a suite of controls nobody has
        classified cannot be measured, and quietly assuming a dimension for
        them would produce a coverage number that is wrong and confident.
        """
        protected: dict[str, set[ast.Dimension]] = {}
        for control in controls:
            dimensions = set(control.dimensions)
            if ast.Dimension.INTEGRITY in dimensions:
                # A referential control checks a value against another dataset,
                # which is exactly what the accuracy expectation asks for:
                # something outside the row to compare against. Treating them
                # as different would report a CDE with a master-data check as
                # having no accuracy control, which is not true in any sense a
                # reviewer would recognise.
                dimensions.add(ast.Dimension.ACCURACY)
            for name in _subjects(control):
                protected.setdefault(name, set()).update(dimensions)
        return protected

    @staticmethod
    def _remedy(attribute: AttributeDeclaration, dimension: ast.Dimension) -> str:
        if dimension is ast.Dimension.COMPLETENESS:
            return (
                "Declare whether it is mandatory — Γ writes the control. Until then a "
                "half-empty column makes every other control on it a statement about "
                "the half that is there."
            )
        if dimension is ast.Dimension.VALIDITY:
            if attribute.semantic_type:
                return (
                    f"It is declared to be a {attribute.semantic_type} and nothing "
                    f"checks that it is one."
                )
            return "Declare its value domain — a code list, a range or a pattern."
        if dimension is ast.Dimension.CONSISTENCY:
            return (
                f"Nothing checks {attribute.name} against "
                f"{attribute.currency_attribute or 'the column it depends on'}; an "
                f"aggregate over it is not currently meaningful."
            )
        return (
            "Nothing compares it with a source outside the row. Declare a relationship "
            "— a master to reference, or a total to reconcile against."
        )


def _subjects(control: ast.Control) -> tuple[str, ...]:
    """Which attributes a control is about."""
    assertion = control.assertion
    subject = getattr(assertion, "subject", None)
    if isinstance(subject, ast.ColumnRef):
        return (subject.name,)
    column = getattr(assertion, "column", None)
    if isinstance(column, ast.ColumnRef):
        return (column.name,)
    columns = getattr(assertion, "columns", None)
    if columns:
        return tuple(c.name for c in columns if isinstance(c, ast.ColumnRef))
    determinant = getattr(assertion, "determinant", ())
    dependent = getattr(assertion, "dependent", ())
    return tuple(c.name for c in (*determinant, *dependent) if isinstance(c, ast.ColumnRef))
