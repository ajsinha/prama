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

from prama.backend import DIALECTS
from prama.controls.language import catalogue_of, check, compile_source
from prama.core.clock import utc_now
from prama.core.errors import PramaError
from prama.core.provenance import content_hash
from prama.ir.resolve import resolved
from prama.pql import builder
from prama.pql.analysis import LanguageService
from prama.pql.types import Catalogue
from prama.schedule import describe as describe_schedule
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
    SUBJECT = "control"
    WRITE_SCOPE = "control:propose"
    """The studio, and the two endpoints its editor calls."""

    def register(self) -> None:
        self.page("/controls", self.control_list, name="control_list")
        self.page("/controls/studio", self.control_studio, name="control_studio")
        self.page("/controls/build", self.rule_builder, name="rule_builder")
        self.page("/controls/build", self.rule_build, name="rule_build", methods=["POST"])
        # The four language operations. POST, because a control's text does not
        # belong in a query string — but they parse, type-check, lint, complete,
        # explain and compile a string and store nothing. `control:read`, not
        # the class's `control:propose`. QA round 3, Q-66.
        #
        # Deriving a write scope from the HTTP verb made linting a control need
        # the permission to author one, so an `owner` — who holds
        # `control:approve` and deliberately not `control:propose` — could
        # approve a control and not check its text first. Approving what you
        # were not allowed to read is backwards, and the workaround it invites
        # is granting owners `control:propose`, which erases the maker-checker
        # separation the two scopes exist to create.
        self.page(
            "/controls/check",
            self.control_check,
            name="control_check",
            methods=["POST"],
            scope="control:read",
        )
        self.page(
            "/controls/completions",
            self.control_completions,
            name="control_completions",
            methods=["POST"],
            scope="control:read",
        )
        self.page(
            "/controls/hover",
            self.control_hover,
            name="control_hover",
            methods=["POST"],
            scope="control:read",
        )
        self.page(
            "/controls/compile",
            self.control_compile,
            name="control_compile",
            methods=["POST"],
            scope="control:read",
        )
        self.page("/controls/save", self.control_save, name="control_save", methods=["POST"])
        self.page(
            "/controls/{control_id}/activate",
            self.control_activate,
            name="control_activate",
            methods=["POST"],
            # `control:approve`, not the class's `control:propose`. The
            # vocabulary separates authoring a control from activating one
            # precisely so the same person need not do both — that is the
            # maker-checker rule, expressed as a scope. A class-level verb
            # collapsed them and locked an owner, who holds `control:approve`
            # and not `control:propose`, out of the only action their role
            # exists for.
            scope="control:approve",
        )
        self.page(
            "/controls/{control_id}/suppress",
            self.control_suppress,
            name="control_suppress",
            methods=["POST"],
            # `control:approve`, not the class's `control:propose`. The
            # vocabulary separates authoring a control from activating one
            # precisely so the same person need not do both — that is the
            # maker-checker rule, expressed as a scope. A class-level verb
            # collapsed them and locked an owner, who holds `control:approve`
            # and not `control:propose`, out of the only action their role
            # exists for.
            scope="control:approve",
        )

    async def _catalogue(self, caller: Caller, uow: Uow) -> Catalogue:
        """The checker's catalogue, derived from declarations (`catalogue_of`)."""
        return await catalogue_of(uow, caller.tenant_id)

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
        from prama.controls.approval import activate

        try:
            await activate(
                uow,
                control_id,
                tenant_id=caller.tenant_id,
                approver=caller.principal_id,
                reason="accepted",
            )
        except PramaError as exc:
            flash_error_and_log(request, "That control could not be activated", exc)
            return redirect_to(request, "control_list")
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
        result = check(source, await self._catalogue(caller, uow))
        return render(
            request,
            "controls/_findings.html",
            syntax_error=result["syntax_error"],
            findings=result["findings"],
            explanations=result["explanations"],
            error_count=result["errors"],
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
        result = compile_source(source, target)
        return render(
            request,
            "controls/_plans.html",
            syntax_error=result["syntax_error"],
            plans=result["plans"],
            target=target,
        )
