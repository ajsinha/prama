"""Why a control exists, in a form that can be shown to its owner.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.provenance import (
    Citation,
    Origin,
    Provenance,
    content_hash,
    identity,
)


def test_a_declaration_outranks_everything_that_merely_observes() -> None:
    """A person stating a fact about their business outranks a miner stating a
    fact about one snapshot of data."""
    assert Origin.DECLARATION.authority > Origin.DOCUMENT.authority
    assert Origin.DOCUMENT.authority > Origin.MINING.authority
    assert Origin.MINING.authority > Origin.INDUCTION.authority


def test_only_a_declaration_may_run_without_review() -> None:
    """Mining is right about the data and silent about the intent. A column
    that happens to be unique in today's extract is not a declared key, and
    enforcing it turns the first legitimate duplicate into an incident."""
    assert Origin.DECLARATION.may_auto_activate
    for origin in Origin:
        if origin is not Origin.DECLARATION:
            assert not origin.may_auto_activate, origin


def test_the_sentence_names_the_person_and_the_day() -> None:
    provenance = Provenance(
        origin=Origin.DECLARATION,
        rule="grain.uniqueness",
        statement="one position per account per business day",
        declared_by="a.sinha",
        declared_at="2026-03-04T09:12:00Z",
    )
    sentence = provenance.sentence()
    assert "a.sinha declared it on 2026-03-04" in sentence
    assert "one position per account per business day" in sentence


def test_corroboration_is_kept_rather_than_deduplicated_away() -> None:
    """The most interesting thing that can happen here: mining agreeing with a
    declaration is independent evidence the declaration is true. A steward
    reading that approves in a second."""
    declared = Provenance(origin=Origin.DECLARATION, rule="grain.uniqueness")
    mined = Provenance(origin=Origin.MINING, rule="ucc")
    combined = declared.corroborated_by(mined, "unique across 4.2m rows in today's extract")
    assert combined.is_corroborated
    assert "independently confirmed" in combined.sentence()
    assert "4.2m rows" in combined.sentence()


def test_corroboration_from_one_origin_is_recorded_once() -> None:
    declared = Provenance(origin=Origin.DECLARATION, rule="x")
    mined = Provenance(origin=Origin.MINING, rule="y")
    twice = declared.corroborated_by(mined, "a").corroborated_by(mined, "b")
    assert len(twice.corroborations) == 1


def test_a_document_rule_must_carry_the_passage_it_came_from() -> None:
    """A rule extracted from a regulatory instruction without the sentence it
    came from is unfalsifiable: nobody can check it, so nobody will trust it,
    so it will not be approved."""
    with pytest.raises(ValueError, match="passage it came from"):
        Provenance(origin=Origin.DOCUMENT, rule="doc.extract")


def test_a_citation_quotes_rather_than_paraphrases() -> None:
    """A paraphrase is the model's reading, and the reading is exactly what is
    in dispute."""
    citation = Citation(
        document="FR Y-14Q instructions",
        quote="Report the legal entity identifier of the obligor.",
        locator="Schedule H.1, field 23",
    )
    rendered = Provenance(origin=Origin.DOCUMENT, rule="doc.extract", citation=citation).sentence()
    assert "Schedule H.1, field 23" in rendered
    assert "legal entity identifier of the obligor" in rendered


def test_identity_survives_an_edit_and_the_content_hash_does_not() -> None:
    """Identity from the text would orphan a control on every edit, and the
    review queue would fill with controls that already exist."""
    same = identity("DS01", "grain.uniqueness", "positions", "account_id")
    assert same == identity("DS01", "grain.uniqueness", "positions", "account_id")
    assert same != identity("DS01", "grain.uniqueness", "positions", "book_id")
    assert content_hash("CHECK a") != content_hash("CHECK b")


def test_provenance_survives_a_round_trip() -> None:
    original = Provenance(
        origin=Origin.DOCUMENT,
        rule="doc.extract",
        citation=Citation(document="d", quote="q", locator="l", document_hash="h"),
        observations=("seen in 99.4% of rows",),
    ).corroborated_by(Provenance(origin=Origin.MINING, rule="m"), "holds in the data")
    assert Provenance.from_dict(original.to_dict()) == original
