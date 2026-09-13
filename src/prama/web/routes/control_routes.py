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
from fastapi.responses import JSONResponse

from prama.backend import DIALECTS, compile_for
from prama.core.clock import utc_now
from prama.core.errors import PramaError
from prama.core.provenance import content_hash
from prama.ir.resolve import resolved
from prama.pql import parse
from prama.pql.analysis import LanguageService
from prama.pql.errors import PqlError
from prama.pql.types import Catalogue, Column, DatasetSchema
from prama.schedule import describe as describe_schedule
from prama.web import builder
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes
from prama.web.routes.preview_routes import MAX_PERIODS

STARTER = """CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date)
  SEVERITY critical
  DIMENSION uniqueness
  BECAUSE 'one position per account per instrument per business day'
"""


class ControlRoutes(UiRoutes):
    """The studio, and the two endpoints its editor calls."""

    def register(self) -> None:
        self.page("/controls", self.control_list, name="control_list")
        self.page("/controls/studio", self.control_studio, name="control_studio")
        self.page("/controls/build", self.rule_builder, name="rule_builder")
        self.page("/controls/build", self.rule_build, name="rule_build", methods=["POST"])
        self.page("/controls/check", self.control_check, name="control_check", methods=["POST"])
        self.page(
            "/controls/completions",
            self.control_completions,
            name="control_completions",
            methods=["POST"],
        )
        self.page("/controls/hover", self.control_hover, name="control_hover", methods=["POST"])
        self.page(
            "/controls/compile", self.control_compile, name="control_compile", methods=["POST"]
        )
        self.page("/controls/save", self.control_save, name="control_save", methods=["POST"])
        self.page(
            "/controls/{control_id}/activate",
            self.control_activate,
            name="control_activate",
            methods=["POST"],
        )
        self.page(
            "/controls/{control_id}/suppress",
            self.control_suppress,
            name="control_suppress",
            methods=["POST"],
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
            attributes = await uow.attributes.for_dataset(
                version.dataset_id, tenant_id=caller.tenant_id
            )
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
        config = request.app.state.config
        return render(
            request,
            "controls/studio.html",
            starter=STARTER,
            dataset_slugs=sorted(v.slug for v in datasets),
            dialects=sorted(DIALECTS),
            # Whether this deployment can run a control at all. The backtest
            # panel is hidden rather than shown-and-broken when it cannot: a
            # button that always fails teaches people the screen is unreliable.
            preview_configured=bool(config.get_str("web.preview.source", "")),
            backtest_days=config.get_int("web.preview.backtest_days", 30),
            max_periods=MAX_PERIODS,
        )

    async def control_list(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """The estate of controls, grouped by whether they actually run.

        The grouping is the point. "We have 340 controls" is the number every
        tool of this kind reports; how many of them are proposals nobody has
        accepted, and how many were silenced during an incident and never
        turned back on, is the number that decides whether the estate is
        protected.
        """
        live = await uow.controls.live(caller.tenant_id)
        proposed = await uow.controls.of_status(caller.tenant_id, "proposed")
        suppressed = await uow.controls.of_status(caller.tenant_id, "suppressed")
        overdue = await uow.controls.silenced_past_expiry(caller.tenant_id, utc_now().isoformat())
        # Rendered through the parser rather than printed raw, so a schedule
        # that cannot be read shows as unreadable on the page instead of
        # looking fine and never firing.
        schedules = {
            str(version.control_id): describe_schedule(version.schedule)
            for version in (*live, *proposed, *suppressed)
        }
        return render(
            request,
            "controls/list.html",
            live=live,
            proposed=proposed,
            suppressed=suppressed,
            schedules=schedules,
            unreadable={
                control_id
                for control_id, text in schedules.items()
                if text.startswith("unreadable")
            },
            overdue={str(version.control_id) for version in overdue},
            retired=len(await uow.controls.of_status(caller.tenant_id, "retired")),
        )

    async def control_save(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        pql: Annotated[str, Form()],
        identity: Annotated[str, Form()] = "",
    ) -> Any:
        """Save a hand-written control into the estate.

        Authored controls get an identity derived from their text when none is
        supplied, which is the honest fallback: a person editing their own
        control in the studio and saving it again means to replace it, and an
        identity derived from the text cannot know that. So the studio passes
        the identity back when it has one, and a genuinely new control gets a
        new one.
        """
        try:
            control, _ = await uow.controls.declare(
                tenant_id=caller.tenant_id,
                identity=identity or content_hash(pql),
                pql=pql,
                origin="declaration",
                rule="authored",
                status="proposed",
                authored_by=caller.principal_id,
                reason="written in the studio",
            )
        except PramaError as exc:
            flash_error_and_log(request, "That control could not be saved", exc)
            return redirect_to(request, "control_studio")
        return redirect_to(
            request,
            "control_list",
            flash_message=(
                f"Saved as a proposal. Accept it on this page to start running it "
                f"({control.identity[:12]}…)."
            ),
        )

    async def control_activate(
        self, request: Request, control_id: str, caller: Caller, uow: Uow
    ) -> Any:
        await uow.controls.activate(
            control_id,
            tenant_id=caller.tenant_id,
            approved_by=caller.principal_id or "console",
            reason="accepted",
        )
        return redirect_to(request, "control_list", flash_message="The control is now running.")

    async def control_suppress(
        self,
        request: Request,
        control_id: str,
        caller: Caller,
        uow: Uow,
        until: Annotated[str, Form()] = "",
        because: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            await uow.controls.suppress(
                control_id,
                tenant_id=caller.tenant_id,
                until=until,
                because=because,
                by=caller.principal_id,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That control could not be suppressed", exc)
        return redirect_to(request, "control_list")

    async def rule_builder(self, request: Request, caller: Caller, uow: Uow) -> Any:
        """The form a person who will never write PQL uses."""
        versions = await uow.datasets.list_current(caller.tenant_id, limit=5000)
        return render(
            request,
            "controls/builder.html",
            questions=builder.QUESTIONS,
            datasets=sorted(v.slug for v in versions),
            columns={
                v.slug: [
                    a.name
                    for a in await uow.attributes.for_dataset(
                        v.dataset_id, tenant_id=caller.tenant_id
                    )
                ]
                for v in versions
            },
            submitted={},
        )

    async def rule_build(self, request: Request) -> Any:
        # No caller and no unit of work: the builder composes an AST and
        # renders it, and touches nothing tenant-scoped. Taking them anyway
        # would open a transaction per keystroke-driven rebuild for nothing.
        """Assemble, verify the round trip, and show the PQL.

        Always shows it. A builder that hides its output produces controls
        nobody reviews, and a control nobody reviews is one nobody trusts when
        it fires.
        """
        form = dict(await request.form())
        answers = {key: str(value) for key, value in form.items()}
        try:
            control = builder.build(
                dataset=answers.get("dataset", ""),
                rule=answers.get("rule", ""),
                severity=answers.get("severity", "major"),
                because=answers.get("because", ""),
                column=answers.get("column", ""),
                columns=answers.get("columns", ""),
                values=answers.get("values", ""),
                pattern=answers.get("pattern", ""),
                lower=answers.get("lower", ""),
                upper=answers.get("upper", ""),
                minimum=answers.get("minimum", ""),
                maximum=answers.get("maximum", ""),
                reference_dataset=answers.get("reference_dataset", ""),
                reference_column=answers.get("reference_column", ""),
                tolerance_minutes=answers.get("tolerance_minutes", "0"),
                due_time=answers.get("due_time", ""),
                calendar=answers.get("calendar", ""),
                tolerated_percent=answers.get("tolerated_percent", ""),
                unknown_is_violation=answers.get("unknown_is_violation", "1") == "1",
            )
            pql = builder.render_and_verify(control)
        except PramaError as exc:
            return render(
                request,
                "controls/_built.html",
                error={"message": str(exc), "remedy": getattr(exc, "remedy", "")},
                pql="",
                sentence="",
            )
        return render(
            request,
            "controls/_built.html",
            error=None,
            pql=pql,
            sentence=resolved(control).description,
        )

    async def control_check(
        self,
        request: Request,
        caller: Caller,
        uow: Uow,
        source: Annotated[str, Form()] = "",
    ) -> Any:
        """Parse, type-check, lint and explain. Returns a fragment.

        Every judgement comes from ``LanguageService``, which is the same module
        ``prama lsp`` calls. Two implementations of "is this column real" is how
        an editor comes to underline something the compiler accepts, and the
        first time that happens people stop reading the underlines.
        """
        service = LanguageService(await self._catalogue(caller, uow))
        diagnostics = service.diagnostics(source)
        syntax = next((d for d in diagnostics if d.level == "error" and not d.control), None)
        if syntax is not None:
            # A text that will not parse has one finding and no controls; the
            # panel says so rather than listing an empty result beside it.
            return render(
                request,
                "controls/_findings.html",
                syntax_error=syntax.to_dict(),
                findings=[],
                explanations=[],
                error_count=1,
            )
        return render(
            request,
            "controls/_findings.html",
            syntax_error=None,
            findings=[d.to_dict() for d in diagnostics],
            # Explained here rather than by the language service: explaining
            # means lowering, and the language layer may not depend on the
            # lowerer. The console already compiles a control on this screen.
            explanations=_explanations(parse(source).controls),
            error_count=sum(1 for d in diagnostics if d.level == "error"),
        )

    async def control_completions(
        self,
        caller: Caller,
        uow: Uow,
        source: Annotated[str, Form()] = "",
        line: Annotated[int, Form()] = 1,
        column: Annotated[int, Form()] = 1,
    ) -> Any:
        """What may legitimately be typed here. JSON, for the editor.

        Never a name the estate cannot satisfy: a suggestion nobody can honour
        is worse than none, because it gets accepted.
        """
        service = LanguageService(await self._catalogue(caller, uow))
        return JSONResponse(
            {"items": [c.to_dict() for c in service.completions(source, line, column)]}
        )

    async def control_hover(
        self,
        caller: Caller,
        uow: Uow,
        source: Annotated[str, Form()] = "",
        line: Annotated[int, Form()] = 1,
        column: Annotated[int, Form()] = 1,
    ) -> Any:
        """What the name under the cursor means, from the estate's own words."""
        service = LanguageService(await self._catalogue(caller, uow))
        return JSONResponse(service.hover(source, line, column).to_dict())

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
                plan = resolved(control)
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
            out.append({"name": label, "sentence": resolved(control).description})
        except PramaError as exc:
            out.append({"name": label, "sentence": f"cannot be explained: {exc}"})
    return out
