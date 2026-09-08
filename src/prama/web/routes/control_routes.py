"""The control studio: write PQL, see what it means, see what will run.

Three answers to three different questions, on one screen, because they are
asked in that order and by different people:

* **check** — is this sound? Type errors and lint findings together.
* **explain** — what does it say, in English? What a data owner approves.
* **compile** — what SQL will run, on which engine, and what will it *not*
  test? What a DBA asks for before granting access.

The last of these is what makes the platform inspectable rather than trusted,
which is why it is on the same screen and not behind an "advanced" toggle. It
includes the incompleteness disclosure: a compiled control whose SQL applies a
screen rather than the exact test says so, because a lower bound reported as a
count is the most dangerous number this system can produce.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.backend import DIALECTS, compile_for
from prama.core.errors import PramaError
from prama.ir import lower
from prama.pql import parse
from prama.pql.errors import PqlError
from prama.pql.lint import Linter
from prama.pql.types import Catalogue, Column, DatasetSchema, TypeChecker
from prama.web.deps import Caller, Uow
from prama.web.rendering import render
from prama.web.routes.base import UiRoutes

STARTER = """CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date)
  SEVERITY critical
  DIMENSION uniqueness
  BECAUSE 'one position per account per instrument per business day'
"""


class ControlRoutes(UiRoutes):
    """The studio, and the two endpoints its editor calls."""

    def register(self) -> None:
        self.page("/controls", self.control_studio, name="control_studio")
        self.page("/controls/check", self.control_check, name="control_check", methods=["POST"])
        self.page(
            "/controls/compile", self.control_compile, name="control_compile", methods=["POST"]
        )

    async def _catalogue(self, caller: Caller, uow: Uow) -> Catalogue:
        """The checker's catalogue, derived from declarations.

        Derived, never restated: what the editor checks against is what the
        business declared. A separately maintained catalogue would drift, and
        the drift would surface as a control that checks clean and then fails
        at execution — the worst possible place to find it.
        """
        catalogue = Catalogue()
        for version in await uow.datasets.list_current(caller.tenant_id, limit=5000):
            attributes = await uow.attributes.for_dataset(version.dataset_id)
            catalogue = catalogue.with_dataset(
                DatasetSchema(
                    name=version.slug,
                    columns=tuple(
                        Column(a.name, getattr(a, "physical_type", "") or "") for a in attributes
                    ),
                )
            )
        return catalogue

    async def control_studio(self, request: Request, caller: Caller, uow: Uow) -> Any:
        datasets = await uow.datasets.list_current(caller.tenant_id, limit=5000)
        return render(
            request,
            "controls/studio.html",
            starter=STARTER,
            dataset_slugs=sorted(v.slug for v in datasets),
            dialects=sorted(DIALECTS),
        )

    async def control_check(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        source: Annotated[str, Form()] = "",
    ) -> Any:
        """Parse, type-check, lint and explain. Returns a fragment."""
        catalogue = await self._catalogue(caller, uow)
        try:
            program = parse(source)
        except PqlError as exc:
            return render(
                request,
                "controls/_findings.html",
                syntax_error=_position_of(exc),
                findings=[],
                explanations=[],
                error_count=1,
            )

        checker = TypeChecker(catalogue)
        linter = Linter()
        findings: list[dict[str, Any]] = []
        # An undeclared dataset is one fact about the estate, not one per
        # control. Saying it once per control buries the findings that really
        # are about a control.
        already_said: set[str] = set()
        for index, control in enumerate(program.controls):
            label = control.name or f"control {index + 1}"
            for finding in checker.check(control, source=source):
                if finding.message in already_said:
                    continue
                already_said.add(finding.message)
                findings.append({**finding.to_dict(), "control": label})
            for lint_finding in linter.check(control):
                findings.append(
                    {
                        "level": "warning",
                        "message": lint_finding.message,
                        "remedy": getattr(lint_finding, "remedy", ""),
                        "control": label,
                        "position": None,
                    }
                )
        return render(
            request,
            "controls/_findings.html",
            syntax_error=None,
            findings=findings,
            explanations=_explanations(program.controls),
            error_count=sum(1 for f in findings if f["level"] == "error"),
        )

    async def control_compile(
        self,
        request: Request,
        source: Annotated[str, Form()] = "",
        # The backend's own name for the dialect, not the configuration key
        # ("postgres"). The studio's select is populated from DIALECTS, so the
        # two only diverge on a hand-made request — and then it fails loudly
        # with the list of real names rather than compiling for the wrong one.
        target: Annotated[str, Form()] = "postgresql",
    ) -> Any:
        """The SQL, its plan id, and what it does not test."""
        try:
            program = parse(source)
        except PqlError as exc:
            return render(
                request,
                "controls/_plans.html",
                syntax_error=_position_of(exc),
                plans=[],
                target=target,
            )

        plans: list[dict[str, Any]] = []
        for index, control in enumerate(program.controls):
            label = control.name or f"control {index + 1}"
            try:
                plan = lower(control)
                compiled = compile_for(plan, target)
            except PramaError as exc:
                # Named, not swallowed. "This dialect cannot express this
                # control" is a real answer and a useful one; a blank panel is
                # not, and a silently omitted control is a lie.
                plans.append({"name": label, "error": str(exc)})
                continue
            plans.append(
                {
                    "name": label,
                    "plan_id": plan.plan_id,
                    "description": plan.description,
                    "metric_query": compiled.metric_query,
                    "sample_query": compiled.sample_query,
                    "metric_names": list(compiled.metric_names),
                    "parameters": list(compiled.parameters),
                    "is_complete": compiled.is_complete,
                    # The residual: what SQL screened but did not decide. A
                    # pass reported from an incomplete screen is a false
                    # assurance, and this is where the reader is told.
                    "residual_validators": [
                        {"validator": v, "column": c} for v, c in compiled.residual_validators
                    ],
                }
            )
        return render(
            request, "controls/_plans.html", syntax_error=None, plans=plans, target=target
        )


def _position_of(exc: PqlError) -> dict[str, Any]:
    """A syntax error the editor can point at.

    Line and column, or nothing — never a guess. CodeMirror will happily
    underline line 1 column 1 and send the reader to the wrong place, which is
    worse than underlining nothing at all.
    """
    position = getattr(exc, "position", None)
    return {
        "message": str(exc),
        "remedy": getattr(exc, "remedy", ""),
        "line": getattr(position, "line", None),
        "column": getattr(position, "column", None),
    }


def _explanations(controls: Any) -> list[dict[str, str]]:
    """Each control as the sentence a data owner approves.

    Taken from the lowered plan's ``description``, which is generated from the
    IR — so the sentence is derived from the same structure the SQL is derived
    from, and the two cannot describe different controls. Writing a second
    English renderer here is how a UI ends up explaining one thing and running
    another.
    """
    out = []
    for index, control in enumerate(controls):
        label = control.name or f"control {index + 1}"
        try:
            out.append({"name": label, "sentence": lower(control).description})
        except PramaError as exc:
            out.append({"name": label, "sentence": f"cannot be explained: {exc}"})
    return out
