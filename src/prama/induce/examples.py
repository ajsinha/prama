"""Rules generalised from a handful of labelled cells.

`FR-IND-011`, and the Raha result: a usable rule from twenty labels or fewer.
The premise is that a steward who cannot write a control can always point at a
value and say "that one is wrong", and that twenty such judgements carry more
information than they look like they do.

**No model is involved, and that is not a limitation.** The candidate rules are
enumerated from the deterministic vocabulary already established — nullity,
semantic type, code-list membership, numeric range, string length — and scored
against the labels. A model would add candidates this cannot enumerate, and
would also add the possibility of a rule that fits the labels and means nothing;
the deterministic candidates all mean something by construction, and there are
enough of them.

**Precision matters more than recall here, and asymmetrically so.** A rule that
flags every bad cell and also a thousand good ones is worse than useless — it is
the noisy control that gets the whole suite switched off. A rule that catches
half the bad cells and nothing else is a real, shippable control. So a candidate
that misclassifies a *good* cell is eliminated outright, while one that misses a
bad cell is merely ranked lower.

**Active learning asks the question that resolves the most disagreement.** With
twenty labels several candidates usually survive, and they disagree about
specific cells. The next label worth asking for is the one those candidates
disagree about most — which is a far better use of a steward's attention than
the next row in the table, and is the difference between twenty labels and two
hundred.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import Any

from prama.classify.codelists import REGISTRY as CODELISTS
from prama.classify.validators import REGISTRY as VALIDATORS
from prama.core.provenance import Origin, Provenance, identity

#: Below this many labels, anything found is a description of the labels.
MINIMUM_LABELS = 6

#: A candidate that flags a cell the steward called good is eliminated, not
#: penalised. See the asymmetry above.
PERFECT_PRECISION = 1.0


@dataclasses.dataclass(frozen=True, slots=True)
class Label:
    """One steward judgement about one value."""

    value: Any
    #: True when the steward said the value is acceptable.
    good: bool
    #: Optional, and worth asking for: "this LEI is retired" is a different
    #: rule from "this LEI is malformed", and the reason is what tells them
    #: apart when the candidates fit equally well.
    note: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class Candidate:
    """A rule that might explain the labels."""

    #: PQL fragment: what goes after the column in ``CHECK dataset.column …``.
    predicate: str
    #: Plain language, for the steward who is confirming it.
    description: str
    #: True when the value is acceptable under this rule.
    accepts: Callable[[Any], bool] = dataclasses.field(compare=False, repr=False)

    def render(self, dataset: str, column: str) -> str:
        return f"CHECK {dataset}.{column} {self.predicate}"


@dataclasses.dataclass(frozen=True, slots=True)
class Scored:
    """A candidate with how well it matched the labels."""

    candidate: Candidate
    #: Bad cells it correctly flags.
    caught: int
    #: Bad cells it misses.
    missed: int
    #: Good cells it wrongly flags. Any at all disqualifies it.
    false_alarms: int

    @property
    def is_admissible(self) -> bool:
        """Whether it may be proposed at all.

        A single false alarm eliminates a candidate. That is deliberately
        harsher than a threshold: with twenty labels, one false alarm is five
        percent, and a control that flags five percent of good data is the one
        that gets the suite switched off.
        """
        return self.false_alarms == 0 and self.caught > 0

    @property
    def recall(self) -> float:
        total = self.caught + self.missed
        return self.caught / total if total else 0.0

    def describe(self) -> str:
        return (
            f"{self.candidate.description} — catches {self.caught} of "
            f"{self.caught + self.missed} values you marked wrong, and flags none of "
            f"the ones you marked right"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicate": self.candidate.predicate,
            "description": self.candidate.description,
            "caught": self.caught,
            "missed": self.missed,
            "false_alarms": self.false_alarms,
            "recall": round(self.recall, 4),
            "admissible": self.is_admissible,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Question:
    """The next value worth asking a steward about."""

    value: Any
    #: How the surviving candidates split on it. A value they all agree about
    #: teaches nothing, whichever way the steward answers.
    disagreement: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "disagreement": round(self.disagreement, 4),
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Generalisation:
    """What a handful of labels supports."""

    dataset: str
    column: str
    scored: tuple[Scored, ...] = ()
    #: Why nothing was concluded, when nothing was.
    refusal: str = ""
    #: The value to ask about next, when the candidates still disagree.
    next_question: Question | None = None

    @property
    def best(self) -> Scored | None:
        admissible = [s for s in self.scored if s.is_admissible]
        if not admissible:
            return None
        return max(admissible, key=lambda s: (s.recall, -len(s.candidate.predicate)))

    @property
    def is_settled(self) -> bool:
        """Whether one rule stands out enough to stop asking."""
        return self.best is not None and self.next_question is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "column": self.column,
            "scored": [s.to_dict() for s in self.scored],
            "refusal": self.refusal,
            "best": self.best.to_dict() if self.best else None,
            "next_question": self.next_question.to_dict() if self.next_question else None,
        }


class ExampleInducer:
    """Turns labelled cells into a control, and asks for the next label."""

    def __init__(self, *, minimum_labels: int = MINIMUM_LABELS) -> None:
        self._minimum = minimum_labels

    def generalise(
        self,
        dataset: str,
        column: str,
        labels: Sequence[Label],
        *,
        unlabelled: Sequence[Any] = (),
    ) -> Generalisation:
        if len(labels) < self._minimum:
            return Generalisation(
                dataset=dataset,
                column=column,
                refusal=(
                    f"{len(labels)} labels is too few; at least {self._minimum} are "
                    f"needed before a rule is a rule rather than a description of the "
                    f"labels"
                ),
            )
        bad = [label for label in labels if not label.good]
        if not bad:
            return Generalisation(
                dataset=dataset,
                column=column,
                refusal=(
                    "every labelled value was marked acceptable, so there is nothing "
                    "for a rule to separate. Mark a value you consider wrong"
                ),
            )

        scored = [self._score(candidate, labels) for candidate in self._candidates(labels)]
        scored.sort(key=lambda s: (not s.is_admissible, -s.recall))
        admissible = [s for s in scored if s.is_admissible]
        return Generalisation(
            dataset=dataset,
            column=column,
            scored=tuple(scored),
            next_question=self._next_question(admissible, unlabelled),
            refusal=(
                ""
                if admissible
                else (
                    "no rule separates the values you marked wrong from the ones you "
                    "marked right without also flagging some of the right ones. The "
                    "distinction may not be about the value itself — it may depend on "
                    "another column"
                )
            ),
        )

    # -- the candidate vocabulary ------------------------------------------

    def _candidates(self, labels: Sequence[Label]) -> list[Candidate]:
        """Every deterministic rule that could separate these labels.

        Enumerated rather than generated, so each one means something by
        construction. A model would add candidates this cannot reach and would
        also add the possibility of one that fits the labels and means nothing.
        """
        values = [label.value for label in labels]
        candidates: list[Candidate] = [
            Candidate(
                predicate="IS NOT NULL",
                description="the value must be present",
                accepts=lambda v: v is not None and str(v).strip() != "",
            )
        ]

        for name in VALIDATORS.names():
            validator = VALIDATORS.get(name)
            candidates.append(
                Candidate(
                    predicate=f"IS VALID '{name}'",
                    description=f"the value must be {validator.describe()}",
                    accepts=_validator_accepts(name),
                )
            )

        for name in CODELISTS.names():
            code_list = CODELISTS.get(name)
            candidates.append(
                Candidate(
                    predicate=f"IN CODELIST '{name}'",
                    description=f"the value must be a {code_list.label}",
                    accepts=_codelist_accepts(name),
                )
            )

        numeric = [v for v in values if isinstance(v, int | float) and not isinstance(v, bool)]
        if numeric:
            good = [
                label.value
                for label in labels
                if label.good and isinstance(label.value, int | float)
            ]
            if good:
                low, high = min(good), max(good)
                candidates.append(
                    Candidate(
                        predicate=f"BETWEEN {low:g} AND {high:g}",
                        description=f"the value must lie between {low:g} and {high:g}",
                        accepts=_range_accepts(low, high),
                    )
                )
                candidates.append(
                    Candidate(
                        predicate=f">= {low:g}",
                        description=f"the value must be at least {low:g}",
                        accepts=_minimum_accepts(low),
                    )
                )

        text = [str(v) for v in values if isinstance(v, str)]
        if text:
            good_text = [
                str(label.value) for label in labels if label.good and isinstance(label.value, str)
            ]
            if good_text:
                widths = {len(v) for v in good_text}
                if len(widths) == 1:
                    width = widths.pop()
                    candidates.append(
                        Candidate(
                            predicate=f"HAS LENGTH BETWEEN {width} AND {width}",
                            description=f"the value must be exactly {width} characters",
                            accepts=_length_accepts(width, width),
                        )
                    )
                else:
                    low, high = min(widths), max(widths)
                    candidates.append(
                        Candidate(
                            predicate=f"HAS LENGTH BETWEEN {low} AND {high}",
                            description=(f"the value must be between {low} and {high} characters"),
                            accepts=_length_accepts(low, high),
                        )
                    )
                allowed = sorted(set(good_text))
                # Only when the steward saw the same value more than once.
                #
                # Without this the enumeration wins every time and means
                # nothing: with five distinct good LEIs labelled, ``IN
                # ('5493001…', '213800…', …)`` has perfect recall on the labels
                # and rejects every valid LEI in the world that is not one of
                # those five. It is memorisation with a perfect score, which is
                # exactly what it looks like from the outside.
                #
                # Repetition is the signal that separates a closed domain from
                # a sample. Seeing BUY and SELL five times each says the column
                # has two permitted values; seeing five identifiers once each
                # says nothing except that there were five of them.
                repeats_seen = len(allowed) < len(good_text)
                if repeats_seen and 1 < len(allowed) <= 12:
                    rendered = ", ".join(f"'{v}'" for v in allowed)
                    candidates.append(
                        Candidate(
                            predicate=f"IN ({rendered})",
                            description=f"the value must be one of {rendered}",
                            accepts=_membership_accepts(frozenset(allowed)),
                        )
                    )
        return candidates

    @staticmethod
    def _score(candidate: Candidate, labels: Sequence[Label]) -> Scored:
        caught = missed = false_alarms = 0
        for label in labels:
            accepted = candidate.accepts(label.value)
            if label.good and not accepted:
                false_alarms += 1
            elif not label.good and accepted:
                missed += 1
            elif not label.good:
                caught += 1
        return Scored(candidate=candidate, caught=caught, missed=missed, false_alarms=false_alarms)

    @staticmethod
    def _next_question(admissible: list[Scored], unlabelled: Sequence[Any]) -> Question | None:
        """The unlabelled value the surviving rules disagree about most.

        A value they all agree about teaches nothing, whichever way the steward
        answers it. This is the difference between twenty labels and two
        hundred.
        """
        if len(admissible) < 2 or not unlabelled:
            return None
        best: Question | None = None
        for value in unlabelled:
            votes = [s.candidate.accepts(value) for s in admissible]
            accepting = sum(votes)
            # Maximal at an even split, zero at unanimity.
            disagreement = 1.0 - abs(2 * accepting / len(votes) - 1.0)
            if disagreement <= 0:
                continue
            if best is None or disagreement > best.disagreement:
                best = Question(
                    value=value,
                    disagreement=disagreement,
                    reason=(
                        f"{accepting} of {len(votes)} surviving rules accept this value "
                        f"and the rest reject it, so your answer eliminates about half "
                        f"of them"
                    ),
                )
        return best


def generalisation_provenance(
    dataset: str, column: str, scored: Scored, labels: Sequence[Label]
) -> Provenance:
    bad = sum(1 for label in labels if not label.good)
    return Provenance(
        origin=Origin.EXAMPLE,
        rule="induce.examples",
        source_ref=f"{dataset}#{column}",
        statement=scored.describe(),
        observations=(
            f"generalised from {len(labels)} values you labelled, {bad} of them as wrong",
            f"catches {scored.caught} of {bad} and flags none of the values you accepted",
        ),
    )


def generalisation_identity(dataset: str, column: str, scored: Scored) -> str:
    return identity(dataset, "induce.examples", column, scored.candidate.predicate)


# ---------------------------------------------------------------------------
# Acceptance predicates, built as closures so a candidate is self-contained
# ---------------------------------------------------------------------------


def _validator_accepts(name: str) -> Callable[[Any], bool]:
    def accepts(value: Any) -> bool:
        return value is None or VALIDATORS.get(name).judge(str(value)).valid

    return accepts


def _codelist_accepts(name: str) -> Callable[[Any], bool]:
    def accepts(value: Any) -> bool:
        return value is not None and CODELISTS.get(name).contains(str(value))

    return accepts


def _range_accepts(low: float, high: float) -> Callable[[Any], bool]:
    def accepts(value: Any) -> bool:
        return isinstance(value, int | float) and low <= value <= high

    return accepts


def _minimum_accepts(low: float) -> Callable[[Any], bool]:
    def accepts(value: Any) -> bool:
        return isinstance(value, int | float) and value >= low

    return accepts


def _length_accepts(low: int, high: int) -> Callable[[Any], bool]:
    def accepts(value: Any) -> bool:
        return value is not None and low <= len(str(value)) <= high

    return accepts


def _membership_accepts(allowed: frozenset[str]) -> Callable[[Any], bool]:
    def accepts(value: Any) -> bool:
        return str(value) in allowed

    return accepts
