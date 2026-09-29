"""The print packs, assembled from the estate: declarations, controls, an attestation.

What goes into each pack is gathered here, once, and rendered by
`prama.report.render`. The console's ``/reports`` screens and
``/api/v1/reports`` both read through here, so the HTML a person downloads from
the console and the HTML a script downloads from the API are the same document,
and the JSON a script asks for is the content that document was rendered from.

There is no server-side PDF: the packs are print-ready HTML, and "Print to PDF"
in a browser is the PDF (see `prama.report.render`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.backend import compile_for
from prama.core.errors import PramaError
from prama.derive import ControlGenerator
from prama.derive.persisted import dataset_declaration_of
from prama.ir.resolve import resolved
from prama.report.render import (
    Artefact,
    Coverage,
    Provenance,
    attestation_pack,
    control_pack,
    declaration_pack,
)
from prama.semantic.services import EstateService
from prama.semantic.values import TIER_LABELS

#: Lifecycle states a pack reports on. A retired dataset is deliberately out of
#: scope and deliberately *counted* — an auditor asking "is this everything?"
#: gets a number rather than a shrug.
REPORTED_STATES = ("proposed", "active", "deprecated")

#: The packs an estate can produce on demand, for an index. An attestation pack
#: is per attestation, so it is listed with the attestations rather than here.
CATALOGUE = (
    {
        "name": "declarations",
        "title": "Declaration pack",
        "description": "What the business says its data is, including what nobody has connected.",
        "formats": ["html", "json"],
    },
    {
        "name": "controls",
        "title": "Control pack",
        "description": "Every generated control, its reason, and the SQL it becomes.",
        "formats": ["html", "json"],
    },
)


def coverage_dict(coverage: Coverage) -> dict[str, Any]:
    return {**dataclasses.asdict(coverage), "total": coverage.total, "summary": coverage.describe()}


async def index(uow: Any, tenant_id: str) -> dict[str, Any]:
    """Which packs exist, and how many declared datasets they would cover."""
    return {
        "declared": await uow.datasets.count_current(tenant_id),
        "reports": [dict(entry) for entry in CATALOGUE],
    }


async def _in_scope(uow: Any, tenant_id: str) -> tuple[list[Any], Coverage]:
    versions = await uow.datasets.list_current(tenant_id, limit=5000)
    reported = [v for v in versions if v.lifecycle_state in REPORTED_STATES]
    excluded = len(versions) - len(reported)
    reported.sort(key=lambda v: (v.criticality, v.name.lower()))
    return reported, Coverage(
        included=len(reported),
        excluded=excluded,
        exclusion_reason="retired, and therefore out of scope for this pack",
    )


async def declaration_contents(uow: Any, tenant_id: str) -> dict[str, Any]:
    """What the declaration pack says: the datasets, the gaps, the coverage."""
    reported, coverage = await _in_scope(uow, tenant_id)
    return {
        "coverage": coverage,
        "gaps": await EstateService(uow).coverage_gaps(tenant_id),
        "datasets": [
            {
                "name": version.name,
                "description": version.description or "",
                "criticality": version.criticality,
                "tier_label": TIER_LABELS.get(version.criticality, f"Tier {version.criticality}"),
                "shape": version.shape,
                "is_bound": version.is_bound,
                "has_grain": version.has_grain,
                "grain_statement": (version.grain_json or {}).get("statement", ""),
                "grain_attributes": (version.grain_json or {}).get("attributes", []),
                "owner": version.owner_id or "",
            }
            for version in reported
        ],
    }


async def control_contents(uow: Any, tenant_id: str) -> dict[str, Any]:
    """What the control pack says: every control, what could not be generated, coverage."""
    reported, _ = await _in_scope(uow, tenant_id)
    generator = ControlGenerator()
    controls: list[dict[str, Any]] = []
    unsatisfiable: list[dict[str, Any]] = []
    covered: set[str] = set()

    for version in reported:
        attributes = await uow.attributes.for_dataset(version.dataset_id, tenant_id=tenant_id)
        generation = generator.generate(dataset_declaration_of(version, attributes))
        for derived in generation.controls:
            covered.add(version.dataset_id)
            controls.append(_describe(derived, version.name))
        for item in generation.unsatisfiable:
            unsatisfiable.append(
                {
                    "dataset": version.name,
                    "rule": item.rule,
                    "declared": item.declared,
                    "reason": item.reason,
                }
            )
    return {
        "controls": controls,
        "unsatisfiable": unsatisfiable,
        # The denominator is datasets, not controls: "220 controls" says
        # nothing about how much of the estate they touch, and a pack whose
        # coverage number counts its own contents can never report a gap.
        "coverage": Coverage(
            included=len(covered),
            excluded=len(reported) - len(covered),
            exclusion_reason="declared, but nothing could be generated from them",
        ),
    }


async def declarations(uow: Any, tenant_id: str, *, generated_by: str = "") -> Artefact:
    """The declaration pack, rendered."""
    contents = await declaration_contents(uow, tenant_id)
    return declaration_pack(
        provenance=Provenance(tenant_id=tenant_id, generated_by=generated_by), **contents
    )


async def controls(uow: Any, tenant_id: str, *, generated_by: str = "") -> Artefact:
    """The control pack, rendered."""
    contents = await control_contents(uow, tenant_id)
    return control_pack(
        provenance=Provenance(tenant_id=tenant_id, generated_by=generated_by), **contents
    )


def as_json(contents: dict[str, Any]) -> dict[str, Any]:
    """A pack's contents with its coverage spelled out, for a JSON caller."""
    return {**contents, "coverage": coverage_dict(contents["coverage"])}


async def attestation(
    uow: Any, tenant_id: str, attestation_id: str, key: bytes, *, generated_by: str = ""
) -> Artefact:
    """A signed attestation, as the document an auditor is handed."""
    row = await uow.attestations.in_tenant(attestation_id, tenant_id)
    value = await uow.attestations.value(attestation_id)
    intact, sealed = await uow.attestations.verify(attestation_id, key)
    return attestation_pack(
        provenance=Provenance(tenant_id=tenant_id, generated_by=generated_by),
        attestation=value,
        seal=row.seal,
        intact=intact,
        sealed=sealed,
        coverage=Coverage(
            included=value.coverage.controls_run,
            excluded=value.coverage.controls_in_scope - value.coverage.controls_run,
            exclusion_reason="in scope and produced no verdict in the period",
        ),
    )


def _describe(derived: Any, dataset_name: str) -> dict[str, Any]:
    """One control, with its plan and its SQL, or with the reason there is none.

    A control that cannot be lowered or compiled still appears — naming the
    failure. Dropping it would make the pack shorter and would make it claim
    coverage it does not have.
    """
    entry: dict[str, Any] = {
        "name": derived.identity,
        "dataset": dataset_name,
        "pql": derived.content,
        "description": derived.describe(),
        "plan_id": "",
        "metric_query": "",
        "residual_validators": [],
    }
    try:
        plan = resolved(derived.control)
        compiled = compile_for(plan, "postgresql")
    except PramaError as exc:
        entry["description"] = f"{entry['description']} (not compiled: {exc})"
        return entry
    entry["plan_id"] = plan.plan_id
    entry["description"] = plan.description
    entry["metric_query"] = compiled.metric_query
    entry["residual_validators"] = [
        {"validator": validator, "column": column}
        for validator, column in compiled.residual_validators
    ]
    return entry


__all__ = [
    "CATALOGUE",
    "REPORTED_STATES",
    "as_json",
    "attestation",
    "control_contents",
    "controls",
    "declaration_contents",
    "declarations",
    "index",
]
