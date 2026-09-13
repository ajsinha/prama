"""Catalogue write-back: putting quality state where people already look.

Nobody opens a data quality tool to find out whether a table is trustworthy.
They open the catalogue — Alation, Collibra, Atlan, Purview — because that is
where they were going anyway. A control plane whose verdicts live only inside
itself is one whose verdicts are read by the people who already agreed with it.

So this is an SPI, and the shape of what gets written is the whole design:

* **A badge without a date is a lie by omission.** "Trusted" on a table nobody
  has checked since March reads as current. Every write carries when the verdict
  was established and what it covered, and a catalogue that cannot store those
  is told so rather than given the badge alone.
* **"Not established" is written, not withheld.** The temptation is to publish
  passes and stay quiet otherwise, which leaves a table looking unassessed when
  it is actually failing. Silence and health must not render the same.
* **Nothing is written that cannot be traced back.** Every entry carries the
  evidence identifier, because the first response to a badge somebody disagrees
  with is "show me", and a badge that cannot answer gets ignored from then on.
* **A partial write is reported as partial.** A catalogue that accepted four of
  forty updates has left thirty-six stale, and stale-but-present is worse than
  absent: it is a figure people act on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
from collections.abc import Iterable, Sequence
from typing import Any

from prama.security.egress import Gate, ResidencyRefused


class Standing(enum.Enum):
    """What a catalogue should show for a dataset."""

    HEALTHY = "healthy"
    FAILING = "failing"
    #: Controls exist and could not establish a verdict — a screen without its
    #: residual, an errored run. Not a pass and not a failure.
    NOT_ESTABLISHED = "not_established"
    #: Controls exist and have not run in the window.
    UNPROVEN = "unproven"
    #: No control covers this dataset at all.
    UNCOVERED = "uncovered"

    @property
    def is_reassuring(self) -> bool:
        return self is Standing.HEALTHY

    @property
    def label(self) -> str:
        return {
            Standing.HEALTHY: "checked and clean",
            Standing.FAILING: "checked and failing",
            Standing.NOT_ESTABLISHED: "checked, and a pass could not be established",
            Standing.UNPROVEN: "controls exist and have not run",
            Standing.UNCOVERED: "no control covers this",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Badge:
    """One dataset's quality state, as a catalogue should carry it."""

    dataset: str
    standing: Standing
    #: When the verdict was established. Required — see the module docstring.
    established_at: str
    #: What it covered: ``full`` or an incremental scope. A badge from an
    #: incremental run says what it looked at, because "passed" over the rows
    #: examined is a narrower claim than "passed".
    coverage: str = "full"
    controls: int = 0
    failing_controls: int = 0
    #: The evidence this rests on, so "show me" has an answer.
    evidence_reference: str = ""
    detail: str = ""
    #: Where the dataset's data belongs. Carried on the badge because the
    #: residency question is about the *subject*, and an egress that knows its
    #: destination but not its subject's home cannot answer it.
    jurisdiction: str = ""

    def __post_init__(self) -> None:
        if not self.established_at:
            from prama.core.errors import ValidationError

            raise ValidationError(
                f"a badge for {self.dataset!r} has no date",
                remedy=(
                    "Every badge carries when its verdict was established. "
                    '"Trusted" on a table nobody has checked since March reads '
                    "as current, and a reader has no way to tell."
                ),
                context={"dataset": self.dataset},
            )

    def render(self) -> str:
        """The sentence a catalogue shows, dated and scoped."""
        scope = "" if self.coverage == "full" else f", over the rows examined ({self.coverage})"
        head = f"{self.standing.label} as at {self.established_at}{scope}"
        if self.standing is Standing.FAILING and self.failing_controls:
            head += f" — {self.failing_controls} of {self.controls} control(s) failing"
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "standing": self.standing.value,
            "label": self.standing.label,
            "established_at": self.established_at,
            "coverage": self.coverage,
            "controls": self.controls,
            "failing_controls": self.failing_controls,
            "evidence_reference": self.evidence_reference,
            "detail": self.detail,
            "jurisdiction": self.jurisdiction,
            "rendered": self.render(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class WriteReport:
    """What a write-back actually achieved."""

    attempted: int = 0
    written: int = 0
    #: ``dataset -> why``. Named rather than counted, because the useful
    #: question is which tables are now stale and not how many.
    refused: tuple[tuple[str, str], ...] = ()
    #: Facts the target cannot store. Reported so nobody believes the catalogue
    #: shows a date it has no field for.
    dropped_fields: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether everything offered was written.

        An empty publish is not complete. `written == attempted` is trivially
        true when both are zero, so `publish([])` reported a complete write
        while `describe()` said "nothing was written, because nothing was
        offered" — the two halves of the same object disagreeing, and the
        machine-readable half taking the flattering view (QA finding INT-014).

        A caller polling `complete` to decide whether a catalogue sync
        succeeded would have been told yes by a sync that never ran.
        """
        if not self.attempted:
            return False
        return self.written == self.attempted and not self.refused

    def describe(self) -> str:
        if not self.attempted:
            return "nothing was written, because nothing was offered"
        if self.complete:
            note = ""
            if self.dropped_fields:
                note = (
                    f" This catalogue cannot store {', '.join(self.dropped_fields)}, so "
                    "those are absent from it rather than shown as blank."
                )
            return f"{self.written} of {self.attempted} written.{note}"
        reasons = {why for _, why in self.refused}
        if len(reasons) == 1 and len(self.refused) == self.attempted:
            # Everything failed for one reason. That reason *is* the finding,
            # and listing the datasets instead would make a systemic problem
            # look like a list of unlucky tables.
            return (
                f"Nothing was written — all {self.attempted} refused for the same "
                f"reason: {next(iter(reasons))}."
            )
        # Otherwise the stale ones first. Stale-but-present is worse than
        # absent: it is a figure people act on.
        stale = ", ".join(name for name, _ in self.refused[:5])
        return (
            f"{len(self.refused)} dataset(s) were NOT updated and are now showing a "
            f"stale badge: {stale}"
            + ("…" if len(self.refused) > 5 else "")
            + f". {self.written} of {self.attempted} written."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "written": self.written,
            "refused": [{"dataset": name, "why": why} for name, why in self.refused],
            "dropped_fields": list(self.dropped_fields),
            "complete": self.complete,
            "message": self.describe(),
        }


class CatalogTarget(abc.ABC):
    """A catalogue Prama can write quality state into.

    Deliberately narrow. A target that could also *read* the catalogue would
    invite the estate to be defined there, and an estate defined in two places
    is an estate that disagrees with itself.
    """

    #: The catalogue's name, for a report.
    name: str = ""
    #: Where this catalogue physically is. A target that does not say cannot be
    #: residency-checked, and under a tenant with a rule that means refused —
    #: an unstated destination is not a domestic one.
    region: str = ""
    #: Fields this catalogue can actually store. A target that cannot hold a
    #: date says so here rather than dropping it silently — and then the badge
    #: is refused, because an undated badge is the failure this whole module is
    #: about.
    supports: frozenset[str] = frozenset(
        {"standing", "established_at", "coverage", "evidence_reference", "detail"}
    )

    @abc.abstractmethod
    def write(self, badge: Badge) -> None:
        """Write one badge, or raise if the catalogue would not take it."""

    def publish(self, badges: Iterable[Badge], *, gate: Gate | None = None) -> WriteReport:
        """Write many, reporting what did not land.

        Never raises for one bad badge: a catalogue rejecting one table must not
        leave the other thirty-nine unwritten, because those thirty-nine then
        show yesterday's verdict with today's confidence.

        ``gate`` is the residency check. It is optional because most
        deployments have no residency obligation and a mandatory argument would
        be one every caller passes ``None`` to — but when one is given, a badge
        that may not cross is refused *per badge* and the rest still land. A
        residency breach is not a reason to leave forty tables stale.
        """
        offered = list(badges)
        if "established_at" not in self.supports:
            # Refused wholesale rather than written undated. A badge without a
            # date reads as current forever.
            return WriteReport(
                attempted=len(offered),
                refused=tuple(
                    (
                        badge.dataset,
                        f"{self.name or 'this catalogue'} cannot store a date, "
                        "and an undated badge reads as current forever",
                    )
                    for badge in offered
                ),
            )

        written = 0
        refused: list[tuple[str, str]] = []
        for badge in offered:
            if gate is not None:
                try:
                    gate.require(
                        "catalog-write-back",
                        destination=self.region,
                        jurisdiction=badge.jurisdiction,
                        subject=f"the quality badge for {badge.dataset}",
                    )
                except ResidencyRefused as refusal:
                    refused.append((badge.dataset, refusal.message))
                    continue
            try:
                self.write(badge)
                written += 1
            except Exception as exc:
                refused.append((badge.dataset, f"{type(exc).__name__}: {exc}"))

        dropped = tuple(
            sorted(
                field
                for field in ("coverage", "evidence_reference", "detail")
                if field not in self.supports
            )
        )
        return WriteReport(
            attempted=len(offered),
            written=written,
            refused=tuple(refused),
            dropped_fields=dropped,
        )


class RecordingTarget(CatalogTarget):
    """The reference target: keeps everything in memory.

    Exists so the contract can be exercised without a Collibra licence — and so
    a real adapter has something to be checked against. An SPI whose only
    implementation is behind a vendor's login is an SPI nobody can test.
    """

    name = "recording"

    def __init__(
        self, *, supports: frozenset[str] | None = None, refuse: Sequence[str] = ()
    ) -> None:
        if supports is not None:
            self.supports = supports
        self.written: list[Badge] = []
        self._refuse = set(refuse)

    def write(self, badge: Badge) -> None:
        if badge.dataset in self._refuse:
            raise RuntimeError("the catalogue rejected this dataset")
        self.written.append(badge)

    def badge_for(self, dataset: str) -> Badge | None:
        return next((b for b in reversed(self.written) if b.dataset == dataset), None)


def _explains(failing: Sequence[Any], unestablished: Sequence[Any], records: Sequence[Any]) -> str:
    """The record a reader should be sent to, given the standing.

    A failure explains a FAILING badge; an unestablished record explains
    NOT_ESTABLISHED; for a healthy dataset any record does, so the first is
    fine and is stable enough to be quotable.
    """
    for candidates in (failing, unestablished, records):
        if candidates:
            return str(candidates[0].record_hash)
    return ""


def badges_from(
    latest: dict[str, Any],
    *,
    datasets: Iterable[str],
    established_at: str,
) -> list[Badge]:
    """Badges for every dataset, including the ones nothing covers.

    ``latest`` maps a control id to its most recent record. Datasets with no
    record at all get an ``UNCOVERED`` badge rather than being skipped: a
    catalogue showing a badge on nine tables and nothing on the tenth invites a
    reader to assume the tenth is fine.
    """
    by_dataset: dict[str, list[Any]] = {name: [] for name in datasets}
    for record in latest.values():
        by_dataset.setdefault(record.dataset, []).append(record)

    out: list[Badge] = []
    for dataset, records in sorted(by_dataset.items()):
        if not records:
            out.append(
                Badge(
                    dataset=dataset,
                    standing=Standing.UNCOVERED,
                    established_at=established_at,
                    detail="no control covers this dataset",
                )
            )
            continue
        failing = [r for r in records if r.verdict == "fail"]
        unestablished = [r for r in records if r.verdict in ("indeterminate", "error")]
        if failing:
            standing = Standing.FAILING
        elif unestablished:
            standing = Standing.NOT_ESTABLISHED
        else:
            standing = Standing.HEALTHY
        # The narrowest coverage of any contributing record. A dataset whose
        # badge said "full" because one control scanned everything, while
        # another only sampled, would be claiming more than was established.
        coverage = "full" if all(r.coverage == "full" for r in records) else "partial"
        out.append(
            Badge(
                dataset=dataset,
                standing=standing,
                established_at=established_at,
                coverage=coverage,
                controls=len(records),
                failing_controls=len(failing),
                # The record that *explains the standing*, not whichever came
                # first. A badge reading FAILING pointed at `records[0]` — the
                # first inserted, which dict order makes arbitrary and which is
                # usually one that passed. So "show me" showed a clean record
                # for a failing dataset (QA finding INT-009).
                #
                # A badge is a claim and this reference is its evidence. An
                # evidence link that answers a different question than the one
                # the badge raises is worse than no link: the reader checks it,
                # sees a pass, and concludes the badge is wrong.
                evidence_reference=_explains(failing, unestablished, records),
            )
        )
    return out


__all__ = [
    "Badge",
    "CatalogTarget",
    "RecordingTarget",
    "Standing",
    "WriteReport",
    "badges_from",
]
