"""The model seam: residency at the boundary, and failure as an outcome.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

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
from prama.security.egress import Gate, ResidencyRefused
from prama.semantic.values import Sensitivity


def permitting_gate() -> Gate:
    """A residency rule that allows the movement.

    Installed explicitly in the tests below that are about the *wire format*,
    because residency is now enforced in `ask` and an absent gate is a refusal.
    Spelling it out at each such call site is the point: a test that sends a
    prompt to a hosted model is a test that has decided the prompt may go.
    """
    return Gate.for_tenant(residency=None, tenant_id="t")


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

    provider = OpenAiCompatibleProvider(
        endpoint="http://localhost:1", model="m", opener=refuse, hosting=Hosting.SELF_HOSTED
    )
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
    provider = OpenAiCompatibleProvider(
        endpoint="http://x", model="m", opener=opener, hosting=Hosting.SELF_HOSTED, dialect="vllm"
    )
    response = provider.ask(Request(system="be terse", prompt="write a control"))
    assert response.text == "CHECK t.x IS NOT NULL"
    assert response.input_tokens == 10
    body = json.loads(opener.seen.data)  # type: ignore[attr-defined]
    assert body["messages"][0] == {"role": "system", "content": "be terse"}
    assert body["temperature"] == 0.0
    assert body["seed"] == 7


def test_a_grammar_is_passed_through_and_the_response_says_it_was() -> None:
    opener = canned({"choices": [{"message": {"content": "x"}}]})
    provider = OpenAiCompatibleProvider(
        endpoint="http://x", model="m", opener=opener, hosting=Hosting.SELF_HOSTED, dialect="vllm"
    )
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
    provider = OpenAiCompatibleProvider(
        endpoint="http://x", model="m", opener=opener, hosting=Hosting.SELF_HOSTED, dialect="vllm"
    )
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
        gate=permitting_gate(),
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
        gate=permitting_gate(),
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


# -- residency, which is a different question from sensitivity ---------------


class TestResidencyIsEnforcedNotAssumed:
    """`model-inference` is registered as an egress point in
    :mod:`prama.security.egress`, and until this was written nothing enforced
    it. The sensitivity check was standing in for a residency check it cannot
    perform: it asks what *class* the data is, never where it is *from* or
    where the model *is*. A prompt carrying EU column names and samples reached
    a US endpoint so long as nobody had labelled it PII.
    """

    def canned_provider(self, **kwargs: object) -> AnthropicProvider:
        return AnthropicProvider(
            endpoint="https://api.example",
            model="m",
            api_key=SecretValue("k"),
            opener=canned({"content": [{"type": "text", "text": "x"}]}),
            **kwargs,  # type: ignore[arg-type]
        )

    def test_a_hosted_provider_without_a_gate_refuses(self) -> None:
        """Undeclared is not unrestricted. The deployment nobody got round to
        configuring must not be the one that exports."""
        with pytest.raises(ResidencyRefused, match="no residency rule is declared"):
            self.canned_provider().ask(Request(system="s", prompt="p"))

    def test_a_self_hosted_provider_needs_no_gate(self) -> None:
        """Nothing leaves the network, so there is nothing to permit. An
        air-gapped estate is not asked to declare a residency rule about a
        movement that does not happen."""
        assert ScriptedProvider(lambda _: "ok").ask(Request(system="s", prompt="p")).ok

    def test_a_prompt_may_not_travel_where_its_subject_may_not(self) -> None:
        """The case sensitivity cannot catch: ordinary internal data, correctly
        classified, belonging to a jurisdiction that forbids the destination."""
        provider = self.canned_provider(
            gate=Gate.for_tenant(residency="EU", tenant_id="t"), region="US"
        )
        with pytest.raises(ResidencyRefused):
            provider.ask(
                Request(
                    system="s",
                    prompt="p",
                    context={"jurisdiction": "EU", "dataset": "positions"},
                )
            )

    def test_the_same_prompt_travels_within_its_jurisdiction(self) -> None:
        """The counterfactual. A control that refuses everything is not a
        residency rule, it is an outage."""
        provider = self.canned_provider(
            gate=Gate.for_tenant(residency="EU", tenant_id="t"), region="EU"
        )
        assert provider.ask(
            Request(
                system="s",
                prompt="p",
                context={"jurisdiction": "EU", "dataset": "positions"},
            )
        ).ok


class TestTheThreeDefects:
    """Wave 12's first item (docs/design/llm-gateway.md §0). Each test fails
    against the code before the repair."""

    @pytest.mark.parametrize("dialect", ["ollama", "lmstudio", "tgi", "openai", "generic"])
    def test_a_server_that_ignores_grammars_is_not_recorded_as_enforcing_one(
        self, dialect: str
    ) -> None:
        opener = canned({"choices": [{"message": {"content": "x"}}]})
        provider = OpenAiCompatibleProvider(
            endpoint="http://x",
            model="m",
            opener=opener,
            hosting=Hosting.SELF_HOSTED,
            dialect=dialect,
        )
        response = provider.ask(
            Request(system="s", prompt="p", grammar=Grammar(name="g", definition='root ::= "x"'))
        )
        assert not response.grammar_enforced
        assert "guided_grammar" not in json.loads(opener.seen.data)  # type: ignore[attr-defined]

    def test_llamacpp_takes_a_grammar_but_not_a_regex(self) -> None:
        opener = canned({"choices": [{"message": {"content": "x"}}]})
        provider = OpenAiCompatibleProvider(
            endpoint="http://x",
            model="m",
            opener=opener,
            hosting=Hosting.SELF_HOSTED,
            dialect="llamacpp",
        )
        grammar = provider.ask(
            Request(system="s", prompt="p", grammar=Grammar(name="g", definition="root ::= x"))
        )
        assert grammar.grammar_enforced  # the control: a dialect that does enforce
        assert json.loads(opener.seen.data)["grammar"]  # type: ignore[attr-defined]
        regex = provider.ask(
            Request(system="s", prompt="p", grammar=Grammar(name="g", pattern="^CHECK"))
        )
        assert not regex.grammar_enforced

    def test_hosting_must_be_stated(self) -> None:
        with pytest.raises(ValidationError, match="must say where the model runs"):
            OpenAiCompatibleProvider(endpoint="http://localhost:8000", model="m")

    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://api.openai.com",
            "https://bank.openai.azure.com",
            "https://router.huggingface.co",
            "https://bedrock-runtime.eu-west-1.amazonaws.com",
        ],
    )
    def test_a_vendor_api_cannot_be_declared_self_hosted(self, endpoint: str) -> None:
        with pytest.raises(ValidationError, match="not self-hosted"):
            OpenAiCompatibleProvider(endpoint=endpoint, model="m", hosting=Hosting.SELF_HOSTED)

    def test_a_vendor_api_declared_hosted_is_accepted(self) -> None:
        # The control: the check is about the claim, not the vendor.
        OpenAiCompatibleProvider(
            endpoint="https://api.openai.com", model="m", hosting=Hosting.HOSTED
        )

    def test_a_secret_and_a_card_number_are_withheld_from_the_prompt(self) -> None:
        opener = canned({"choices": [{"message": {"content": "x"}}]})
        provider = OpenAiCompatibleProvider(
            endpoint="http://x", model="m", opener=opener, hosting=Hosting.SELF_HOSTED
        )
        provider.ask(
            Request(
                system="s",
                prompt="card 4111 1111 1111 1111, db postgres://u:p@h/db, trade 1234567890123",
            )
        )
        sent = json.loads(opener.seen.data)["messages"][1]["content"]  # type: ignore[attr-defined]
        assert "4111" not in sent and "postgres://" not in sent
        assert "1234567890123" in sent  # the control: not every long number is a card


class TestPatternRedaction:
    def test_a_valid_iban_is_withheld_and_a_lookalike_is_not(self) -> None:
        from prama.llm.redact import redact

        # GB82 WEST 1234 5698 7654 32 is the ISO 13616 example, and valid.
        out = redact("pay GB82 WEST 1234 5698 7654 32 today; ref GB00 WEST 1234 5698 7654 32")
        assert "GB82 WEST" not in out and "[an IBAN withheld]" in out
        assert "GB00 WEST 1234 5698 7654 32" in out  # the control: bad check digits survive

    def test_an_email_address_is_withheld(self) -> None:
        from prama.llm.redact import redact

        out = redact("ask ada.lovelace@bank.example about trades.notional")
        assert "ada.lovelace" not in out and "trades.notional" in out


class TestStreaming:
    def test_the_openai_stream_is_read_token_by_token(self) -> None:
        events = [
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"CHECK "}}]}\n',
            b": keep-alive\n",
            b"data: not json\n",
            b'data: {"choices":[{"delta":{"content":"t.a IS NOT NULL"}}]}\n',
            b"data: [DONE]\n",
            b'data: {"choices":[{"delta":{"content":"after done"}}]}\n',
        ]
        provider = OpenAiCompatibleProvider(
            endpoint="http://x",
            model="m",
            hosting=Hosting.SELF_HOSTED,
            streamer=lambda _request, _timeout: iter(events),
        )
        pieces = list(provider.ask_stream(Request(system="s", prompt="p")))
        assert pieces == ["CHECK ", "t.a IS NOT NULL"]

    def test_a_provider_that_cannot_stream_yields_its_answer_once(self) -> None:
        from prama.llm.providers import ScriptedProvider

        assert list(ScriptedProvider(["whole"]).ask_stream(Request(system="s", prompt="p"))) == [
            "whole"
        ]

    def test_streaming_applies_the_same_residency_rule(self) -> None:
        hosted = OpenAiCompatibleProvider(
            endpoint="https://api.openai.com", model="m", hosting=Hosting.HOSTED
        )
        with pytest.raises(ValidationError):
            list(hosted.ask_stream(Request(system="s", prompt="p", sensitivity=Sensitivity.PII)))


class TestBedrock:
    def _provider(self, opener: Any) -> Any:
        from prama.llm.providers import BedrockProvider

        return BedrockProvider(
            aws_region="eu-west-1",
            model="anthropic.claude-sonnet-5",
            opener=opener,
            api_key=SecretValue("AKIDEXAMPLE:wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"),
            gate=permitting_gate(),
        )

    def test_a_converse_call_is_signed_and_read(self) -> None:
        opener = canned(
            {
                "output": {"message": {"content": [{"text": "CHECK t.a IS NOT NULL"}]}},
                "usage": {"inputTokens": 12, "outputTokens": 6},
                "stopReason": "end_turn",
            }
        )
        response = self._provider(opener).ask(Request(system="s", prompt="p"))
        assert response.text == "CHECK t.a IS NOT NULL" and response.input_tokens == 12
        sent = opener.seen  # type: ignore[attr-defined]
        assert sent.full_url.endswith("/model/anthropic.claude-sonnet-5/converse")
        authorization = sent.get_header("Authorization")
        assert authorization.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
        assert "/eu-west-1/bedrock/aws4_request" in authorization
        assert "wJalrXUtnFEMI" not in json.dumps(response.to_dict())

    def test_bedrock_cannot_be_declared_self_hosted(self) -> None:
        from prama.llm.providers import BedrockProvider

        with pytest.raises(ValidationError, match="not self-hosted"):
            BedrockProvider(aws_region="eu-west-1", model="m", hosting=Hosting.SELF_HOSTED)
