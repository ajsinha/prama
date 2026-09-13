"""One reconciliation run, reproducible from what it recorded.

`FR-REC-001`…`005`. The engine is short because the work is in the three
modules it composes — normalisation, matching, classification — and keeping it
short is the point: what a run *is* should be readable in one screen, because
the first question about any break is which of those three produced it.

**A run is reproducible or it is not evidence.** Given the same two datasets
and the same business date, it must produce the same breaks — which means every
input that could move (an exchange rate, a code mapping) is resolved as of the
date being reconciled and recorded on the result. Without that, a break
somebody investigated and cleared reappears next week with a different number
and nobody can say whether the data changed or the rate did.

**The match rate is checked before the breaks are.** A reconciliation matching
sixty percent of its rows produces a break population that is mostly artefacts
of the mapping gap, and working it is a week spent on the wrong thing. The run
still completes and still reports, and it says at the top that the number to
look at is the match rate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from prama.recon.classify import Break, BreakKind, Classifier, Population, attribute_to_fx
from prama.recon.match import Matcher, MatchKey, MatchReport, ToleranceMatcher
from prama.recon.normalise import AmountNormaliser, AmountSpec, RateSource, Unavailable
from prama.semantic.relationships import Tolerance


@dataclasses.dataclass(frozen=True, slots=True)
class Side:
    """One half of a reconciliation, and how to read it."""

    name: str
    amount_column: str
    spec: AmountSpec = dataclasses.field(default_factory=AmountSpec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "amount_column": self.amount_column,
            "spec": self.spec.to_dict(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Definition:
    """Everything a reconciliation needs to be run twice and agree.

    Deliberately a value: two runs of the same definition on the same data are
    the same run, and a definition that changed between them is visible as a
    different definition rather than as a mysterious change in the breaks.
    """

    name: str
    left: Side
    right: Side
    key: MatchKey
    tolerance: Tolerance
    target_currency: str = ""
    #: Days of slack on the last key component. Zero means exact; one is the
    #: usual answer for two systems that book on adjacent days.
    date_window: int = 0
    rounding_places: int | None = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "key": self.key.to_dict(),
            "tolerance": self.tolerance.to_dict(),
            "target_currency": self.target_currency,
            "date_window": self.date_window,
            "rounding_places": self.rounding_places,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Run:
    """What one reconciliation concluded, and everything it used to conclude it."""

    definition: Definition
    business_date: date
    match: MatchReport
    population: Population
    #: Normalisation inputs actually used — every rate, with its source and the
    #: day it was quoted for. The record that makes the run reproducible, and
    #: the first thing to look at when a cleared break reappears.
    rates_used: tuple[dict[str, Any], ...] = ()
    #: Set when the run could not complete: a missing rate, an unmapped code.
    #: A refusal rather than a partial answer, because a reconciliation missing
    #: some of its rows is not a smaller reconciliation, it is a wrong one.
    refusal: str = ""

    @property
    def completed(self) -> bool:
        return not self.refusal

    @property
    def is_clean(self) -> bool:
        return self.completed and not self.population.genuine

    def headline(self) -> str:
        """The one sentence, and it is about the match rate when it needs to be."""
        if self.refusal:
            return f"{self.definition.name} could not be run: {self.refusal}"
        if self.match.looks_misconfigured:
            return (
                f"{self.definition.name}: {self.match.describe()} — look at this before "
                f"the {len(self.population):,} breaks, which are mostly downstream of it"
            )
        return f"{self.definition.name}: {self.population.describe()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition": self.definition.to_dict(),
            "business_date": self.business_date.isoformat(),
            "completed": self.completed,
            "clean": self.is_clean,
            "refusal": self.refusal,
            "match": self.match.to_dict(),
            "population": self.population.to_dict(),
            "breaks": [item.to_dict() for item in self.population.breaks],
            "rates_used": list(self.rates_used),
            "headline": self.headline(),
        }


class Reconciliation:
    """Runs one definition against two datasets."""

    def __init__(self, definition: Definition, *, rates: RateSource | None = None) -> None:
        self._definition = definition
        self._rates = rates

    def run(
        self,
        left: Sequence[Mapping[str, Any]],
        right: Sequence[Mapping[str, Any]],
        *,
        business_date: date,
    ) -> Run:
        definition = self._definition
        matcher = (
            ToleranceMatcher(
                definition.key,
                window=definition.date_window,
                near=getattr(definition, "date_column", ""),
            )
            if definition.date_window
            else Matcher(definition.key)
        )
        report = matcher.match(left, right)

        target = definition.target_currency or definition.right.spec.currency or ""
        left_normaliser = AmountNormaliser(
            definition.left.spec, target_currency=target, rates=self._rates
        )
        right_normaliser = AmountNormaliser(
            definition.right.spec, target_currency=target, rates=self._rates
        )
        classifier = Classifier(definition.tolerance, rounding_places=definition.rounding_places)

        breaks: list[Break] = []
        seen_rates: dict[str, dict[str, Any]] = {}
        try:
            for pair in report.pairs:
                left_total, left_steps = self._total(
                    pair.left,
                    definition.left.amount_column,
                    left_normaliser,
                    business_date,
                    seen_rates,
                )
                right_total, right_steps = self._total(
                    pair.right,
                    definition.right.amount_column,
                    right_normaliser,
                    business_date,
                    seen_rates,
                )
                found = classifier.classify(
                    pair.render_key(),
                    left_total,
                    right_total,
                    normalisation=(*left_steps, *right_steps),
                    aggregated=pair.is_aggregated,
                    # The matcher knows and the comparison cannot: a pair
                    # found only by looking at the adjacent day is the same
                    # item recognised on two dates.
                    timing=pair.matched_by_tolerance,
                )
                if found is not None:
                    breaks.append(found)

            for missing in report.unmatched_left:
                total, steps = self._total(
                    missing.rows,
                    definition.left.amount_column,
                    left_normaliser,
                    business_date,
                    seen_rates,
                )
                breaks.append(
                    Break(
                        key=missing.render_key(),
                        kind=BreakKind.MISSING,
                        left=total,
                        right=None,
                        because=(
                            f"present in {definition.left.name} and not in {definition.right.name}"
                        ),
                        normalisation=steps,
                    )
                )
            for extra in report.unmatched_right:
                total, steps = self._total(
                    extra.rows,
                    definition.right.amount_column,
                    right_normaliser,
                    business_date,
                    seen_rates,
                )
                breaks.append(
                    Break(
                        key=extra.render_key(),
                        kind=BreakKind.EXTRA,
                        left=None,
                        right=total,
                        because=(
                            f"present in {definition.right.name} and not in {definition.left.name}"
                        ),
                        normalisation=steps,
                    )
                )
        except Unavailable as error:
            # A refusal, not a partial answer. A reconciliation missing some of
            # its rows is not a smaller reconciliation; it is a wrong one, and
            # the total it reports would be quoted.
            return Run(
                definition=definition,
                business_date=business_date,
                match=report,
                population=Population(),
                rates_used=tuple(seen_rates.values()),
                refusal=str(error),
            )

        return Run(
            definition=definition,
            business_date=business_date,
            match=report,
            population=Population(breaks=attribute_to_fx(breaks)),
            rates_used=tuple(seen_rates.values()),
        )

    def _total(
        self,
        rows: Sequence[Mapping[str, Any]],
        column: str,
        normaliser: AmountNormaliser,
        business_date: date,
        seen_rates: dict[str, dict[str, Any]],
    ) -> tuple[Decimal | None, tuple[str, ...]]:
        """Normalise each row, then sum. In that order, and it matters.

        Summing first and converting the total is cheaper and wrong whenever
        the rows are in more than one currency — it converts a meaningless
        mixed-currency sum at one rate and produces a total that looks
        plausible.
        """
        total = Decimal(0)
        steps: list[str] = []
        unvalued = 0
        for row in rows:
            normalised = normaliser.normalise(row, column, business_date)
            if normalised.value is None:
                # Not skipped. `match.aggregate` states the rule this module
                # then failed to follow: a null in an amount column is not
                # zero, and dropping the row makes the total wrong by exactly
                # the missing amount — so the side reconciles, or breaks by a
                # number that looks like a value difference, when the finding
                # is that a posting has no amount at all.
                unvalued += 1
                continue
            total += normalised.value
            for _, detail in normalised.steps:
                if detail not in steps:
                    steps.append(detail)
                if "converted" in detail:
                    seen_rates.setdefault(detail, {"detail": detail})
        if unvalued:
            steps.append(
                f"{unvalued} row(s) carry no {column}, so this side has no total — "
                "treating a missing amount as zero would report it as a value "
                "difference of exactly the wrong size"
            )
            return None, tuple(steps)
        return total, tuple(steps)
