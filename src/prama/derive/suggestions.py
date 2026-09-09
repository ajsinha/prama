"""Declaration defaults inferred from a profile — and never confirmed by one.

The point of the estate map is that a business owner declares what a dataset
*means*, and Prama derives controls from the declaration. The cost of that is a
form, and the form is the reason people stop. So the form should arrive already
filled in with what the data suggests.

The danger is precisely the same thing. A pre-filled form that a person clicks
through has produced a *declaration nobody made*, and every control derived from
it inherits an authority it never earned. Prama's whole thesis is the distinction
between what was observed and what was declared; a suggestion layer is where that
distinction is easiest to lose and most expensive to lose.

So three rules, and each of them costs something:

* **A suggestion carries its evidence, in a sentence.** Not "grain:
  account_id, as_of_date" but "these two together are distinct in every one of
  the 50,000 rows read". A default whose basis is invisible is a default nobody
  can disagree with, and a default nobody can disagree with is not confirmed
  when they accept it.
* **An unrepresentative profile pre-fills nothing.** The first thousand rows of
  a table are the oldest thousand; they show shape and no rate at all. Such a
  profile may *offer* a candidate and may not *select* one, so accepting it
  takes a deliberate act rather than an unchanged form.
* **Warnings are separate from defaults.** A column that is 94% one value is
  usually a field the source stopped populating, and a completeness control on
  it will pass forever while the column is useless. That is worth saying, and
  it is not a default to accept — presenting it as one would mean the reader
  either takes it or dismisses it, when what they need to do is look.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.profile.profiler import DatasetProfile
from prama.profile.statistics import ColumnProfile

#: Above this share, a single value is more likely an unfilled default than
#: data. Not a discovery — it is the same threshold ``dominant_value`` uses,
#: quoted here so the two cannot drift.
DOMINANT_SHARE = 0.9

#: A column this sparse is worth mentioning before somebody declares a
#: completeness control on it. Half is deliberately generous: the point is to
#: prompt a look, not to make a ruling, and a threshold tight enough to be
#: right every time would say nothing most of the time.
SPARSE_RATE = 0.5


@dataclasses.dataclass(frozen=True, slots=True)
class Suggestion:
    """One default the form may offer, and why."""

    field: str
    value: Any
    #: The evidence, in a sentence somebody can disagree with. A default whose
    #: basis is invisible is not confirmed when it is accepted.
    because: str
    #: What may honestly be said about the numbers behind it — the profile's own
    #: confidence note, carried rather than restated.
    confidence: str
    #: Whether the evidence is strong enough to arrive already selected. False
    #: does not mean "probably wrong"; it means "accepting this should be a
    #: deliberate act rather than an unchanged form".
    prefill: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "because": self.because,
            "confidence": self.confidence,
            "prefill": self.prefill,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Warning_:  # noqa: N801 - trailing underscore avoids shadowing the builtin
    """Something worth knowing before declaring, which is not a default.

    Named with a trailing underscore for the same reason ``Exception_`` is: the
    word is the one a reader will look for, and shadowing the builtin is worse
    than the underscore.
    """

    column: str
    message: str
    #: What it costs if it goes unnoticed. Written out rather than left to the
    #: reader, because the whole reason to surface these is that the cost is
    #: not obvious at declaration time — it arrives months later as a control
    #: that has passed every day and tested nothing.
    consequence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "message": self.message,
            "consequence": self.consequence,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Defaults:
    """What a profile suggests for one declaration form."""

    dataset: str
    suggestions: tuple[Suggestion, ...] = ()
    warnings: tuple[Warning_, ...] = ()
    #: The profile's own account of itself, shown once at the top rather than
    #: repeated on every field.
    confidence: str = ""
    rows_examined: int = 0
    is_representative: bool = True

    def of(self, field: str) -> Suggestion | None:
        return next((s for s in self.suggestions if s.field == field), None)

    @property
    def anything_prefilled(self) -> bool:
        return any(s.prefill for s in self.suggestions)

    def describe(self) -> str:
        if not self.suggestions and not self.warnings:
            return (
                f"{self.dataset} was profiled and suggested nothing. That is a "
                "statement about the profile, not about the dataset."
            )
        parts = [f"{len(self.suggestions)} suggestion(s)"]
        if self.warnings:
            parts.append(f"{len(self.warnings)} thing(s) worth looking at first")
        if not self.is_representative:
            parts.append(
                "nothing is pre-filled, because this profile read the first rows "
                "only and shows shape rather than any rate"
            )
        return f"{self.dataset}: " + ", ".join(parts) + f" — {self.confidence}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "warnings": [w.to_dict() for w in self.warnings],
            "confidence": self.confidence,
            "rows_examined": self.rows_examined,
            "representative": self.is_representative,
            "message": self.describe(),
        }


def defaults_from(profile: DatasetProfile) -> Defaults:
    """Turn a profile into things a declaration form may offer."""
    representative = profile.provenance.plan.strategy.is_representative
    note = profile.provenance.confidence_note
    suggestions: list[Suggestion] = []

    grain = _grain(profile, note, representative)
    if grain is not None:
        suggestions.append(grain)

    return Defaults(
        dataset=profile.qualified_name,
        suggestions=tuple(suggestions),
        warnings=tuple(_warnings(profile)),
        confidence=note,
        rows_examined=profile.rows,
        is_representative=representative,
    )


def _grain(profile: DatasetProfile, note: str, representative: bool) -> Suggestion | None:
    """The candidate grain, if the profile found one.

    A single key candidate is offered as the grain. Several are offered as a
    list and never as a *combination*: this profile tests each column alone, so
    "account_id and as_of_date together are unique" is a claim it has not made,
    and inventing it would be the one suggestion here nobody could check.
    """
    candidates = profile.key_candidates
    if not candidates:
        return None

    if len(candidates) == 1:
        because = (
            f"{candidates[0]} is distinct in every row and never null, so it "
            f"identifies a row on its own"
        )
    else:
        because = (
            f"{len(candidates)} column(s) are each distinct in every row: "
            f"{', '.join(candidates)}. Each identifies a row on its own — this "
            f"profile has not tested whether any combination does, so pick the "
            f"one that names what a row *is*"
        )
    return Suggestion(
        field="grain",
        value=candidates[0] if len(candidates) == 1 else "",
        because=because,
        confidence=note,
        # Pre-filled only when there is one candidate *and* the profile saw
        # enough to mean it. A head sample shows shape and no rate, so a key
        # candidate from one is a thing to look at rather than a thing to
        # accept by leaving the form alone.
        prefill=representative and len(candidates) == 1,
    )


def _warnings(profile: DatasetProfile) -> list[Warning_]:
    """Things to look at before declaring. Never defaults.

    At most one per column, and the order is which sentence is *true* as much as
    which is worst. A column can be sparse and constant at once; saying it
    "holds one value in every row" when two thirds of the rows have none is a
    false statement that happens to be reachable from a true predicate.
    """
    out: list[Warning_] = []
    for column in profile.columns:
        if column.rows == 0:
            continue
        if column.nulls == column.rows:
            out.append(
                Warning_(
                    column=column.name,
                    message=f"{column.name} is null in every row read",
                    consequence=(
                        "A control on it would fail everything or, if written as a "
                        "conditional, pass everything. Usually this is a field the "
                        "source stopped populating and nobody was told."
                    ),
                )
            )
            continue
        if _is_sparse(column):
            # Before the constant check, deliberately. A column that is 70% null
            # with one value in the rest satisfies both, and "holds one value in
            # every row" is a false sentence about it — the null rate is the true
            # statement and the more actionable one.
            out.append(
                Warning_(
                    column=column.name,
                    message=f"{column.name} is null in {column.null_rate:.0%} of rows read",
                    consequence=(
                        "Declare whether that is expected before a completeness "
                        "control is generated. If it is expected, the control needs a "
                        "condition; if it is not, this is already the finding."
                    ),
                )
            )
            continue
        if column.is_constant:
            # Before the dominant-value check, because a value covering 100% of
            # rows satisfies both and only one of the two consequences is true:
            # a constant is a constant, not "usually an unfilled default".
            only = column.top_values[0][0] if column.top_values else None
            out.append(
                Warning_(
                    column=column.name,
                    # "One distinct value", not "one value in every row": the
                    # distinct count ignores nulls, so a column with some nulls
                    # would otherwise be described as full of a value it lacks.
                    message=(
                        f"{column.name} holds one distinct value in the rows read"
                        + (f": {only!r}" if only is not None else "")
                    ),
                    consequence=(
                        "Nothing can vary, so nothing can be checked. It may still "
                        "belong in the declaration as context; it will not generate "
                        "a control worth running."
                    ),
                )
            )
            continue
        dominant = column.dominant_value
        if dominant is not None:
            value, share = dominant
            out.append(
                Warning_(
                    column=column.name,
                    message=f"{column.name} is {value!r} in {share:.0%} of rows read",
                    consequence=(
                        "A single value that common is usually an unfilled default "
                        "rather than data. A completeness control here will pass "
                        "every day while the column carries nothing."
                    ),
                )
            )
    return out


def _is_sparse(column: ColumnProfile) -> bool:
    return column.null_rate >= SPARSE_RATE


__all__ = [
    "DOMINANT_SHARE",
    "SPARSE_RATE",
    "Defaults",
    "Suggestion",
    "Warning_",
    "defaults_from",
]
