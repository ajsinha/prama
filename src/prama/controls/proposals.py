"""The proposal queue, and Γ: what the declarations imply, and deciding on it.

Three operations the console's Proposals page, the HTTP API and a case study
all perform, written once:

* **the queue** — every control the estate's declarations, lineage and
  metadata imply that nobody has accepted or rejected yet, *and* every
  declaration that should have produced a control and could not. The second
  list is the reason the queue is worth having: a generator that reports only
  what it generated makes its output look complete when it is not.
* **derivation** — Γ over one declared dataset or one declared relationship,
  with its unsatisfiable items and (for a relationship) the comparison specs
  PQL cannot yet say as a row predicate.
* **deciding** — accepting a proposal (it enters the estate and begins to run)
  or rejecting it (recorded, so the same text is not proposed again).

Nothing here adjudicates. Γ is deterministic and versioned; no model output
decides whether a control passes (CON-007, NFR-AI-002).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

from prama.core.clock import utc_now
from prama.core.errors import NotFoundError, PramaError, ValidationError
from prama.derive import ControlGenerator, RelationshipGenerator
from prama.derive.persisted import dataset_declaration_of
from prama.propose.proposal import RejectionReason
from prama.semantic.relationships import RelationshipDeclaration

#: The reasons a proposal may be turned down, as stored.
REJECTION_REASONS: tuple[str, ...] = tuple(reason.value for reason in RejectionReason)


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


async def queue(uow: Any, tenant_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    """Everything awaiting a decision, and everything that could not be proposed.

    Scoped to one dataset when *dataset_id* is given; then only what that
    dataset's declaration and metadata imply is listed.
    """
    generator = ControlGenerator()
    versions = await uow.datasets.list_current(tenant_id, limit=5000)
    if dataset_id:
        versions = [v for v in versions if v.dataset_id == dataset_id]

    proposals: list[dict[str, Any]] = []
    unsatisfiable: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    accepted_already = 0
    rejected_already = 0
    for version in versions:
        attributes = await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id)
        declaration = dataset_declaration_of(version, attributes)
        try:
            generation = generator.generate(declaration)
        except PramaError as exc:
            # One bad declaration must not empty the queue for the estate.
            unsatisfiable.append(
                {
                    "dataset": version.name,
                    "dataset_id": version.dataset_id,
                    "rule": "generation",
                    "declared": version.slug,
                    "reason": str(exc),
                }
            )
            continue

        for control in generation.controls:
            # Two reasons a proposal is not offered, and they are different
            # answers. Already accepted: it is in the estate, and showing it
            # again would invite somebody to accept it twice. Already rejected:
            # a person said no to this exact text, and asking nightly is the
            # fastest way to lose their attention.
            if await uow.rejections.was_rejected(tenant_id, control.identity, control.content_hash):
                rejected_already += 1
                continue
            stored = await uow.controls.by_identity(tenant_id, control.identity)
            if stored is not None and stored.content_hash == control.content_hash:
                accepted_already += 1
                continue
            proposals.append(
                {
                    "dataset": version.name,
                    "dataset_id": version.dataset_id,
                    "identity": control.identity,
                    "rule": control.rule,
                    "sentence": control.describe(),
                    "pql": control.content,
                    "content_hash": control.content_hash,
                    "criticality": version.criticality,
                    # A proposal that changes an existing control is a
                    # different decision from one that adds a new control, and
                    # a queue that renders them identically gets the first
                    # waved through.
                    "amends": stored is not None,
                }
            )
        for item in generation.unsatisfiable:
            unsatisfiable.append(
                {
                    "dataset": version.name,
                    "dataset_id": version.dataset_id,
                    "rule": item.rule,
                    "declared": item.declared,
                    "reason": item.reason,
                }
            )
        for postponed in generation.deferred:
            deferred.append(
                {
                    "dataset": version.name,
                    "dataset_id": version.dataset_id,
                    "rule": getattr(postponed, "rule", ""),
                    "reason": getattr(postponed, "reason", ""),
                }
            )
    # Proposals derived from lineage: controls carried downstream, and keys
    # checked against where they were copied from. Held while the edge they
    # rest on is only inferred.
    from prama.derive.lineage_controls import propose as from_lineage

    for mined in from_lineage(
        await uow.lineage.edges(tenant_id), await uow.controls.live(tenant_id)
    ):
        if dataset_id:
            continue  # a per-dataset view lists what that dataset's declaration implies
        content_hash = hashlib.sha256(mined.pql.encode("utf-8")).hexdigest()
        if await uow.rejections.was_rejected(tenant_id, mined.identity, content_hash):
            rejected_already += 1
            continue
        if await uow.controls.by_identity(tenant_id, mined.identity) is not None:
            accepted_already += 1
            continue
        if mined.deferred_because:
            deferred.append(
                {
                    "dataset": mined.dataset,
                    "dataset_id": "",
                    "rule": mined.rule,
                    "reason": mined.deferred_because,
                }
            )
            continue
        proposals.append(
            {
                "dataset": mined.dataset,
                "dataset_id": "",
                "identity": mined.identity,
                "rule": mined.rule,
                "sentence": mined.sentence,
                "pql": mined.pql,
                "content_hash": content_hash,
                "criticality": 3,
                "amends": False,
            }
        )
    # Proposals the estate's metadata implies: a field that carries a rule
    # ("mandatory", "allowed values", "key") offers its check once a value is
    # set. A rule that renders to PQL that does not parse is shown as
    # unsatisfiable, not dropped.
    from prama.semantic.services.metadata import proposals as from_metadata

    criticality = {v.dataset_id: v.criticality for v in versions}
    for implied in await from_metadata(uow, tenant_id, dataset_id=dataset_id or ""):
        if "error" in implied:
            unsatisfiable.append(
                {
                    "dataset": implied["dataset"],
                    "dataset_id": "",
                    "rule": "metadata",
                    "declared": implied["pql"],
                    "reason": implied["error"],
                }
            )
            continue
        proposals.append({**implied, "criticality": criticality.get(implied["dataset_id"], 3)})
    # References that follow from two attributes meaning the same thing, when
    # one dataset owns that meaning as its key (`prama.semantic.correlate`).
    if not dataset_id:
        from prama.semantic.services.metadata import correlation

        for referenced in (await correlation(uow, tenant_id))["proposals"]:
            proposals.append({**referenced, "criticality": 3})
    # Tier 1 first, then by rule so a systematically bad rule is visible as a
    # block rather than scattered through the list.
    proposals.sort(key=lambda p: (p["criticality"], p["rule"], p["dataset"]))
    return {
        "proposals": proposals,
        "unsatisfiable": unsatisfiable,
        "deferred": deferred,
        # Counted and shown. An empty queue after a generator run means either
        # "everything is already decided" or "nothing was generated", and
        # those are opposite facts.
        "accepted_already": accepted_already,
        "rejected_already": rejected_already,
    }


# ---------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------


async def accept(
    uow: Any,
    tenant_id: str,
    *,
    identity: str,
    pql: str,
    by: str | None,
    rule: str = "",
    dataset_id: str = "",
    reason: str = "accepted from the proposal queue",
) -> Any:
    """Accept a proposal: the control enters the estate and begins to run.

    The PQL is re-derived on the way in — parsed, lowered, hashed by the DAO —
    so what is stored is what was reviewed, and a request field cannot
    introduce a severity the text does not carry.
    """
    control, _ = await uow.controls.declare(
        tenant_id=tenant_id,
        identity=identity,
        pql=pql,
        # Lineage-derived proposals are mined from the estate; the rule
        # (lineage_propagated, lineage_referential) says which way.
        origin="mining" if rule.startswith("lineage_") else "declaration",
        rule=rule,
        source_ref=dataset_id,
        status="proposed",
        # Derived, not written: the derivation is the maker and `by` the check
        # (prama.controls.approval). Recording `by` as the author would make a
        # Tier-1 derived control unacceptable by anybody.
        authored_by=None,
        reason=reason,
    )
    from prama.controls.approval import activate

    return await activate(uow, str(control.id), tenant_id=tenant_id, approver=by, reason=reason)


async def reject(
    uow: Any,
    tenant_id: str,
    *,
    identity: str,
    content_hash: str,
    by: str | None,
    reason: str = "incorrect",
    note: str = "",
) -> Any:
    """Turn a proposal down, and record that it was turned down.

    Recorded rather than dismissed. The reason matters to the learning loop —
    "too noisy" is a threshold problem and "incorrect" is a rule that should
    never have been proposed — and without the record the same proposal
    returns tomorrow night.
    """
    if reason not in REJECTION_REASONS:
        raise ValidationError(
            f"{reason!r} is not a reason a proposal can be rejected for",
            remedy=f"One of: {', '.join(REJECTION_REASONS)}.",
            context={"reason": reason},
        )
    return await uow.rejections.record(
        tenant_id=tenant_id,
        identity=identity,
        content_hash=content_hash,
        reason=reason,
        note=note,
        rejected_by=by,
        rejected_at=utc_now().isoformat(),
    )


# ---------------------------------------------------------------------------
# Derivation (Γ)
# ---------------------------------------------------------------------------


async def derive_dataset(uow: Any, tenant_id: str, dataset_id: str) -> tuple[Any, Any]:
    """Γ over one declared dataset: its current version, and what Γ concluded."""
    version = await uow.datasets.require_current(dataset_id, tenant_id=tenant_id)
    attributes = await uow.attributes.for_dataset(dataset_id, tenant_id=tenant_id)
    return version, ControlGenerator().generate(dataset_declaration_of(version, attributes))


async def derive_relationship(uow: Any, tenant_id: str, relationship_id: str) -> tuple[Any, Any]:
    """Γ over one declared relationship: its current version, and what Γ concluded.

    The stored declaration names its datasets by identifier, because it has to
    survive a rename; a control names the thing that exists in the engine. So
    the identifiers become the datasets' current names here, as the case-study
    harness does by hand — and a relationship to a dataset that no longer has
    a current version is refused rather than derived against a stale name.
    """
    version = await uow.relationships.current(relationship_id, tenant_id=tenant_id)
    if version is None:
        raise NotFoundError(
            f"relationship {relationship_id!r} has no current version",
            remedy="Check the identifier, or list the declared relationships.",
            context={"relationship_id": relationship_id},
        )
    names: dict[str, str] = {}
    for side in (version.from_dataset_id, version.to_dataset_id):
        dataset = await uow.datasets.current(side, tenant_id=tenant_id)
        if dataset is None:
            raise NotFoundError(
                f"the relationship names dataset {side!r}, which has no current version",
                remedy="Declare the dataset again, or retire the relationship.",
                context={"relationship_id": relationship_id, "dataset_id": side},
            )
        names[side] = dataset.slug
    declaration = RelationshipDeclaration.from_dict(
        {
            "kind": version.kind,
            "from_dataset_id": version.from_dataset_id,
            "to_dataset_id": version.to_dataset_id,
            "match_keys": list(version.match_keys_json or []),
            "compare": list(version.compare_json or []),
            "cardinality": version.cardinality,
            "tolerance": version.tolerance_json,
            "offset": version.offset_json,
            "filter_expression": version.filter_expression,
            "name": version.name,
            "description": version.description,
        }
    )
    readable = dataclasses.replace(
        declaration,
        from_dataset_id=names[version.from_dataset_id],
        to_dataset_id=names[version.to_dataset_id],
    )
    return version, RelationshipGenerator().generate(readable)


async def adopt(
    uow: Any,
    tenant_id: str,
    controls: Any,
    *,
    source_ref: str,
    criticality: int,
    schedule: str,
    by: str | None,
    activate: bool,
    reason: str,
) -> list[dict[str, Any]]:
    """Declare derived controls as proposals and, when asked, activate them.

    Idempotent by identity, like every declaration: deriving twice amends what
    changed and leaves the rest alone, and activating a control that is
    already running writes no new version.
    """
    adopted: list[dict[str, Any]] = []
    for derived in controls:
        entity, version = await uow.controls.declare(
            tenant_id=tenant_id,
            identity=derived.identity,
            pql=derived.content,
            rule=derived.rule,
            source_ref=source_ref,
            criticality=criticality,
            schedule=schedule,
            status="proposed",
            authored_by=None,  # derived: see accept()
            reason=reason,
        )
        if activate and version.status != "active":
            from prama.controls.approval import activate as approve

            version = await approve(
                uow, str(entity.id), tenant_id=tenant_id, approver=by, reason=reason
            )
        adopted.append({"identity": derived.identity, "version": version})
    return adopted


__all__ = [
    "REJECTION_REASONS",
    "accept",
    "adopt",
    "derive_dataset",
    "derive_relationship",
    "queue",
    "reject",
]
