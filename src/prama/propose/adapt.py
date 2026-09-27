"""Turning what Γ and the miners produce into proposals.

A small module on purpose. The generators know how to derive controls and
nothing about review; the queue knows about review and nothing about PQL. This
is the seam, and keeping it thin is what lets a new source of rules — a
document extractor, an example generaliser — reach the queue without either
side learning about the other.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.derive.generator import DerivedControl, Generation
from prama.derive.relationships import ComparisonSpec, RelationshipGeneration
from prama.propose.proposal import Backtest, Proposal


def from_control(control: DerivedControl, *, backtest: Backtest | None = None) -> Proposal:
    """A derived control, ready for review."""
    assertion = control.control.assertion
    subject = getattr(getattr(assertion, "subject", None), "name", "") or getattr(
        getattr(assertion, "column", None), "name", ""
    )
    return Proposal(
        identity=control.identity,
        content=control.content,
        content_hash=control.content_hash,
        provenance=control.provenance,
        description=control.control.describe(),
        dataset=control.control.target,
        subject=subject,
        rule=control.rule,
        severity=control.control.severity.value,
        backtest=backtest,
    )


def from_comparison(spec: ComparisonSpec, *, backtest: Backtest | None = None) -> Proposal:
    """A cross-dataset comparison, ready for review.

    Carries the same shape as a control proposal deliberately. A reviewer
    should not have to learn a second screen because the check happens to span
    two datasets — the question they are answering is the same one.
    """
    # Runnable PQL when the comparison has a PQL form (RECONCILE), so accepting
    # the proposal makes a control that runs; otherwise the specification.
    runnable = spec.to_pql()
    return Proposal(
        identity=spec.identity,
        content=runnable or spec.render(),
        content_hash=spec.content_hash,
        provenance=spec.provenance,
        description=spec.describe(),
        dataset=spec.left,
        subject=", ".join(spec.compare) or spec.right,
        rule=spec.rule,
        severity=spec.severity.value,
        backtest=backtest,
    )


def from_generation(generation: Generation) -> list[Proposal]:
    return [from_control(c) for c in generation.controls]


def from_relationship(generation: RelationshipGeneration) -> list[Proposal]:
    return [
        *(from_control(c) for c in generation.controls),
        *(from_comparison(c) for c in generation.comparisons),
    ]
