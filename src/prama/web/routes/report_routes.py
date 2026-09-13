"""The print artefacts, served from the console.

Rendered as standalone documents rather than as pages inside the shell: a pack
that leaves the building must not depend on the console's stylesheet, its
navigation, or the reader's theme. Everything it needs is inlined, so the file
that is saved is the file that is read.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from prama.backend import compile_for
from prama.core.errors import PramaError
from prama.derive import ControlGenerator
from prama.derive.persisted import dataset_declaration_of
from prama.ir.resolve import resolved
from prama.report.render import Coverage, Provenance, control_pack, declaration_pack
from prama.semantic.services import EstateService
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes
from prama.web.viewmodels import TIER_LABELS

#: Lifecycle states a pack reports on. A retired dataset is deliberately out of
#: scope and deliberately *counted* — an auditor asking "is this everything?"
#: gets a number rather than a shrug.
REPORTED_STATES = ("proposed", "active", "deprecated")


class ReportRoutes(UiRoutes):
    SUBJECT = "report"
    """The pack index and the two packs."""

    def register(self) -> None:
        self.page("/reports", self.report_index, name="report_index")
        self.page("/reports/declarations", self.declaration_pack, name="report_declarations")
        self.page("/reports/controls", self.control_pack, name="report_controls")

    async def report_index(self, request: Request, caller: Caller, uow: Uow) -> Any:
        return render(
            request,
            "reports/index.html",
            declared=await uow.datasets.count_current(caller.tenant_id),
        )

    async def _in_scope(self, caller: Caller, uow: Uow) -> tuple[list[Any], Coverage]:
        versions = await uow.datasets.list_current(caller.tenant_id, limit=5000)
        reported = [v for v in versions if v.lifecycle_state in REPORTED_STATES]
        excluded = len(versions) - len(reported)
        reported.sort(key=lambda v: (v.criticality, v.name.lower()))
        return reported, Coverage(
            included=len(reported),
            excluded=excluded,
            exclusion_reason="retired, and therefore out of scope for this pack",
        )

    def _provenance(self, caller: Caller) -> Provenance:
        return Provenance(tenant_id=caller.tenant_id, generated_by=caller.principal_id or "")

    async def declaration_pack(self, caller: Caller, uow: Uow) -> HTMLResponse:
        """What the business says its data is."""
        reported, coverage = await self._in_scope(caller, uow)
        artefact = declaration_pack(
            provenance=self._provenance(caller),
            coverage=coverage,
            gaps=await EstateService(uow).coverage_gaps(caller.tenant_id),
            datasets=[
                {
                    "name": version.name,
                    "description": version.description or "",
                    "criticality": version.criticality,
                    "tier_label": TIER_LABELS.get(
                        version.criticality, f"Tier {version.criticality}"
                    ),
                    "shape": version.shape,
                    "is_bound": version.is_bound,
                    "has_grain": version.has_grain,
                    "grain_statement": (version.grain_json or {}).get("statement", ""),
                    "grain_attributes": (version.grain_json or {}).get("attributes", []),
                    "owner": version.owner_id or "",
                }
                for version in reported
            ],
        )
        return HTMLResponse(artefact.html)

    async def control_pack(self, caller: Caller, uow: Uow) -> HTMLResponse:
        """Every control, its reason, and the SQL it becomes."""
        reported, _ = await self._in_scope(caller, uow)
        generator = ControlGenerator()
        controls: list[dict[str, Any]] = []
        unsatisfiable: list[dict[str, Any]] = []
        covered: set[str] = set()

        for version in reported:
            attributes = await uow.attributes.for_dataset(
                version.dataset_id, tenant_id=caller.tenant_id
            )
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

        artefact = control_pack(
            provenance=self._provenance(caller),
            controls=controls,
            unsatisfiable=unsatisfiable,
            # The denominator is datasets, not controls: "220 controls" says
            # nothing about how much of the estate they touch, and a pack whose
            # coverage number counts its own contents can never report a gap.
            coverage=Coverage(
                included=len(covered),
                excluded=len(reported) - len(covered),
                exclusion_reason="declared, but nothing could be generated from them",
            ),
        )
        return HTMLResponse(artefact.html)


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
