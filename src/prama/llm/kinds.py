"""Building a provider from its stored description.

A provider row in the database says what kind of server it is, where it is and
how it is hosted; this turns that into a `ModelProvider`. It is the one place
the configured description meets code, so the refusals that protect data live
here too:

* **Offline.** With ``llm.offline`` set, only a self-hosted provider on this
  host or a private network is built. An air-gapped deployment must not be
  one mistyped endpoint away from exporting.
* **Hosting honesty** is enforced by the provider itself (a vendor API cannot
  be declared self-hosted) and so holds here without restating it.

Deliberately free of `prama.db`: a row arrives as a `ProviderSpec`, and the
database package does the mapping (design note §2).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import urllib.parse
from collections.abc import Callable
from typing import Any

from prama.core.errors import ValidationError
from prama.llm.providers import (
    DIALECTS,
    AnthropicProvider,
    NullProvider,
    OpenAiCompatibleProvider,
    ScriptedProvider,
)
from prama.llm.spi import Hosting, ModelProvider
from prama.secrets.value import SecretValue
from prama.security.egress import Gate

#: The kinds a provider row may name, and what each needs.
KINDS: dict[str, str] = {
    "openai_compatible": "vLLM, Ollama, llama.cpp, LM Studio, TGI, or any OpenAI-shaped API",
    "anthropic": "Anthropic's Messages API",
    "scripted": "fixed answers, for demonstrations and tests",
    "none": "no model: every feature falls back to its deterministic path",
}


@dataclasses.dataclass(frozen=True, slots=True)
class ProviderSpec:
    """A provider as stored: everything needed to build it except the secret."""

    name: str
    kind: str
    hosting: str
    endpoint: str = ""
    dialect: str = ""
    region: str = ""
    settings: dict[str, Any] = dataclasses.field(default_factory=dict)


def is_local(endpoint: str) -> bool:
    """Whether *endpoint* is on this host or a private network, by address.

    Hostnames other than ``localhost`` are not resolved: a name that resolves
    privately today can resolve publicly tomorrow, and offline mode must not
    depend on a DNS answer.
    """
    host = (urllib.parse.urlsplit(endpoint).hostname or "").lower()
    if host in ("localhost", "ip6-localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def build(
    spec: ProviderSpec,
    *,
    model: str,
    credential: SecretValue | None = None,
    gate: Gate | None = None,
    offline: bool = False,
    opener: Callable[..., bytes] | None = None,
) -> ModelProvider:
    """A `ModelProvider` for *spec*, serving *model*."""
    if spec.kind not in KINDS:
        raise ValidationError(
            f"unknown provider kind {spec.kind!r}",
            remedy=f"One of: {', '.join(sorted(KINDS))}.",
            context={"provider": spec.name, "kind": spec.kind},
        )
    try:
        hosting = Hosting(spec.hosting)
    except ValueError as exc:
        raise ValidationError(
            f"{spec.hosting!r} is not a hosting class",
            remedy="One of: self_hosted, tenant, hosted.",
            context={"provider": spec.name},
            cause=exc,
        ) from exc
    networked = spec.kind in ("openai_compatible", "anthropic")
    if (
        offline
        and networked
        and (hosting is not Hosting.SELF_HOSTED or not is_local(spec.endpoint))
    ):
        raise ValidationError(
            f"{spec.name} is not usable offline",
            remedy=(
                "llm.offline allows only self-hosted providers on this host or a "
                "private network (by address). Turn offline off, or point the "
                "provider at a local server."
            ),
            context={"provider": spec.name, "endpoint": spec.endpoint},
        )
    extra: dict[str, Any] = {"opener": opener} if opener is not None else {}
    if spec.kind == "openai_compatible":
        return OpenAiCompatibleProvider(
            endpoint=spec.endpoint,
            model=model,
            api_key=credential,
            hosting=hosting,
            dialect=spec.dialect or "generic",
            gate=gate,
            region=spec.region,
            timeout=float(spec.settings.get("timeout_s", 60.0)),
            **extra,
        )
    if spec.kind == "anthropic":
        return AnthropicProvider(
            endpoint=spec.endpoint or "https://api.anthropic.com",
            model=model,
            api_key=credential,
            hosting=hosting,
            gate=gate,
            region=spec.region,
            **extra,
        )
    if spec.kind == "scripted":
        return ScriptedProvider(list(spec.settings.get("answers", [])))
    return NullProvider()


__all__ = ["DIALECTS", "KINDS", "ProviderSpec", "build", "is_local"]
