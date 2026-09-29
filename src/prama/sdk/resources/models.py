"""The model gateway's administration: the Models page and ``prama llm``. Needs ``admin``.

Sending a prompt as an ordinary user is ``client.llm.chat``; this namespace is
for whoever configures where models run, which purpose uses which, what they
cost, and for checking the record of every call.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg


@namespace("models")
class Models(Resource):
    """Providers, profiles, templates, prices, budgets, the call ledger, evaluations."""

    # -- providers ---------------------------------------------------------

    @endpoint("GET", "/models/kinds")
    def kinds(self) -> Any:
        """Provider kinds, OpenAI-compatible dialects and hosting classes."""
        return self._get("/models/kinds")

    @endpoint("GET", "/models/providers")
    def providers(self) -> Any:
        """The configured providers. A credential shows only as "reference set"."""
        return self._get("/models/providers")

    @endpoint("POST", "/models/providers")
    def add_provider(
        self,
        name: str,
        *,
        kind: str,
        hosting: str,
        endpoint: str | None = None,
        dialect: str | None = None,
        region: str | None = None,
        credential_ref: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Any:
        """Add a provider. *credential_ref* is a reference (``env://OPENAI_KEY``),
        never the key: a pasted secret is refused, not stored."""
        return self._post(
            "/models/providers",
            body(
                name=name,
                kind=kind,
                hosting=hosting,
                endpoint=endpoint,
                dialect=dialect,
                region=region,
                credential_ref=credential_ref,
                settings=settings,
            ),
        )

    # -- profiles ----------------------------------------------------------

    @endpoint("GET", "/models/profiles")
    def profiles(self) -> Any:
        """Each purpose, its versions, and which is current."""
        return self._get("/models/profiles")

    @endpoint("POST", "/models/profiles")
    def set_profile(
        self,
        purpose: str,
        route: list[str],
        *,
        attempts: int | None = None,
        fallback_across_hosting: bool | None = None,
        note: str | None = None,
    ) -> Any:
        """Point a purpose at ``["provider:model", …]``, tried in order. A new
        version; current at once unless ``llm.eval.gate_activation`` is on."""
        return self._post(
            "/models/profiles",
            body(
                purpose=purpose,
                route=list(route),
                attempts=attempts,
                fallback_across_hosting=fallback_across_hosting,
                note=note,
            ),
        )

    @endpoint("POST", "/models/profiles/{purpose}/activate")
    def activate_profile(self, purpose: str, version: int) -> Any:
        """Make a recorded profile version current (after a passing run, when gated)."""
        return self._post(f"/models/profiles/{seg(purpose)}/activate", {"version": version})

    # -- templates ---------------------------------------------------------

    @endpoint("GET", "/models/templates")
    def templates(self) -> Any:
        """Every prompt template version and its status."""
        return self._get("/models/templates")

    @endpoint("POST", "/models/templates")
    def add_template(self, document: dict[str, Any]) -> Any:
        """Record a template (name, system, body, variables, response_schema) as a draft."""
        return self._post("/models/templates", {"document": document})

    @endpoint("POST", "/models/templates/{name}/versions/{version}/approve")
    def approve_template(self, name: str, version: int) -> Any:
        """Approve a draft and make it current. Not by its author."""
        return self._post(f"/models/templates/{seg(name)}/versions/{seg(version)}/approve")

    # -- prices and budgets ------------------------------------------------

    @endpoint("GET", "/models/prices")
    def prices(self) -> Any:
        """Every dated price per million tokens."""
        return self._get("/models/prices")

    @endpoint("POST", "/models/prices")
    def set_price(
        self,
        provider: str,
        model: str,
        *,
        input_per_million: str | float,
        output_per_million: str | float,
        cached_per_million: str | float | None = None,
        effective_from: str | None = None,
    ) -> Any:
        """Record a dated price in currency units per million tokens."""
        return self._post(
            "/models/prices",
            body(
                provider=provider,
                model=model,
                input_per_million=str(input_per_million),
                output_per_million=str(output_per_million),
                cached_per_million=None if cached_per_million is None else str(cached_per_million),
                effective_from=effective_from,
            ),
        )

    @endpoint("GET", "/models/budgets")
    def budgets(self) -> Any:
        """Each budget and what has been spent against it this period."""
        return self._get("/models/budgets")

    @endpoint("PUT", "/models/budgets")
    def set_budget(
        self,
        *,
        limit: str | float | None = None,
        limit_tokens: int | None = None,
        period: str | None = None,
        action: str | None = None,
        scope_kind: str | None = None,
        scope_id: str | None = None,
    ) -> Any:
        """Set the budget for a scope (the estate by default) and period."""
        return self._put(
            "/models/budgets",
            body(
                limit=None if limit is None else str(limit),
                limit_tokens=limit_tokens,
                period=period,
                action=action,
                scope_kind=scope_kind,
                scope_id=scope_id,
            ),
        )

    # -- the ledger, trying, evaluating -----------------------------------

    @endpoint("GET", "/models/calls")
    def calls(self, *, limit: int = 50) -> Any:
        """Recent model calls, newest first: hashes, tokens, cost; never text."""
        return self._get("/models/calls", limit=limit)

    @endpoint("GET", "/models/calls/verify")
    def verify(self) -> Any:
        """Recompute the call ledger's hash chain: ``{"intact", "checked", "break"}``."""
        return self._get("/models/calls/verify")

    @endpoint("POST", "/models/try")
    def try_model(self, purpose: str, prompt: str, *, system: str | None = None) -> Any:
        """One prompt through a purpose's profile, recorded in the ledger."""
        return self._post("/models/try", body(purpose=purpose, prompt=prompt, system=system))

    @endpoint("POST", "/models/evaluations")
    def evaluate(
        self,
        suite: dict[str, Any],
        *,
        profile_version: int | None = None,
        template_version: int | None = None,
    ) -> Any:
        """Run an evaluation suite (``prama llm eval run``); returns the recorded run."""
        return self._post(
            "/models/evaluations",
            body(suite=suite, profile_version=profile_version, template_version=template_version),
        )

    @endpoint("GET", "/models/evaluations")
    def evaluations(self, *, limit: int = 50) -> Any:
        """Recent evaluation runs, newest first."""
        return self._get("/models/evaluations", limit=limit)

    @endpoint("GET", "/models/evaluations/{run_id}")
    def evaluation(self, run_id: str) -> Any:
        """One evaluation run with its per-case report."""
        return self._get(f"/models/evaluations/{seg(run_id)}")
