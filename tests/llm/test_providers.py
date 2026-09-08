"""The model seam: residency at the boundary, and failure as an outcome.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from prama.core.errors import ValidationError
from prama.llm.providers import (
    AnthropicProvider,
    NullProvider,
    OpenAiCompatibleProvider,
    ScriptedProvider,
)
from prama.llm.spi import Grammar, Hosting, ProviderRegistry, Request
from prama.secrets.value import SecretValue
from prama.semantic.values import Sensitivity


def canned(payload: dict[str, object]):  # type: ignore[no-untyped-def]
    def opener(request: urllib.request.Request, timeout: float) -> bytes:
        opener.seen = request  # type: ignore[attr-defined]
        return json.dumps(payload).encode()

    return opener


# -- residency ---------------------------------------------------------------


def test_pii_may_not_be_sent_to_a_hosted_model() -> None:
    """The check lives at the boundary rather than in each caller, because a
    rule enforced in six places is a rule with a hole in it."""
    provider = AnthropicProvider(
        endpoint="https://example.invalid", model="m", api_key=SecretValue("k")
    )
    with pytest.raises(ValidationError, match="may not be sent to a hosted model"):
        provider.ask(Request(system="s", prompt="p", sensitivity=Sensitivity.PII))


def test_a_self_hosted_model_may_see_anything() -> None:
    """The deployment this exists for. An air-gapped estate loses nothing that
    produces a verdict, and nothing that needs a model either."""
    provider = ScriptedProvider(lambda _: "ok")
    for sensitivity in Sensitivity:
        assert provider.ask(Request(system="s", prompt="p", sensitivity=sensitivity)).ok


def test_the_most_restricted_class_may_not_even_leave_the_tenancy() -> None:
    assert Sensitivity.RESTRICTED not in Hosting.TENANT.permits
    assert Sensitivity.RESTRICTED in Hosting.SELF_HOSTED.permits


def test_the_registry_prefers_the_provider_that_does_not_move_the_data() -> None:
    """When a self-hosted model can do the job it is the right answer whatever
    else is configured."""
    registry = ProviderRegistry()
    registry.register(AnthropicProvider(endpoint="https://example.invalid", model="m"))
    registry.register(ScriptedProvider([]))
    assert registry.for_sensitivity(Sensitivity.INTERNAL)[0] == "scripted"
    assert registry.for_sensitivity(Sensitivity.PII) == ("scripted",)


def test_an_unconfigured_provider_says_that_models_are_optional() -> None:
    with pytest.raises(ValidationError, match="no model provider named") as caught:
        ProviderRegistry().get("anthropic")
    assert "deterministic half" in str(caught.value)


# -- failure is an outcome, not an exception ---------------------------------


def test_no_provider_configured_declines_politely() -> None:
    """A deployment with no provider behaves identically to one whose provider
    is down — which is the behaviour that has to work anyway."""
    response = NullProvider().ask(Request(system="s", prompt="p"))
    assert not response.ok
    assert "optional" in response.incomplete


def test_an_unreachable_model_returns_a_response_rather_than_raising() -> None:
    """Raising would turn a degraded feature into a failed run, which is the
    coupling between the engine and the model that CON-007 forbids."""

    def refuse(request: urllib.request.Request, timeout: float) -> bytes:
        raise urllib.error.URLError("connection refused")

    provider = OpenAiCompatibleProvider(endpoint="http://localhost:1", model="m", opener=refuse)
    response = provider.ask(Request(system="s", prompt="p"))
    assert not response.ok
    assert "connection refused" in response.incomplete


# -- the wire formats --------------------------------------------------------


def test_the_openai_shape_carries_system_and_user_messages() -> None:
    opener = canned(
        {
            "model": "local-1",
            "choices": [{"message": {"content": "CHECK t.x IS NOT NULL"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )
    provider = OpenAiCompatibleProvider(endpoint="http://x", model="m", opener=opener)
    response = provider.ask(Request(system="be terse", prompt="write a control"))
    assert response.text == "CHECK t.x IS NOT NULL"
    assert response.input_tokens == 10
    body = json.loads(opener.seen.data)  # type: ignore[attr-defined]
    assert body["messages"][0] == {"role": "system", "content": "be terse"}
    assert body["temperature"] == 0.0
    assert body["seed"] == 7


def test_a_grammar_is_passed_through_and_the_response_says_it_was() -> None:
    opener = canned({"choices": [{"message": {"content": "x"}}]})
    provider = OpenAiCompatibleProvider(endpoint="http://x", model="m", opener=opener)
    response = provider.ask(
        Request(
            system="s",
            prompt="p",
            grammar=Grammar(name="g", definition='root ::= "CHECK"'),
        )
    )
    assert json.loads(opener.seen.data)["guided_grammar"]  # type: ignore[attr-defined]
    assert response.grammar_enforced


def test_a_truncated_completion_is_reported_as_incomplete() -> None:
    """Silently returning half a control would send unparseable PQL to the
    gate and blame the model for a token limit."""
    opener = canned({"choices": [{"message": {"content": "CHECK t.x"}, "finish_reason": "length"}]})
    provider = OpenAiCompatibleProvider(endpoint="http://x", model="m", opener=opener)
    assert "truncated" in provider.ask(Request(system="s", prompt="p")).incomplete


def test_the_anthropic_shape_pins_its_api_version() -> None:
    """A version that moves underneath a deployment changes what every proposal
    in the queue was generated from, and nothing would record that it had."""
    opener = canned(
        {
            "model": "claude",
            "content": [{"type": "text", "text": "CHECK t.x IS NOT NULL"}],
            "usage": {"input_tokens": 3, "output_tokens": 4},
        }
    )
    provider = AnthropicProvider(
        endpoint="https://api.example",
        model="m",
        api_key=SecretValue("k"),
        opener=opener,
    )
    response = provider.ask(Request(system="s", prompt="p"))
    assert response.text == "CHECK t.x IS NOT NULL"
    assert opener.seen.headers["Anthropic-version"] == "2023-06-01"  # type: ignore[attr-defined]


def test_an_api_key_never_appears_in_a_recorded_response() -> None:
    opener = canned({"content": [{"type": "text", "text": "x"}]})
    provider = AnthropicProvider(
        endpoint="https://api.example",
        model="m",
        api_key=SecretValue("sk-secret-value"),
        opener=opener,
    )
    response = provider.ask(Request(system="s", prompt="p"))
    assert "sk-secret-value" not in json.dumps(response.to_dict())


def test_a_provider_pointed_at_a_vendor_can_declare_its_real_hosting() -> None:
    """A self-hosted vLLM and a vendor's API speak the same protocol and are
    not the same residency class."""
    hosted = OpenAiCompatibleProvider(
        endpoint="https://api.vendor", model="m", hosting=Hosting.HOSTED
    )
    with pytest.raises(ValidationError, match="may not be sent"):
        hosted.ask(Request(system="s", prompt="p", sensitivity=Sensitivity.PII))
