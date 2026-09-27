"""The gateway routes by purpose, falls back safely, and records every call.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.llm.gateway import (
    Candidate,
    LlmGateway,
    MemoryLedger,
    ProfileProvider,
    Route,
    seal,
)
from prama.llm.providers import OpenAiCompatibleProvider, ScriptedProvider
from prama.llm.spi import Hosting, Request
from prama.security.egress import ResidencyRefused
from prama.semantic.values import Sensitivity


def _candidate(name: str, answers: list[str], hosting: Hosting = Hosting.SELF_HOSTED) -> Candidate:
    return Candidate(ScriptedProvider(answers), name, name, "scripted", hosting, "m")


def _gateway(*candidates: Candidate, across: bool = False) -> tuple[LlmGateway, MemoryLedger]:
    ledger = MemoryLedger()
    route = Route("author", tuple(candidates), max_attempts=1, fallback_across_hosting=across)
    return LlmGateway({"author": route}, ledger, tenant_id="t", surface="test"), ledger


def test_the_first_candidate_answers_and_is_recorded() -> None:
    gateway, ledger = _gateway(_candidate("local", ["CHECK t.a IS NOT NULL"]))
    assert gateway.run("author", Request(system="s", prompt="p")).text
    (record,) = ledger.records
    assert record.outcome == "ok" and record.provider_id == "local"
    assert record.response_hash and "CHECK" not in str(record.content())  # hashes, not text


def test_a_failed_candidate_falls_back_to_the_next() -> None:
    gateway, ledger = _gateway(_candidate("down", []), _candidate("up", ["ok"]))
    assert gateway.run("author", Request(system="s", prompt="p")).text == "ok"
    assert ledger.records[0].fallback_from == "down"
    assert ledger.records[0].attempts == 2


def test_fallback_never_becomes_less_local_unless_allowed() -> None:
    local_down = _candidate("local", [])
    vendor = _candidate("vendor", ["from the vendor"], Hosting.HOSTED)
    gateway, ledger = _gateway(local_down, vendor)
    assert gateway.run("author", Request(system="s", prompt="p")).text == ""
    assert ledger.records[0].outcome == "error"
    allowed, _ = _gateway(_candidate("local", []), vendor, across=True)
    # The control: with the profile's permission, it does reach the vendor.
    assert allowed.run("author", Request(system="s", prompt="p")).text == "from the vendor"


def test_a_residency_refusal_moves_to_a_candidate_that_may_receive_it() -> None:
    hosted = OpenAiCompatibleProvider(
        endpoint="https://api.openai.com", model="m", hosting=Hosting.HOSTED
    )
    vendor = Candidate(hosted, "vendor", "vendor", "openai_compatible", Hosting.HOSTED, "m")
    route = Route("author", (vendor, _candidate("local", ["kept at home"])), max_attempts=1)
    ledger = MemoryLedger()
    gateway = LlmGateway({"author": route}, ledger, tenant_id="t", surface="test")
    pii = Request(system="s", prompt="p", sensitivity=Sensitivity.PII)
    assert gateway.run("author", pii).text == "kept at home"


def test_when_nothing_may_receive_it_the_refusal_is_recorded_and_raised() -> None:
    hosted = OpenAiCompatibleProvider(
        endpoint="https://api.openai.com", model="m", hosting=Hosting.HOSTED
    )
    route = Route(
        "author", (Candidate(hosted, "v", "v", "openai_compatible", Hosting.HOSTED, "m"),)
    )
    ledger = MemoryLedger()
    gateway = LlmGateway({"author": route}, ledger, tenant_id="t", surface="test")
    with pytest.raises((ValidationError, ResidencyRefused)):
        gateway.run("author", Request(system="s", prompt="p", sensitivity=Sensitivity.PII))
    assert ledger.records[0].outcome == "refused_policy"


def test_an_unconfigured_purpose_says_how_to_configure_it() -> None:
    gateway, _ = _gateway(_candidate("local", ["x"]))
    with pytest.raises(ValidationError, match="prama llm profile set explain"):
        gateway.run("explain", Request(system="s", prompt="p"))


def test_a_profile_provider_is_a_model_provider() -> None:
    gateway, ledger = _gateway(_candidate("local", ["answer"]))
    assert ProfileProvider(gateway, "author").ask(Request(system="s", prompt="p")).text == "answer"
    assert len(ledger.records) == 1


def test_the_seal_chains() -> None:
    gateway, ledger = _gateway(_candidate("local", ["a", "b"]))
    gateway.run("author", Request(system="s", prompt="p"))
    first = seal(ledger.records[0], sequence=0, previous_hash="0" * 64)
    assert seal(ledger.records[0], sequence=0, previous_hash=first) != first


class TestTheCache:
    def _cached(self) -> tuple[LlmGateway, MemoryLedger, ScriptedProvider]:
        from prama.llm.gateway import ResponseCache

        provider = ScriptedProvider(["first", "second"])
        candidate = Candidate(provider, "local", "local", "scripted", Hosting.SELF_HOSTED, "m")
        ledger = MemoryLedger()
        gateway = LlmGateway(
            {"author": Route("author", (candidate,), max_attempts=1)},
            ledger,
            tenant_id="t",
            surface="test",
            cache=ResponseCache(),
        )
        return gateway, ledger, provider

    def test_a_repeated_deterministic_request_is_served_from_cache(self) -> None:
        gateway, ledger, provider = self._cached()
        ask = Request(system="s", prompt="p", temperature=0.0)
        assert gateway.run("author", ask).text == "first"
        assert gateway.run("author", ask).text == "first"
        assert len(provider.calls) == 1
        assert [r.served_from for r in ledger.records] == ["provider", "cache"]

    def test_a_sampled_request_is_never_cached(self) -> None:
        gateway, _, provider = self._cached()
        ask = Request(system="s", prompt="p", temperature=0.7)
        gateway.run("author", ask)
        assert gateway.run("author", ask).text == "second"  # the control
        assert len(provider.calls) == 2

    def test_a_cached_answer_is_no_oracle_for_a_refused_request(self) -> None:
        from prama.llm.gateway import ResponseCache

        hosted = OpenAiCompatibleProvider(
            endpoint="https://api.openai.com", model="m", hosting=Hosting.HOSTED
        )
        vendor = Candidate(hosted, "v", "v", "openai_compatible", Hosting.HOSTED, "m")
        route = Route("author", (vendor,), max_attempts=1)
        cache = ResponseCache()
        pii = Request(system="s", prompt="p", sensitivity=Sensitivity.PII, temperature=0.0)
        from prama.llm.spi import Response

        cache.put(
            ResponseCache.key("t", route, vendor, pii), Response("leak", "m", "v", pii.fingerprint)
        )
        gateway = LlmGateway(
            {"author": route}, MemoryLedger(), tenant_id="t", surface="x", cache=cache
        )
        with pytest.raises((ValidationError, ResidencyRefused)):
            gateway.run("author", pii)
