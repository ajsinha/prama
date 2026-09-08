"""Asking a model for a control, and not believing the answer.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.provenance import Origin
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.induce.llm import Induced, Inducer, retrieve
from prama.induce.validate import Gate, Rejection, Validator
from prama.llm.providers import ScriptedProvider
from prama.llm.spi import Request
from prama.pql.types import Catalogue
from prama.semantic.values import Grain, Optionality

CATALOGUE = Catalogue.of(positions={"side": "text", "qty": "number", "lei": "text"})
ROWS = [{"side": "BUY", "qty": 10, "lei": "5493001KJTIIGC8Y1R12"}] * 60


def declaration() -> DatasetDeclaration:
    return DatasetDeclaration(
        name="positions",
        purpose="the firm's end-of-day book, used for FRTB",
        grain=Grain(attributes=("lei",), statement="one row per counterparty"),
        attributes=(
            AttributeDeclaration(
                name="side",
                definition="whether the firm bought or sold",
                interpretation="always from the firm's perspective, never the client's",
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(name="qty"),
            AttributeDeclaration(name="lei", semantic_type="lei"),
        ),
    )


def inducer(answers: list[str], **kwargs: object) -> tuple[Inducer, ScriptedProvider]:
    provider = ScriptedProvider(answers, **kwargs)  # type: ignore[arg-type]
    return (
        Inducer(provider, Validator(catalogue=CATALOGUE)),
        provider,
    )


# -- retrieval ---------------------------------------------------------------


def test_the_prompt_carries_the_interpretation_and_not_just_the_schema() -> None:
    """ "Always from the firm's perspective" is the sentence that decides
    whether a sign control is right or backwards, and it exists in no schema
    anywhere."""
    declared = declaration()
    prompt = retrieve(declared, declared.attribute("side")).render()
    assert "always from the firm's perspective" in prompt
    assert "one row per counterparty" in prompt
    assert "the firm's end-of-day book" in prompt


def test_controls_already_in_force_are_named_so_they_are_not_re_proposed() -> None:
    prompt = retrieve(declaration(), existing=["CHECK positions.side IS NOT NULL"]).render()
    assert "do not repeat these" in prompt
    assert "CHECK positions.side IS NOT NULL" in prompt


# -- the pipeline ------------------------------------------------------------


def test_a_good_answer_becomes_an_induced_control() -> None:
    engine, _ = inducer(["CHECK positions.side IN ('BUY', 'SELL')"])
    outcome = engine.induce(retrieve(declaration()), "check the side is valid", ROWS)
    assert isinstance(outcome, Induced)
    assert outcome.attempts == 1
    assert outcome.provenance.origin is Origin.INDUCTION
    assert not outcome.provenance.origin.may_auto_activate


def test_a_bad_answer_is_retried_with_the_reason_quoted() -> None:
    """A retry with the identical prompt is a retry with the identical answer,
    at the same price."""
    engine, provider = inducer(["CHECK positions.nope IS NOT NULL", "CHECK positions.qty > 0"])
    outcome = engine.induce(retrieve(declaration()), "check the quantity", ROWS)
    assert isinstance(outcome, Induced)
    assert outcome.attempts == 2
    assert outcome.rejected[0].gate is Gate.TYPE_CHECK
    assert "rejected at the type_check stage" in provider.calls[1].prompt
    assert "nope" in provider.calls[1].prompt


def test_a_model_that_never_gets_it_right_yields_the_last_reason() -> None:
    engine, _ = inducer(["not pql", "still not pql", "nope"])
    outcome = engine.induce(retrieve(declaration()), "anything", ROWS)
    assert isinstance(outcome, Rejection)
    assert outcome.gate is Gate.PARSE


def test_a_model_declining_is_an_ordinary_outcome() -> None:
    """Every feature using this has a deterministic path that does not need
    it."""
    engine, _ = inducer(["NONE"])
    assert engine.induce(retrieve(declaration()), "something impossible", ROWS) is None


def test_a_vacuous_answer_never_reaches_a_reviewer() -> None:
    engine, _ = inducer(["CHECK positions.side MATCHES /.*/"] * 3)
    outcome = engine.induce(retrieve(declaration()), "check the side", ROWS)
    assert isinstance(outcome, Rejection)
    assert outcome.gate is Gate.COUNTERFACTUAL


# -- grammar -----------------------------------------------------------------


def test_a_grammar_is_offered_to_every_provider() -> None:
    """One that can constrain decoding uses it; one that cannot ignores the
    field, and the response records which happened."""
    engine, provider = inducer(["CHECK positions.qty > 0"])
    engine.induce(retrieve(declaration()), "check the quantity", ROWS)
    assert provider.calls[0].grammar is not None
    assert provider.calls[0].grammar.name == "pql_control"


def test_provenance_records_whether_the_grammar_was_actually_enforced() -> None:
    """A constrained provider emitting unparseable PQL is a provider bug worth
    reporting; an unconstrained one doing so is Tuesday."""
    constrained, _ = inducer(["CHECK positions.qty > 0"], supports_grammar=True)
    loose, _ = inducer(["CHECK positions.qty > 0"], supports_grammar=False)
    first = constrained.induce(retrieve(declaration()), "x", ROWS)
    second = loose.induce(retrieve(declaration()), "x", ROWS)
    assert isinstance(first, Induced) and isinstance(second, Induced)
    assert "enforced during decoding" in first.provenance.observations[0]
    assert "cannot constrain decoding" in second.provenance.observations[0]


# -- the published failure rate ----------------------------------------------


def test_the_generation_failure_rate_is_measured_and_reported() -> None:
    """A prompt whose output fails the gate half the time is a prompt somebody
    should fix, and without the number nobody knows."""
    answers = [
        "CHECK positions.qty > 0",
        "nonsense",
        "nonsense",
        "nonsense",
        "CHECK positions.side IN ('BUY', 'SELL')",
    ]
    engine, _ = inducer(answers)
    report = engine.induce_all(
        [
            (retrieve(declaration()), "check the quantity"),
            (retrieve(declaration()), "check something impossible"),
            (retrieve(declaration()), "check the side"),
        ],
        ROWS,
    )
    assert len(report.induced) == 2
    assert report.requested == 3
    assert report.generation_failure_rate == pytest.approx(1 / 3)
    assert report.failures_by_gate()["parse"] == 3
    assert "failure rate" in report.describe()


def test_the_report_separates_a_model_saying_no_from_a_model_being_wrong() -> None:
    engine, _ = inducer(["NONE", "nonsense", "nonsense", "nonsense"])
    report = engine.induce_all(
        [
            (retrieve(declaration()), "impossible"),
            (retrieve(declaration()), "also impossible"),
        ],
        ROWS,
    )
    assert report.declined == 1
    assert report.rejections


# -- what a request records --------------------------------------------------


def test_the_same_question_has_the_same_fingerprint() -> None:
    """Without it, "the model changed its mind" and "we asked something
    different" are indistinguishable and lead to opposite conclusions."""
    first = Request(system="s", prompt="p")
    assert first.fingerprint == Request(system="s", prompt="p").fingerprint
    assert first.fingerprint != Request(system="s", prompt="q").fingerprint
