"""The gateway: every model call goes through here, by purpose, and is recorded.

A caller asks for a *purpose* ("author", "explain"), not a model. The purpose's
profile names an ordered route of provider and model; the gateway tries them in
order, retries a failed attempt on the same candidate, falls back to the next,
and records one hash-chained call row whatever happened. `ProfileProvider` makes
the gateway look like any other `ModelProvider`, so the assistant and the
inducer use profiles without changing their code.

Two rules shape the fallback:

* **Policy refusals are not failures to retry.** A hosted provider refusing
  PII is the residency rule working; the gateway moves on to a candidate that
  may receive it (a self-hosted one), and records the refusal if none may.
* **Fallback never becomes less local** unless the profile says so. A route
  that starts self-hosted must not quietly end at a vendor because the local
  server was busy.

Free of `prama.db`: the route arrives already resolved, and records leave
through the `CallLedger` port, which the database package implements.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import hashlib
import json
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from prama.core import pjson
from prama.core.errors import PramaError, ValidationError
from prama.llm.spi import Hosting, ModelProvider, Request, Response

#: How local each hosting class is; fallback may only move to an equal or
#: lower number unless a profile allows otherwise.
LOCALITY: dict[Hosting, int] = {Hosting.SELF_HOSTED: 0, Hosting.TENANT: 1, Hosting.HOSTED: 2}

GENESIS = "0" * 64


@dataclasses.dataclass(frozen=True, slots=True)
class Candidate:
    """One step of a route: a built provider and what it is."""

    provider: ModelProvider
    provider_id: str
    provider_name: str
    kind: str
    hosting: Hosting
    model: str


@dataclasses.dataclass(frozen=True, slots=True)
class Route:
    """A profile version, resolved: the candidates to try, in order."""

    purpose: str
    candidates: tuple[Candidate, ...]
    profile_id: str = ""
    version: int | None = None
    max_attempts: int = 2
    fallback_across_hosting: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class CallRecord:
    """What one gateway call did. Hashes of the prompt and answer, never text."""

    tenant_id: str
    surface: str
    purpose: str
    sensitivity: str
    request_fingerprint: str
    prompt_hash: str
    started_at: str
    finished_at: str
    outcome: str
    principal_id: str | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    provider_id: str | None = None
    provider_kind: str = ""
    hosting: str = ""
    model_requested: str = ""
    model_reported: str = ""
    response_hash: str = ""
    temperature: float = 0.0
    seed: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1
    fallback_from: str | None = None
    grammar_enforced: bool = False
    outcome_detail: str = ""
    api_key_id: str | None = None
    #: Set when the record is persisted, from the dated price row: the
    #: gateway does not know prices, the store does.
    cost_micros: int = 0
    price_model_id: str | None = None
    served_from: str = "provider"
    #: Which template version produced the prompt, and the digest of the stored
    #: payload when `llm.audit.payloads` keeps one. Left out of the sealed
    #: content when empty, so records written before these fields existed still
    #: hash to what they were sealed as.
    template_id: str | None = None
    template_version: int | None = None
    payload_digest: str | None = None

    def content(self) -> dict[str, Any]:
        content = dataclasses.asdict(self)
        for late in ("template_id", "template_version", "payload_digest"):
            if content[late] is None:
                del content[late]
        return content


def seal(record: CallRecord, *, sequence: int, previous_hash: str) -> str:
    """The record's hash, chained to the one before it."""
    body = pjson.canonical({"sequence": sequence, "previous": previous_hash, **record.content()})
    return hashlib.sha256(body).hexdigest()


class CallLedger(abc.ABC):
    """Where call records go. The database package implements this."""

    @abc.abstractmethod
    def append(self, record: CallRecord) -> None: ...


class MemoryLedger(CallLedger):
    """Records held in memory, for callers that persist them afterwards."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []
        #: digest -> (request JSON, response JSON, mode), for `llm_payload`.
        self.payloads: dict[str, tuple[str, str, str]] = {}
        #: How long a stored payload is kept (`llm.audit.payload_retention_days`).
        self.retention_days = 30

    def append(self, record: CallRecord) -> None:
        self.records.append(record)


class ResponseCache:
    """Answers to deterministic requests, bounded, least recently used first out.

    Only temperature-zero requests are cached, since those are the ones asked
    to give the same answer twice. A cached answer is served only after the
    candidate's policy checks pass, so it is never an oracle for a request that
    would now be refused.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        import collections

        self._entries: collections.OrderedDict[str, Response] = collections.OrderedDict()
        self._max = max_entries

    @staticmethod
    def key(tenant: str, route: Route, candidate: Candidate, request: Request) -> str:
        return "|".join(
            (
                tenant,
                request.fingerprint,
                candidate.provider_id,
                candidate.model,
                str(route.version),
            )
        )

    def get(self, key: str) -> Response | None:
        found = self._entries.get(key)
        if found is not None:
            self._entries.move_to_end(key)
        return found

    def put(self, key: str, response: Response) -> None:
        self._entries[key] = response
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LlmGateway:
    """Runs a request for a purpose along its route, and records the call."""

    def __init__(
        self,
        routes: Mapping[str, Route],
        ledger: CallLedger,
        *,
        tenant_id: str,
        surface: str,
        principal_id: str | None = None,
        api_key_id: str | None = None,
        cache: ResponseCache | None = None,
        payloads: str = "none",
    ) -> None:
        #: `none`, `redacted` or `full`: what of each exchange is kept.
        self._payloads = payloads
        self._routes = routes
        self._api_key = api_key_id
        self._cache = cache
        self._ledger = ledger
        self._tenant = tenant_id
        self._surface = surface
        self._principal = principal_id

    def _route(self, purpose: str) -> Route:
        """The purpose's profile, or the mock model when none is configured.

        It used to raise, so every caller needed its own "no model" branch and
        the unconfigured case looked like a failure. The mock answers with no
        text and says why, which is the path every feature already has for a
        model that returned nothing.
        """
        route = self._routes.get(purpose)
        if route is not None and route.candidates:
            return route
        from prama.llm.providers import MockProvider

        mock = Candidate(
            provider=MockProvider(purpose),
            provider_id="",
            provider_name="mock",
            kind="mock",
            hosting=Hosting.SELF_HOSTED,
            model="mock",
        )
        return Route(purpose=purpose, candidates=(mock,), max_attempts=1)

    def embed(
        self, purpose: str, texts: list[str], *, sensitivity: Any = None
    ) -> tuple[list[list[float]], str] | None:
        """Vectors for *texts* from the first candidate of *purpose* that can embed,
        with the model that made them; None when no candidate can.

        The mock route (no profile) cannot embed, so an unconfigured purpose
        returns None and the caller uses its non-model ranking.
        """
        from prama.semantic.values import Sensitivity

        route = self._route(purpose)
        level = sensitivity or Sensitivity.INTERNAL
        probe = Request(system="", prompt="\n".join(texts), sensitivity=level)
        started, clock = _now(), time.monotonic()
        base = {
            "tenant_id": self._tenant,
            "surface": self._surface,
            "purpose": purpose,
            "sensitivity": level.value,
            "request_fingerprint": probe.fingerprint,
            "prompt_hash": _hash(probe.prompt),
            "principal_id": self._principal,
            "api_key_id": self._api_key,
            "profile_id": route.profile_id or None,
            "profile_version": route.version,
            "temperature": 0.0,
            "seed": None,
        }
        for candidate in route.candidates:
            try:
                vectors = candidate.provider.embed(texts, sensitivity=level)
            except PramaError as exc:
                self._record(
                    base, started, clock, candidate, None, 1, None, "refused_policy", str(exc)
                )
                continue
            except Exception as exc:  # a provider that fails is a finding, and the next is tried
                self._record(base, started, clock, candidate, None, 1, None, "error", str(exc))
                continue
            if vectors is None:
                continue
            reply = Response(
                text="",
                model=candidate.model,
                provider=candidate.kind,
                request_fingerprint=probe.fingerprint,
            )
            self._record(base, started, clock, candidate, reply, 1, None, "ok")
            return vectors, candidate.model
        return None

    def run(self, purpose: str, request: Request) -> Response:
        route = self._route(purpose)
        started, clock = _now(), time.monotonic()
        base = {
            "tenant_id": self._tenant,
            "surface": self._surface,
            "purpose": purpose,
            "sensitivity": request.sensitivity.value,
            "request_fingerprint": request.fingerprint,
            "prompt_hash": _hash(request.system + "\x1f" + request.prompt),
            "principal_id": self._principal,
            "api_key_id": self._api_key,
            "profile_id": route.profile_id or None,
            "profile_version": route.version,
            "temperature": request.temperature,
            "seed": request.seed,
            **_template_of(request),
            "_request": request,
        }
        first_locality = LOCALITY[route.candidates[0].hosting]
        attempts, previous, refusal, failure = 0, None, None, None
        for candidate in route.candidates:
            if LOCALITY[candidate.hosting] > first_locality and not route.fallback_across_hosting:
                continue
            cacheable = self._cache is not None and request.temperature == 0
            if cacheable:
                try:
                    # Policy first: a cached answer must not reach a request
                    # this candidate would now refuse.
                    candidate.provider.permit(request)
                    candidate.provider.permit_residency(request)
                except PramaError as exc:
                    refusal = exc
                    previous = candidate
                    continue
                key = ResponseCache.key(self._tenant, route, candidate, request)
                hit = self._cache.get(key) if self._cache else None
                if hit is not None:
                    self._record(
                        base,
                        started,
                        clock,
                        candidate,
                        hit,
                        attempts,
                        previous,
                        "ok",
                        served_from="cache",
                    )
                    return hit
            for _ in range(max(1, route.max_attempts)):
                attempts += 1
                try:
                    response = candidate.provider.ask(request)
                except PramaError as exc:
                    # The residency or sensitivity rule refusing this candidate:
                    # not retried, but another candidate may be allowed.
                    refusal = exc
                    break
                if response.text or not response.incomplete:
                    if cacheable and self._cache is not None and response.text:
                        self._cache.put(key, response)
                    self._record(
                        base, started, clock, candidate, response, attempts, previous, "ok"
                    )
                    return response
                failure = response
            previous = candidate
        if failure is not None:
            self._record(
                base,
                started,
                clock,
                previous,
                failure,
                attempts,
                None,
                "error",
                failure.incomplete,
            )
            return failure
        detail = str(refusal) if refusal else "no candidate is allowed by the profile"
        self._record(base, started, clock, None, None, attempts, None, "refused_policy", detail)
        if refusal is not None:
            raise refusal
        raise ValidationError(detail, remedy="Check the profile's route and its hosting.")

    def run_stream(self, purpose: str, request: Request) -> Iterator[str]:
        """Stream the answer from the first candidate the policy allows.

        No fallback once tokens have gone out: half an answer cannot be taken
        back, so the choice of candidate is made before the first token. The
        call is recorded when the stream ends, however it ends.
        """
        route = self._route(purpose)
        started, clock = _now(), time.monotonic()
        base = {
            "tenant_id": self._tenant,
            "surface": self._surface,
            "purpose": purpose,
            "sensitivity": request.sensitivity.value,
            "request_fingerprint": request.fingerprint,
            "prompt_hash": _hash(request.system + "\x1f" + request.prompt),
            "principal_id": self._principal,
            "api_key_id": self._api_key,
            "profile_id": route.profile_id or None,
            "profile_version": route.version,
            "temperature": request.temperature,
            "seed": request.seed,
            **_template_of(request),
            "_request": request,
        }
        first_locality = LOCALITY[route.candidates[0].hosting]
        refusal: PramaError | None = None
        for candidate in route.candidates:
            if LOCALITY[candidate.hosting] > first_locality and not route.fallback_across_hosting:
                continue
            try:
                candidate.provider.permit(request)
                candidate.provider.permit_residency(request)
            except PramaError as exc:
                refusal = exc
                continue
            pieces: list[str] = []
            outcome, detail = "ok", ""
            try:
                for piece in candidate.provider.ask_stream(request):
                    pieces.append(piece)
                    yield piece
            except Exception as exc:
                outcome, detail = "error", f"{type(exc).__name__}: {exc}"
                raise
            finally:
                text = "".join(pieces)
                done = Response(text, candidate.model, candidate.provider_name, request.fingerprint)
                self._record(base, started, clock, candidate, done, 1, None, outcome, detail)
            return
        detail = str(refusal) if refusal else "no candidate is allowed by the profile"
        self._record(base, started, clock, None, None, 0, None, "refused_policy", detail)
        if refusal is not None:
            raise refusal
        raise ValidationError(detail, remedy="Check the profile's route and its hosting.")

    def _keep(self, request: Request, response: Response) -> str:
        """Store the exchange per policy; return its digest. Redacted unless `full`."""
        from prama.llm.redact import redact

        full = self._payloads == "full"
        sent = request if full else ModelProvider.withhold(request)
        asked = json.dumps({"system": sent.system, "prompt": sent.prompt}, sort_keys=True)
        answered = json.dumps({"text": response.text if full else redact(response.text)})
        digest = hashlib.sha256((asked + "\n" + answered).encode("utf-8")).hexdigest()
        if isinstance(self._ledger, MemoryLedger):
            self._ledger.payloads[digest] = (asked, answered, "full" if full else "redacted")
        return digest

    def _record(
        self,
        base: dict[str, Any],
        started: str,
        clock: float,
        candidate: Candidate | None,
        response: Response | None,
        attempts: int,
        fell_from: Candidate | None,
        outcome: str,
        detail: str = "",
        *,
        served_from: str = "provider",
    ) -> None:
        base = dict(base)
        request = base.pop("_request", None)
        extra: dict[str, Any] = {}
        if response is not None and request is not None and self._payloads != "none":
            extra["payload_digest"] = self._keep(request, response)
        if candidate is not None:
            extra |= {
                "provider_id": candidate.provider_id or None,
                "provider_kind": candidate.kind,
                "hosting": candidate.hosting.value,
                "model_requested": candidate.model,
            }
        if response is not None:
            extra |= {
                "model_reported": response.model,
                "response_hash": _hash(response.text) if response.text else "",
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "grammar_enforced": response.grammar_enforced,
            }
        self._ledger.append(
            CallRecord(
                **base,
                **extra,
                started_at=started,
                finished_at=_now(),
                latency_ms=int((time.monotonic() - clock) * 1000),
                attempts=attempts,
                fallback_from=fell_from.provider_id if fell_from else None,
                outcome=outcome,
                outcome_detail=detail[:1000],
                served_from=served_from,
            )
        )


def _template_of(request: Request) -> dict[str, Any]:
    template = request.context.get("template_id")
    version = request.context.get("template_version")
    if not template:
        return {}
    return {"template_id": template, "template_version": int(version) if version else None}


class ProfileProvider(ModelProvider):
    """The gateway, for one purpose, as a `ModelProvider`.

    The assistant and the inducer take a provider; handing them this switches
    them to profiles, fallback and the call ledger without changing either.
    The checks `ModelProvider.ask` performs are done per candidate inside the
    gateway, so this delegates rather than repeating them against a hosting
    class it does not have.
    """

    name: ClassVar[str] = "profile"
    hosting: ClassVar[Hosting] = Hosting.SELF_HOSTED

    def __init__(self, gateway: LlmGateway, purpose: str) -> None:
        self._gateway = gateway
        self.purpose = purpose

    def ask(self, request: Request) -> Response:
        return self._gateway.run(self.purpose, request)

    def complete(self, request: Request) -> Response:
        return self._gateway.run(self.purpose, request)
