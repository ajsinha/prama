"""The regulatory control catalogue: obligations, citations, and coverage.

An auditor's question is never "do you have data quality controls". It is
*"which controls address principle 4, and did they pass?"* — and a system that
cannot answer it by obligation is a system whose evidence has to be assembled by
hand every examination.

So a catalogue entry is not a rule. It is an obligation with a citation, a
control objective in the business's own words, and one or more PQL templates
that would discharge it. The templates are **templates**: they name the
attributes they need, and until an estate has bound them to real datasets they
are not coverage. That distinction is the whole point of this module, because
the flattering alternative — counting shipped templates as controls — reports a
bank as compliant on the strength of a file nobody has read.

Three states, never two. For every obligation:

* **Unaddressed** — no control exists. A gap.
* **Addressed but unproven** — controls exist and have produced no verdict for
  the period. *Not* the same as passing, and the difference is exactly what a
  regulator is examining.
* **Addressed and proven** — controls ran, and here is what they found.

A coverage report that collapsed the middle state into either neighbour would be
useless in opposite directions: into the first it under-reports the estate, into
the last it certifies work nobody did.

**Citations are load-bearing.** Every obligation names a document and a clause,
because "show me where this comes from" is the follow-up to every finding, and a
control whose provenance is folklore is one the bank cannot defend.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable, Mapping
from typing import Any

from prama.semantic.relationships import RelationshipKind


class Standing(enum.Enum):
    """How an obligation stands for a period."""

    UNADDRESSED = "unaddressed"
    ADDRESSED_UNPROVEN = "addressed_unproven"
    PROVEN_CLEAN = "proven_clean"
    PROVEN_WITH_EXCEPTIONS = "proven_with_exceptions"

    @property
    def is_a_gap(self) -> bool:
        """Whether this needs work before an examination.

        Both of the first two. An obligation whose controls have never run is
        as undefended as one with no controls — the difference is how long it
        takes to fix, not whether it is a problem.
        """
        return self in (Standing.UNADDRESSED, Standing.ADDRESSED_UNPROVEN)

    @property
    def label(self) -> str:
        return {
            Standing.UNADDRESSED: "no control addresses this",
            Standing.ADDRESSED_UNPROVEN: "controls exist and have not run in this period",
            Standing.PROVEN_CLEAN: "controls ran and found nothing",
            Standing.PROVEN_WITH_EXCEPTIONS: "controls ran and found exceptions",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Citation:
    """Where an obligation comes from, precisely enough to look up.

    ``confirmed`` records whether a person has checked this reference against
    the published text. It defaults to false and is *meant* to be visible:
    "show me where this comes from" is the follow-up to every finding an
    examiner makes, and an unverified article number that turns out to be wrong
    costs more credibility than having cited nothing. Marking them is what lets
    a bank's own compliance function work through the list rather than
    discovering the problem in the room.
    """

    document: str
    clause: str
    #: The publishing body, because two documents share a number often enough.
    authority: str = ""
    url: str = ""
    #: Checked against the published text by a person, and by whom.
    confirmed: bool = False
    confirmed_by: str = ""

    def __post_init__(self) -> None:
        if self.confirmed and not self.confirmed_by:
            raise ValueError(
                f"{self.render()} is marked confirmed with nobody named. "
                "An unattributable confirmation is not one."
            )

    def render(self) -> str:
        body = f"{self.authority} " if self.authority else ""
        return f"{body}{self.document} {self.clause}".strip()

    def render_with_standing(self) -> str:
        """The citation, and whether anybody has checked it."""
        if self.confirmed:
            return f"{self.render()} (confirmed by {self.confirmed_by})"
        return f"{self.render()} [unconfirmed against the published text]"


@dataclasses.dataclass(frozen=True, slots=True)
class Template:
    """A PQL control an estate can instantiate, and what it needs first."""

    identity: str
    #: PQL with ``{placeholders}`` for the attributes an estate must supply.
    pql: str
    #: Attribute roles this template needs — not column names. An estate binds
    #: them to its own columns, which is what makes one template serve four
    #: banks whose warehouses agree about nothing.
    requires: tuple[str, ...] = ()
    severity: str = "critical"
    dimension: str = "accuracy"
    cadence: str = "daily"
    note: str = ""

    def bind(self, columns: Mapping[str, str]) -> str:
        """The template with its placeholders filled in.

        Refuses on a missing binding rather than emitting PQL with a hole in
        it: a control that names ``{amount}`` compiles to SQL that names a
        column called ``{amount}``, and the failure surfaces at execution as a
        database error nobody connects to a template.
        """
        missing = [name for name in self.requires if name not in columns]
        if missing:
            from prama.core.errors import ValidationError

            raise ValidationError(
                f"{self.identity} needs {', '.join(missing)} and they were not bound",
                remedy=(
                    "Map every required attribute to a column in your estate. A "
                    "template with an unbound placeholder is not a control."
                ),
                context={"template": self.identity, "missing": missing},
            )
        return self.pql.format(**columns)


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipRequirement:
    """An obligation discharged by a *declaration*, not by a control.

    Some obligations are not checks on a dataset at all. "Every trade was
    reported" is a statement about two populations, and "these three feeds
    together cover the book" is a statement about a set of them. In Prama those
    are relationship declarations, from which the generator derives controls
    (``docs/03 §2.4``) — so writing them as PQL here would mean inventing
    syntax the language does not have, and a catalogue whose templates do not
    parse is a catalogue of promises.
    """

    kind: RelationshipKind
    #: What it connects, in placeholder terms, e.g. "{trade_store} -> {report}".
    between: str
    note: str = ""

    def render(self) -> str:
        return f"{self.kind.value}: {self.between}"


@dataclasses.dataclass(frozen=True, slots=True)
class Obligation:
    """One thing a regulator requires, and what would discharge it."""

    identity: str
    regime: str
    citation: Citation
    #: What it requires, in the words a business owner would use. Not the
    #: regulation's own words: a control objective nobody can read is one
    #: nobody checks against.
    objective: str
    templates: tuple[Template, ...] = ()
    #: Declarations that discharge part of this obligation.
    relationships: tuple[RelationshipRequirement, ...] = ()
    #: The part of the objective nothing here discharges. Written out rather
    #: than left to be inferred from an absence: an obligation listed in a
    #: catalogue reads as an obligation handled, and a reader who assumes that
    #: finds out in the examination room.
    not_discharged: str = ""
    #: The BCBS 239 principle this maps to, where it maps to one.
    principle: str = ""

    def __post_init__(self) -> None:
        if not self.templates and not self.relationships and not self.not_discharged:
            raise ValueError(
                f"{self.identity} ships nothing that discharges it and does not say so. "
                "An obligation with no templates, no relationships and no stated gap "
                "is an entry that looks covered."
            )

    @property
    def is_fully_discharged(self) -> bool:
        """Whether everything in the objective is addressed by something here."""
        return not self.not_discharged

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "regime": self.regime,
            "citation": self.citation.render(),
            "citation_confirmed": self.citation.confirmed,
            "objective": self.objective,
            "principle": self.principle,
            "templates": [t.identity for t in self.templates],
            "relationships": [r.render() for r in self.relationships],
            "not_discharged": self.not_discharged,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ObligationStanding:
    """How one obligation stands, and on what evidence."""

    obligation: Obligation
    standing: Standing
    controls: tuple[str, ...] = ()
    passed: int = 0
    failed: int = 0
    not_established: int = 0
    never_ran: int = 0

    def describe(self) -> str:
        head = f"{self.obligation.identity} ({self.obligation.citation.render()}): "
        if self.standing is Standing.UNADDRESSED:
            return head + "no control addresses this."
        counted = (
            f"{len(self.controls)} control(s); {self.passed} passed, "
            f"{self.failed} failed, {self.not_established} not established"
        )
        if self.never_ran:
            counted += f", {self.never_ran} never ran"
        return head + counted + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.obligation.to_dict(),
            "standing": self.standing.value,
            "standing_label": self.standing.label,
            "is_a_gap": self.standing.is_a_gap,
            "controls": list(self.controls),
            "passed": self.passed,
            "failed": self.failed,
            "not_established": self.not_established,
            "never_ran": self.never_ran,
            "message": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    """How a whole regime stands. The answer to the auditor's question."""

    regime: str
    standings: tuple[ObligationStanding, ...] = ()

    @property
    def gaps(self) -> tuple[ObligationStanding, ...]:
        return tuple(s for s in self.standings if s.standing.is_a_gap)

    @property
    def unaddressed(self) -> tuple[ObligationStanding, ...]:
        return tuple(s for s in self.standings if s.standing is Standing.UNADDRESSED)

    @property
    def unproven(self) -> tuple[ObligationStanding, ...]:
        return tuple(s for s in self.standings if s.standing is Standing.ADDRESSED_UNPROVEN)

    @property
    def with_exceptions(self) -> tuple[ObligationStanding, ...]:
        return tuple(s for s in self.standings if s.standing is Standing.PROVEN_WITH_EXCEPTIONS)

    def describe(self) -> str:
        """A sentence that names what is *not* covered before what is.

        A coverage figure quoted alone reads as an achievement. The number that
        matters at an examination is the count of obligations nothing addresses,
        and it belongs at the front.
        """
        total = len(self.standings)
        if not total:
            return f"{self.regime}: no obligations are loaded, so nothing is covered."
        parts = []
        if self.unaddressed:
            parts.append(f"{len(self.unaddressed)} obligation(s) have no control at all")
        if self.unproven:
            parts.append(
                f"{len(self.unproven)} have controls that produced no verdict in this "
                "period, which is not the same as passing"
            )
        clean = sum(1 for s in self.standings if s.standing is Standing.PROVEN_CLEAN)
        if clean:
            parts.append(f"{clean} were proven clean")
        if self.with_exceptions:
            parts.append(f"{len(self.with_exceptions)} were proven with exceptions")
        return f"{self.regime}: " + "; ".join(parts) + f" (of {total})."

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "obligations": len(self.standings),
            "unaddressed": len(self.unaddressed),
            "unproven": len(self.unproven),
            "with_exceptions": len(self.with_exceptions),
            "standings": [s.to_dict() for s in self.standings],
            "message": self.describe(),
        }


class Catalogue:
    """Obligations by regime, and coverage against a set of controls."""

    def __init__(self, obligations: Iterable[Obligation] = ()) -> None:
        self._obligations = tuple(obligations)

    def __len__(self) -> int:
        return len(self._obligations)

    @property
    def obligations(self) -> tuple[Obligation, ...]:
        return self._obligations

    def regimes(self) -> tuple[str, ...]:
        return tuple(sorted({o.regime for o in self._obligations}))

    def of_regime(self, regime: str) -> tuple[Obligation, ...]:
        return tuple(o for o in self._obligations if o.regime.lower() == regime.lower())

    def of_principle(self, principle: str) -> tuple[Obligation, ...]:
        """Every obligation mapping to one BCBS 239 principle.

        The literal form of the auditor's question, which is why it is a method
        rather than something a caller filters for itself.
        """
        return tuple(o for o in self._obligations if o.principle == principle)

    def coverage(
        self,
        regime: str,
        *,
        controls_by_template: Mapping[str, Iterable[str]],
        verdicts: Mapping[str, str] | None = None,
    ) -> Coverage:
        """How a regime stands, given which controls exist and what they found.

        ``controls_by_template`` maps a template identity to the control ids an
        estate instantiated from it. ``verdicts`` maps a control id to its
        verdict for the period; a control absent from it has not run, which is
        recorded rather than assumed to be a pass.
        """
        verdicts = verdicts or {}
        standings: list[ObligationStanding] = []

        for obligation in self.of_regime(regime):
            controls: list[str] = []
            for template in obligation.templates:
                controls.extend(controls_by_template.get(template.identity, ()))

            if not controls:
                standings.append(
                    ObligationStanding(obligation=obligation, standing=Standing.UNADDRESSED)
                )
                continue

            passed = sum(1 for c in controls if verdicts.get(c) == "pass")
            failed = sum(1 for c in controls if verdicts.get(c) == "fail")
            unestablished = sum(
                1 for c in controls if verdicts.get(c) in ("indeterminate", "error")
            )
            never = sum(1 for c in controls if c not in verdicts)

            if never == len(controls):
                standing = Standing.ADDRESSED_UNPROVEN
            elif failed or unestablished:
                standing = Standing.PROVEN_WITH_EXCEPTIONS
            else:
                standing = Standing.PROVEN_CLEAN

            standings.append(
                ObligationStanding(
                    obligation=obligation,
                    standing=standing,
                    controls=tuple(controls),
                    passed=passed,
                    failed=failed,
                    not_established=unestablished,
                    never_ran=never,
                )
            )
        return Coverage(regime=regime, standings=tuple(standings))


__all__ = [
    "Catalogue",
    "Citation",
    "Coverage",
    "Obligation",
    "ObligationStanding",
    "RelationshipRequirement",
    "Standing",
    "Template",
]
