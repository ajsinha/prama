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
from collections.abc import Callable, Sequence
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

    def complete(self, request: Request) -> Response:
        headers = {}
        if self._api_key is not None:
            headers["authorization"] = f"Bearer {self._api_key.reveal()}"
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
            payload = self._post("/v1/chat/completions", body, headers)
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
