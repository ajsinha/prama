"""A model provider for a server's native ``/generate`` route: the worked example of
docs/developer/llm-providers.md.

Hugging Face's text-generation-inference serves an OpenAI-shaped API, which the
shipped ``openai_compatible`` kind already reaches. It also serves its own
``POST /generate``, which takes a regular-expression grammar the OpenAI shape
has no field for. This provider speaks that route.

What a provider implements is one method, ``complete``. What it does **not**
implement is the part that protects data: the sensitivity check, the residency
check and the redaction of card numbers and secrets all live in
`prama.llm.spi.ModelProvider.ask`, which calls ``complete`` last. A provider
written by somebody else cannot skip them, which is the point.

A provider answers questions; it never decides one. Nothing here may turn an
answer into a pass or a fail on data (CON-007).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from typing import Any, ClassVar

from prama.llm.spi import Hosting, ModelProvider, Request, Response
from prama.security.egress import Gate

#: Sends a body to a URL and returns the response body. Injected by the test so
#: nothing leaves the machine.
Opener = Callable[[str, bytes, float], bytes]


def _post(url: str, body: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return bytes(response.read())


class GenerateProvider(ModelProvider):
    """A self-hosted server's native ``POST {endpoint}/generate``."""

    name: ClassVar[str] = "tgi_generate"
    #: On the customer's own hardware. A vendor endpoint must not be declared
    #: self-hosted, or the residency check would let through what must not leave.
    hosting: ClassVar[Hosting] = Hosting.SELF_HOSTED
    supports_grammar: ClassVar[bool] = True

    def __init__(
        self,
        endpoint: str,
        *,
        model: str = "",
        timeout: float = 30.0,
        opener: Opener | None = None,
        gate: Gate | None = None,
        region: str = "",
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self.model = model or "default"
        self._timeout = timeout
        self._open = opener or _post
        # Set, never checked here: `ask` enforces residency, and a provider that
        # carried its own check would be a second place for the rule to live.
        # A jurisdiction ("EU"), not a cloud region ("eu-west-1").
        self.residency_gate = gate
        self.residency_region = region

    def complete(self, request: Request) -> Response:
        parameters: dict[str, Any] = {"max_new_tokens": request.max_tokens, "details": True}
        if request.temperature > 0:
            parameters |= {"do_sample": True, "temperature": request.temperature}
        if request.seed is not None:
            parameters["seed"] = request.seed
        grammar = request.grammar.pattern if request.grammar else ""
        if grammar:
            parameters["grammar"] = {"type": "regex", "value": grammar}
        body = {"inputs": f"{request.system}\n\n{request.prompt}".strip(), "parameters": parameters}

        started = time.perf_counter()
        try:
            raw = self._open(
                f"{self._endpoint}/generate", json.dumps(body).encode("utf-8"), self._timeout
            )
            payload = json.loads(raw)
        except (OSError, ValueError) as exc:
            # A failed call is an ordinary outcome with a fallback, recorded as
            # incomplete, never raised: the caller's deterministic path takes over.
            return Response(
                text="",
                model=self.model,
                provider=self.name,
                request_fingerprint=request.fingerprint,
                incomplete=f"{type(exc).__name__}: {exc}",
            )
        details = payload.get("details") or {}
        return Response(
            text=str(payload.get("generated_text", "")),
            model=self.model,
            provider=self.name,
            request_fingerprint=request.fingerprint,
            output_tokens=int(details.get("generated_tokens") or 0),
            grammar_enforced=bool(grammar),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
