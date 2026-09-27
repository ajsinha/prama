"""The Models page: providers, profiles, a prompt tester, and the call ledger.

Everything here is administration, so every route needs the ``admin`` scope.
Nothing on the page shows a secret: a provider carries a secret *reference*
(``env://…``, ``vault://…``), resolved only when a call is made.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Form, Request

from prama.core.errors import PramaError
from prama.llm.kinds import DIALECTS, KINDS, ProviderSpec, build
from prama.llm.spi import Request as ModelRequest
from prama.llm.wiring import gateway_for, persist
from prama.web.deps import Caller, Uow
from prama.web.rendering import flash_error_and_log, redirect_to, render
from prama.web.routes.base import UiRoutes

ADMIN = "admin"
HOSTINGS = ("self_hosted", "tenant", "hosted")


class LlmRoutes(UiRoutes):
    """Model providers and profiles, for an administrator."""

    SUBJECT = "admin"

    def register(self) -> None:
        post = ["POST"]
        self.page("/models", self.index, name="models", scope=ADMIN)
        self.page(
            "/models/providers",
            self.add_provider,
            name="models_provider_add",
            methods=post,
            scope=ADMIN,
        )
        self.page(
            "/models/profiles",
            self.set_profile,
            name="models_profile_set",
            methods=post,
            scope=ADMIN,
        )
        self.page("/models/try", self.try_prompt, name="models_try", methods=post, scope=ADMIN)

    async def _context(self, uow: Any, tenant: str) -> dict[str, Any]:
        providers = await uow.llm.providers(tenant)
        names = {p.id: p.name for p in providers}
        profiles = []
        for profile in await uow.llm.profiles(tenant):
            current = await uow.llm.current(tenant, profile.purpose)
            if current is not None:
                version = current[1]
                profiles.append(
                    {
                        "purpose": profile.purpose,
                        "version": version.version,
                        "route": [(names.get(r.provider_id, "?"), r.model) for r in version.routes],
                        "fallback_across_hosting": version.fallback_across_hosting,
                    }
                )
        return {
            "providers": providers,
            "profiles": profiles,
            "calls": await uow.llm.calls(tenant, limit=25),
            "kinds": KINDS,
            "dialects": sorted(DIALECTS),
            "hostings": HOSTINGS,
        }

    async def index(self, request: Request, uow: Uow, caller: Caller) -> Any:
        return render(
            request, "llm/index.html", answer=None, **await self._context(uow, caller.tenant_id)
        )

    async def add_provider(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        name: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "",
        hosting: Annotated[str, Form()] = "",
        endpoint: Annotated[str, Form()] = "",
        dialect: Annotated[str, Form()] = "",
        region: Annotated[str, Form()] = "",
        credential_ref: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            spec = ProviderSpec(
                name=name.strip(),
                kind=kind,
                hosting=hosting,
                endpoint=endpoint.strip(),
                dialect=dialect,
                region=region.strip(),
            )
            build(spec, model="probe")  # refuse now what could never be used
            await uow.llm.add_provider(
                caller.tenant_id,
                name=spec.name,
                kind=kind,
                hosting=hosting,
                endpoint=spec.endpoint,
                dialect=dialect,
                region=spec.region,
                credential_ref=credential_ref.strip() or None,
                by=caller.principal_id,
            )
            await uow.flush()
        except PramaError as exc:
            flash_error_and_log(request, "That provider could not be added", exc)
            return redirect_to(request, "models")
        return redirect_to(request, "models", flash_message=f"Provider {name} added.")

    async def set_profile(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        purpose: Annotated[str, Form()] = "",
        route: Annotated[str, Form()] = "",
        fallback_across_hosting: Annotated[str, Form()] = "",
    ) -> Any:
        try:
            steps = []
            for line in route.splitlines():
                provider, _, model = line.strip().partition(":")
                if provider and model:
                    steps.append((provider.strip(), model.strip()))
            version = await uow.llm.set_profile(
                caller.tenant_id,
                purpose.strip(),
                steps,
                fallback_across_hosting=bool(fallback_across_hosting),
                by=caller.principal_id,
            )
        except PramaError as exc:
            flash_error_and_log(request, "That profile could not be saved", exc)
            return redirect_to(request, "models")
        return redirect_to(
            request, "models", flash_message=f"{purpose}: version {version.version} is now current."
        )

    async def try_prompt(
        self,
        request: Request,
        uow: Uow,
        caller: Caller,
        purpose: Annotated[str, Form()] = "",
        prompt: Annotated[str, Form()] = "",
    ) -> Any:
        offline = request.app.state.config.get_bool("llm.offline", False)
        answer: dict[str, Any]
        try:
            gateway, ledger = await gateway_for(
                uow,
                caller.tenant_id,
                surface="console",
                principal_id=caller.principal_id,
                offline=offline,
            )
            try:
                response = gateway.run(
                    purpose, ModelRequest(system="You are a careful assistant.", prompt=prompt)
                )
                answer = {
                    "text": response.text,
                    "incomplete": response.incomplete,
                    "provider": response.provider,
                    "model": response.model,
                }
            finally:
                await persist(uow, caller.tenant_id, ledger)
        except PramaError as exc:
            answer = {"text": "", "incomplete": str(exc), "provider": "", "model": ""}
        return render(
            request,
            "llm/index.html",
            answer=answer,
            asked=prompt,
            asked_purpose=purpose,
            **await self._context(uow, caller.tenant_id),
        )
