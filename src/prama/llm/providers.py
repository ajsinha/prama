"""Concrete model providers.

Two wire formats cover almost every deployment anybody actually has. The
OpenAI-compatible ``/v1/chat/completions`` shape is spoken by vLLM, Ollama,
llama.cpp's server, Azure OpenAI, and most self-hosted gateways — which means
one implementation serves the air-gapped case and the bring-your-own-endpoint
case at once. Anthropic's ``/v1/messages`` is the other.

**What is deliberately not here.** Bedrock and Vertex have their own request
signing and their own message shapes, and both also publish OpenAI-compatible
endpoints. Shipping an unverified guess at their native wire formats would be
worse than shipping neither: it would look like support, fail on first contact,
and the failure would arrive during somebody's evaluation. They are reachable
through :class:`OpenAiCompatibleProvider` today, and a native adapter is a
small class written against a live endpoint by somebody who has one.

The HTTP is stdlib. Adding a dependency for an optional feature is how an
air-gapped install acquires a package it cannot download, and a JSON POST does
not need a library.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any, ClassVar

from prama.core.errors import ValidationError
from prama.llm.spi import Grammar, Hosting, ModelProvider, Request, Response
from prama.secrets.value import SecretValue
from prama.security.egress import Gate


class NullProvider(ModelProvider):
    """No model at all, declining politely.

    Registered by default so that every model-assisted path has something to
    call and a deployment with no provider configured behaves identically to
    one whose provider is down — which is the behaviour that has to work
    anyway. Prama's deterministic half is unaffected: nothing here decides a
    verdict.
    """

    name: ClassVar[str] = "none"
    hosting: ClassVar[Hosting] = Hosting.SELF_HOSTED

    def complete(self, request: Request) -> Response:
        return Response(
            text="",
            model="none",
            provider=self.name,
            request_fingerprint=request.fingerprint,
            incomplete=(
                "no model provider is configured. Every model-assisted feature is "
                "optional; the deterministic controls are unaffected"
            ),
        )


class ScriptedProvider(ModelProvider):
    """A model whose answers are written down.

    For tests, for offline demonstrations, and for the conformance corpus. The
    validation pipeline downstream must behave identically whether the text
    came from a model or from here, and the only way to be sure of that is for
    the tests to exercise it with text nobody can quietly make well-formed.
    """

    name: ClassVar[str] = "scripted"
    hosting: ClassVar[Hosting] = Hosting.SELF_HOSTED

    def __init__(
        self,
        answers: Sequence[str] | Callable[[Request], str],
        *,
        supports_grammar: bool = False,
    ) -> None:
        self._answers = answers
        self._index = 0
        self.calls: list[Request] = []
        # Instance-level rather than class-level: two scripted providers in one
        # test may stand for different vendors.
        self.supports_grammar = supports_grammar  # type: ignore[misc]

    def complete(self, request: Request) -> Response:
        self.calls.append(request)
        if callable(self._answers):
            text = self._answers(request)
        elif self._index < len(self._answers):
            text = self._answers[self._index]
            self._index += 1
        else:
            text = ""
        return Response(
            text=text,
            model="scripted",
            provider=self.name,
            request_fingerprint=request.fingerprint,
            output_tokens=len(text.split()),
            grammar_enforced=bool(self.supports_grammar and request.grammar),
            incomplete="" if text else "the script ran out of answers",
        )


class _HttpProvider(ModelProvider):
    """Shared plumbing for the two wire formats."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: SecretValue | None = None,
        timeout: float = 60.0,
        hosting: Hosting | None = None,
        opener: Callable[[urllib.request.Request, float], bytes] | None = None,
        streamer: Callable[[urllib.request.Request, float], Iterable[bytes]] | None = None,
        gate: Gate | None = None,
        region: str = "",
    ) -> None:
        if not endpoint:
            raise ValidationError(
                f"{self.name} needs an endpoint",
                remedy="Set the provider's endpoint in configuration.",
            )
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        #: Overridable per instance, because a self-hosted vLLM and a vendor's
        #: API speak the same protocol and are not the same residency class.
        if hosting is not None:
            self.hosting = hosting  # type: ignore[misc]
        vendor = _vendor_of(self._endpoint)
        if vendor and self.hosting is Hosting.SELF_HOSTED:
            # Self-hosted is exempt from residency checks, so calling a vendor's
            # API self-hosted would send RESTRICTED data with no gate at all.
            raise ValidationError(
                f"{self._endpoint} is {vendor}'s API, which is not self-hosted",
                remedy=(
                    "Set hosting to 'hosted' (the vendor's shared API) or 'tenant' "
                    "(the vendor's model in your own cloud tenancy), and install a "
                    "residency gate."
                ),
                context={"endpoint": self._endpoint, "vendor": vendor},
            )
        #: Injected so the wire format can be tested without a network. The
        #: request construction is the part with bugs in it; the socket is not.
        self._open = opener or _urlopen
        self._stream = streamer or _urlstream
        #: Residency is enforced in `ModelProvider.ask`, which is why these are
        #: set rather than checked here: a provider that carried its own check
        #: would be a second place for the rule to live, and the one that gets
        #: forgotten. Absent, and hosted, `ask` refuses.
        self.residency_gate = gate
        #: A jurisdiction ("EU"), not a cloud region ("eu-west-1"): it is
        #: matched against the tenant's residency list.
        self.residency_region = region

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        request = urllib.request.Request(
            url=f"{self._endpoint}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json", **headers},
            method="POST",
        )
        return json.loads(self._open(request, self._timeout))

    def _failure(self, request: Request, error: Exception) -> Response:
        """A provider that cannot answer returns a response saying so.

        Never an exception. A model being unreachable is an ordinary operating
        condition, and every caller has a fallback — raising would turn a
        degraded feature into a failed run, which is precisely the coupling
        between the deterministic engine and the model that CON-007 forbids.
        """
        return Response(
            text="",
            model=self._model,
            provider=self.name,
            request_fingerprint=request.fingerprint,
            incomplete=f"{type(error).__name__}: {error}",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Dialect:
    """What one OpenAI-compatible server does with a constrained-output request:
    the body field it reads for a GBNF grammar and for a regex, or empty when it
    has none and would ignore the field."""

    grammar: str = ""
    regex: str = ""


DIALECTS: dict[str, Dialect] = {
    "vllm": Dialect(grammar="guided_grammar", regex="guided_regex"),
    "llamacpp": Dialect(grammar="grammar"),
    "ollama": Dialect(),
    "lmstudio": Dialect(),
    "tgi": Dialect(),
    "openai": Dialect(),
    #: Unknown server: assume it enforces nothing, the safe side of the claim.
    "generic": Dialect(),
}

#: API hosts that belong to a vendor. A provider pointed at one cannot be
#: declared self-hosted.
VENDOR_HOSTS: tuple[tuple[str, str], ...] = (
    ("api.openai.com", "OpenAI"),
    (".openai.azure.com", "Microsoft Azure"),
    ("api.anthropic.com", "Anthropic"),
    ("huggingface.co", "Hugging Face"),
    (".amazonaws.com", "Amazon"),
    ("googleapis.com", "Google"),
    ("api.mistral.ai", "Mistral"),
    ("api.together.xyz", "Together"),
    ("api.groq.com", "Groq"),
)


def _vendor_of(endpoint: str) -> str:
    host = (urllib.parse.urlsplit(endpoint).hostname or "").lower()
    for suffix, vendor in VENDOR_HOSTS:
        bare = suffix.lstrip(".")
        if host == bare or host.endswith("." + bare):
            return vendor
    return ""


class OpenAiCompatibleProvider(_HttpProvider):
    """Anything speaking ``/v1/chat/completions``.

    vLLM, Ollama, llama.cpp's server, Azure OpenAI, and most gateways. The
    default hosting is self-hosted because that is the deployment this exists
    for; point it at a vendor and set the hosting to match, or the residency
    check will let through data that should not leave.
    """

    name: ClassVar[str] = "openai_compatible"
    hosting: ClassVar[Hosting] = Hosting.SELF_HOSTED
    supports_grammar: ClassVar[bool] = True

    def __init__(
        self, *, hosting: Hosting | None = None, dialect: str = "generic", **kwargs: Any
    ) -> None:
        # Required, not defaulted. The default used to be self-hosted, which
        # is exempt from residency checks, so the one deployment that forgot
        # to say where its model ran was the one that exported.
        if hosting is None:
            raise ValidationError(
                "an OpenAI-compatible provider must say where the model runs",
                remedy="Pass hosting: self_hosted, tenant or hosted.",
            )
        if dialect not in DIALECTS:
            raise ValidationError(
                f"unknown server dialect {dialect!r}",
                remedy=f"One of: {', '.join(sorted(DIALECTS))}.",
                context={"dialect": dialect},
            )
        #: Which server this is, because they differ in what they enforce:
        #: vLLM honours a grammar and a regex, llama.cpp a grammar only, and
        #: Ollama, LM Studio, TGI's chat route and OpenAI ignore both.
        self.dialect = dialect
        super().__init__(hosting=hosting, **kwargs)

    def _path(self) -> str:
        """Where chat completions are posted, relative to the endpoint."""
        return "/v1/chat/completions"

    def _auth(self, headers: dict[str, str]) -> dict[str, str]:
        if self._api_key is not None:
            headers["authorization"] = f"Bearer {self._api_key.reveal()}"
        return headers

    def complete(self, request: Request) -> Response:
        headers = self._auth({})
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.seed is not None:
            body["seed"] = request.seed
        # Enforced only where this server's dialect is known to apply it. It
        # used to be recorded as enforced whenever the field was *sent*, and a
        # server that does not know the field ignores it silently, so the
        # record claimed a constraint that was never applied.
        enforced = False
        fields = DIALECTS[self.dialect]
        if request.grammar is not None and request.grammar.definition and fields.grammar:
            body[fields.grammar] = request.grammar.definition
            enforced = True
        elif request.grammar is not None and request.grammar.pattern and fields.regex:
            body[fields.regex] = request.grammar.pattern
            enforced = True

        started = time.monotonic()
        try:
            payload = self._post(self._path(), body, headers)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            return self._failure(request, error)
        usage = payload.get("usage") or {}
        choices = payload.get("choices") or [{}]
        message = (choices[0] or {}).get("message") or {}
        finish = (choices[0] or {}).get("finish_reason", "")
        return Response(
            text=message.get("content") or "",
            model=payload.get("model") or self._model,
            provider=self.name,
            request_fingerprint=request.fingerprint,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            grammar_enforced=enforced,
            latency_ms=(time.monotonic() - started) * 1000,
            incomplete="truncated: hit the token limit" if finish == "length" else "",
        )

    def stream(self, request: Request) -> Iterator[str]:
        """Tokens from ``/v1/chat/completions`` with ``stream: true`` (SSE)."""
        headers = self._auth({"content-type": "application/json"})
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.seed is not None:
            body["seed"] = request.seed
        call = urllib.request.Request(
            url=f"{self._endpoint}{self._path()}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        for raw in self._stream(call, self._timeout):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                delta = (json.loads(data).get("choices") or [{}])[0].get("delta") or {}
            except (ValueError, AttributeError, IndexError):
                continue  # a malformed event is skipped, not fatal to the stream
            if delta.get("content"):
                yield str(delta["content"])


class AzureOpenAiProvider(OpenAiCompatibleProvider):
    """Azure OpenAI: a deployment in the customer's own Azure tenant.

    The route's model is the *deployment* name, and the key travels as
    ``api-key``. Hosting defaults to `tenant`, which is what Azure OpenAI is.
    """

    name: ClassVar[str] = "azure_openai"
    hosting: ClassVar[Hosting] = Hosting.TENANT
    #: Pinned, for the same reason as Anthropic's: a moving API version changes
    #: what every proposal was generated from without recording that it did.
    api_version: ClassVar[str] = "2024-10-21"

    def __init__(self, *, hosting: Hosting | None = None, **kwargs: Any) -> None:
        kwargs["dialect"] = "openai"
        super().__init__(hosting=hosting or Hosting.TENANT, **kwargs)

    def _path(self) -> str:
        deployment = urllib.parse.quote(self._model, safe="")
        return f"/openai/deployments/{deployment}/chat/completions?api-version={self.api_version}"

    def _auth(self, headers: dict[str, str]) -> dict[str, str]:
        if self._api_key is not None:
            headers["api-key"] = self._api_key.reveal()
        return headers


class VertexProvider(OpenAiCompatibleProvider):
    """Google Vertex AI through its OpenAI-compatible endpoint.

    The endpoint is the full base,
    ``https://<location>-aiplatform.googleapis.com/v1/projects/<project>/locations/<location>/endpoints/openapi``,
    and the credential reference resolves to an OAuth access token (for example
    one refreshed by `gcloud auth print-access-token` into the secret store).
    Models are named as Vertex names them: ``google/gemini-2.0-flash-001``.
    """

    name: ClassVar[str] = "vertex"
    hosting: ClassVar[Hosting] = Hosting.HOSTED

    def __init__(self, *, hosting: Hosting | None = None, **kwargs: Any) -> None:
        if "/endpoints/openapi" not in str(kwargs.get("endpoint", "")):
            raise ValidationError(
                "a Vertex provider needs its OpenAI-compatible endpoint",
                remedy=(
                    "Set the endpoint to https://<location>-aiplatform.googleapis.com/v1/"
                    "projects/<project>/locations/<location>/endpoints/openapi."
                ),
            )
        kwargs["dialect"] = "openai"
        super().__init__(hosting=hosting or Hosting.HOSTED, **kwargs)

    def _path(self) -> str:
        return "/chat/completions"


class AnthropicProvider(_HttpProvider):
    """Anthropic's ``/v1/messages``."""

    name: ClassVar[str] = "anthropic"
    hosting: ClassVar[Hosting] = Hosting.HOSTED
    supports_grammar: ClassVar[bool] = False

    #: Pinned rather than "latest". An API version that moves underneath a
    #: deployment changes what every proposal in the queue was generated from,
    #: and nothing would record that it had.
    api_version: ClassVar[str] = "2023-06-01"

    def complete(self, request: Request) -> Response:
        if self._api_key is None:
            return self._failure(request, ValueError("no API key configured"))
        headers = {
            "x-api-key": self._api_key.reveal(),
            "anthropic-version": self.api_version,
        }
        body = {
            "model": self._model,
            "system": request.system,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        started = time.monotonic()
        try:
            payload = self._post("/v1/messages", body, headers)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            return self._failure(request, error)
        blocks = payload.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = payload.get("usage") or {}
        return Response(
            text=text,
            model=payload.get("model") or self._model,
            provider=self.name,
            request_fingerprint=request.fingerprint,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            grammar_enforced=False,
            latency_ms=(time.monotonic() - started) * 1000,
            incomplete=(
                "truncated: hit the token limit"
                if payload.get("stop_reason") == "max_tokens"
                else ""
            ),
        )


def _urlopen(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return bytes(response.read())


def _urlstream(request: urllib.request.Request, timeout: float) -> Iterator[bytes]:
    """The response body line by line, for server-sent events."""
    with urllib.request.urlopen(request, timeout=timeout) as response:
        yield from response


#: Grammars a provider can be asked to enforce. Defined here rather than in the
#: inducer so a provider's capability check has something concrete to answer
#: about.
PQL_CONTROL_GRAMMAR = Grammar(
    name="pql_control",
    # Deliberately loose: it constrains the *shape* — a CHECK, one target, a
    # BECAUSE — and leaves the assertion to the parser. A grammar tight enough
    # to encode all of PQL would have to be regenerated whenever the language
    # changed, and the two would drift; the parser is the authority, and this
    # exists to stop a model returning an apology instead of a control.
    definition=(
        'root ::= "CHECK " target " " assertion clause* "\\n"\n'
        "target ::= [a-zA-Z_][a-zA-Z0-9_.]*\n"
        "assertion ::= [^\\n]+\n"
        'clause ::= "\\n  " [A-Z][^\\n]*\n'
    ),
    pattern=r"(?s)^CHECK\s+\S+.*$",
)


class BedrockProvider(_HttpProvider):
    """Amazon Bedrock's Converse API, signed with SigV4 from the standard library.

    The credential is one secret reference resolving to
    ``ACCESS_KEY_ID:SECRET_ACCESS_KEY`` (optionally ``:SESSION_TOKEN``), so no
    key is ever stored in configuration. Hosting defaults to `tenant`: the model
    runs in the customer's own AWS account, which is what Bedrock is for.
    """

    name: ClassVar[str] = "bedrock"
    hosting: ClassVar[Hosting] = Hosting.TENANT
    supports_grammar: ClassVar[bool] = False

    def __init__(self, *, aws_region: str, hosting: Hosting | None = None, **kwargs: Any) -> None:
        if not aws_region:
            raise ValidationError(
                "a Bedrock provider needs its AWS region", remedy="Set settings.aws_region."
            )
        self.aws_region = aws_region
        kwargs.setdefault("endpoint", f"https://bedrock-runtime.{aws_region}.amazonaws.com")
        super().__init__(hosting=hosting or Hosting.TENANT, **kwargs)

    def _credentials(self) -> tuple[str, str, str]:
        if self._api_key is None:
            raise ValidationError(
                "a Bedrock provider needs a credential reference",
                remedy="Point credential_ref at ACCESS_KEY_ID:SECRET_ACCESS_KEY[:SESSION_TOKEN].",
            )
        parts = self._api_key.reveal().split(":")
        if len(parts) not in (2, 3):
            raise ValidationError(
                "the Bedrock credential is not ACCESS_KEY_ID:SECRET_ACCESS_KEY[:SESSION_TOKEN]",
                remedy="Store the credential in that form under the referenced secret.",
            )
        return parts[0], parts[1], parts[2] if len(parts) == 3 else ""

    def complete(self, request: Request) -> Response:
        from datetime import UTC, datetime

        from prama.llm.sigv4 import sign

        body = {
            "messages": [{"role": "user", "content": [{"text": request.prompt}]}],
            "system": [{"text": request.system}],
            "inferenceConfig": {
                "maxTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        payload = json.dumps(body).encode("utf-8")
        path = f"/model/{urllib.parse.quote(self._model, safe='')}/converse"
        host = urllib.parse.urlsplit(self._endpoint).hostname or ""
        started = time.monotonic()
        try:
            access, secret, token = self._credentials()
            headers = {"content-type": "application/json"}
            headers |= sign(
                method="POST",
                host=host,
                path=path,
                headers=headers,
                payload=payload,
                access_key=access,
                secret_key=secret,
                region=self.aws_region,
                service="bedrock",
                amz_date=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
                session_token=token,
            )
            call = urllib.request.Request(
                url=f"{self._endpoint}{path}", data=payload, headers=headers, method="POST"
            )
            reply = json.loads(self._open(call, self._timeout))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            return self._failure(request, error)
        content = ((reply.get("output") or {}).get("message") or {}).get("content") or []
        text = "".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        usage = reply.get("usage") or {}
        return Response(
            text=text,
            model=self._model,
            provider=self.name,
            request_fingerprint=request.fingerprint,
            input_tokens=int(usage.get("inputTokens") or 0),
            output_tokens=int(usage.get("outputTokens") or 0),
            latency_ms=(time.monotonic() - started) * 1000,
            incomplete="truncated: hit the token limit"
            if reply.get("stopReason") == "max_tokens"
            else "",
        )
