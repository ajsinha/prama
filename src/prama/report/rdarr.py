"""The RDARR pack: obligations, the controls that address them, and what ran.

docs/corpus/19 calls this the demonstration that closes deals — a BCBS 239 attestation
pack for one risk domain, *generated* rather than assembled: every obligation,
the controls addressing it, their executions for the period, exceptions with
justifications, and a sign-off.

Everything it needs already exists and was not connected. The catalogue knows
what a regulator requires; the ledger knows what ran; the attestation knows who
signed. This is the join, and the join is where a pack stops being a document
somebody wrote and starts being a statement about what happened.

**The coverage is derived, not asserted.** Which controls address which
obligation comes from a binding an estate declared; whether they passed comes
from the ledger. Nothing in the pack is a number somebody typed, which is the
difference between a pack an examiner reads and a pack an examiner audits.

**Its most important section is the gaps.** An RDARR pack that led with what
passed would be a marketing document. Obligations with no control, and
obligations whose controls never ran, come first — and the second is stated as
its own thing, because "we have a control for that" and "we have evidence of
that" are the two answers an examiner is separating.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.packs.banking.regulatory import Catalogue, Coverage, Standing


@dataclasses.dataclass(frozen=True, slots=True)
class Pack:
    """One regime, one period, and everything that bears on it."""

    regime: str
    scope: str
    period_start: str
    period_end: str
    coverage: Coverage
    #: Controls per obligation, as the estate bound them. Carried so the pack
    #: can name them: an examiner asking which controls address an obligation
    #: wants their identifiers, not a count.
    bindings: dict[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    #: Evidence records in the period, for the replay section.
    evidence_records: int = 0
    evidence_root: str = ""
    #: Set when an attestation covers this pack.
    attested_by: str = ""
    attested_at: str = ""

    @property
    def is_defensible(self) -> bool:
        """Whether every obligation has evidence behind it.

        Not "whether everything passed". A pack full of exceptions that were
        found, explained and signed is defensible; a pack with an obligation
        nobody has evidence for is not, however clean the rest looks.
        """
        return not self.coverage.gaps

    def headline(self) -> str:
        """The sentence an examiner reads first, and it names the gaps."""
        coverage = self.coverage
        total = len(coverage.standings)
        if not total:
            return (
                f"{self.regime} over {self.scope}: no obligations are loaded, so this "
                "pack establishes nothing."
            )
        if self.is_defensible:
            exceptions = len(coverage.with_exceptions)
            tail = (
                f" {exceptions} carried exceptions, each listed with its disposition."
                if exceptions
                else " None carried exceptions."
            )
            return (
                f"{self.regime} over {self.scope}, {self.period_start} to "
                f"{self.period_end}: all {total} obligations have controls that "
                f"produced evidence in the period.{tail}"
            )
        return (
            f"{self.regime} over {self.scope}, {self.period_start} to {self.period_end}: "
            f"{len(coverage.unaddressed)} obligation(s) have no control and "
            f"{len(coverage.unproven)} have controls that produced no evidence in the "
            f"period. That is {len(coverage.gaps)} of {total} an examiner would ask about."
        )

    def sections(self) -> list[dict[str, Any]]:
        """The pack in reading order: gaps, then exceptions, then what held.

        The order is the argument. A pack that led with what passed would be a
        marketing document, and an examiner who had to look for the gaps would
        rightly wonder what else was arranged for them.
        """
        return [
            {
                "title": "Obligations with no control",
                "why": (
                    "Nothing addresses these. They are the first thing an examiner "
                    "will ask about and the first thing to fix."
                ),
                "standings": [s.to_dict() for s in self.coverage.unaddressed],
            },
            {
                "title": "Obligations with controls that produced no evidence",
                "why": (
                    '"We have a control for that" and "we have evidence of that" are '
                    "the two answers being separated here. A control that has not run "
                    "has proven nothing."
                ),
                "standings": [s.to_dict() for s in self.coverage.unproven],
            },
            {
                "title": "Obligations proven with exceptions",
                "why": (
                    "Controls ran and found something. Every exception is listed with "
                    "its disposition; a qualified position that is explained is a "
                    "defensible one."
                ),
                "standings": [s.to_dict() for s in self.coverage.with_exceptions],
            },
            {
                "title": "Obligations proven clean",
                "why": "Controls ran over the period and found nothing.",
                "standings": [
                    s.to_dict()
                    for s in self.coverage.standings
                    if s.standing is Standing.PROVEN_CLEAN
                ],
            },
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "scope": self.scope,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "defensible": self.is_defensible,
            "headline": self.headline(),
            "evidence_records": self.evidence_records,
            "evidence_root": self.evidence_root,
            "attested_by": self.attested_by,
            "attested_at": self.attested_at,
            "coverage": self.coverage.to_dict(),
            "sections": self.sections(),
        }


async def build(
    uow: Any,
    tenant_id: str,
    *,
    catalogue: Catalogue,
    regime: str,
    scope: str,
    period_start: str,
    period_end: str,
    bindings: dict[str, list[str]],
) -> Pack:
    """An RDARR pack, read from the ledger and the estate.

    ``bindings`` maps a template identity to the control ids an estate
    instantiated from it — the one thing neither the catalogue nor the ledger
    can know, because it is a decision the estate made.

    Verdicts come from the *latest* record per control within the period. A
    control that ran twenty times contributes one standing, not twenty: an
    obligation is not more addressed for having been checked hourly.
    """
    records = await uow.evidence.in_period(tenant_id, period_start, period_end)

    latest: dict[str, Any] = {}
    for record in records:
        control = record.control_id
        if not control:
            continue
        seen = latest.get(control)
        if seen is None or record.finished_at >= seen.finished_at:
            latest[control] = record
    verdicts = {control: record.verdict for control, record in latest.items()}

    coverage = catalogue.coverage(regime, controls_by_template=bindings, verdicts=verdicts)
    # Unpacked. `period_root` returns `(root, count)`, and assigning the pair
    # straight into `evidence_root` printed a Python tuple where the Merkle
    # root belongs — in a regulatory pack, in the field a reader checks the
    # evidence against (QA finding RPT-025). `attest.build` unpacks it three
    # modules away; this one did not, and nothing compared the two.
    root, _records_in_period = await uow.evidence.period_root(tenant_id, period_start, period_end)

    return Pack(
        regime=regime,
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        coverage=coverage,
        bindings={key: tuple(value) for key, value in bindings.items()},
        evidence_records=len(records),
        evidence_root=root,
    )


__all__ = ["Pack", "build"]
