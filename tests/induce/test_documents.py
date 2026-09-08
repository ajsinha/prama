"""Rules from documents, and the citation that makes them checkable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.core.provenance import Origin
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.induce.documents import Document, DocumentInducer, stale_citations
from prama.induce.llm import retrieve
from prama.induce.validate import Validator
from prama.llm.providers import ScriptedProvider
from prama.pql.types import Catalogue

TEXT = """\
Schedule H.1 Corporate Loan Data

This schedule collects loan-level data for the corporate portfolio.

Field 23 Obligor LEI. The reporting entity must report the legal entity
identifier of the obligor. This field shall not be left blank for any
outstanding facility.

Field 24 Obligor Name. The name of the obligor as recorded in the reporting
entity's systems. This is provided for reconciliation purposes.
"""

CATALOGUE = Catalogue.of(loans={"obligor_lei": "text", "obligor_name": "text"})
ROWS = [{"obligor_lei": "5493001KJTIIGC8Y1R12", "obligor_name": "X"}] * 60


def declaration() -> DatasetDeclaration:
    return DatasetDeclaration(
        name="loans",
        attributes=(
            AttributeDeclaration(name="obligor_lei", semantic_type="lei"),
            AttributeDeclaration(name="obligor_name"),
        ),
    )


def document() -> Document:
    return Document(name="FR Y-14Q instructions", text=TEXT, reference="fry14q-2026")


def inducer(answers: list[str]) -> DocumentInducer:
    return DocumentInducer(ScriptedProvider(answers), Validator(catalogue=CATALOGUE))


def test_a_document_is_split_into_locatable_passages() -> None:
    """ "Schedule H.1" sends somebody to the right page; "paragraph 41" sends
    them to a scroll bar."""
    locators = [p.locator for p in document().passages()]
    # "Field 23" is what a reader will search the PDF for.
    assert "Field 23" in locators
    assert "Field 24" in locators


def test_only_normative_passages_are_put_to_the_model() -> None:
    """A passage describing what a field means is not a rule, and extracting
    one anyway produces a control nobody asked for on a column somebody else
    owns."""
    normative = [p for p in document().passages() if p.looks_normative]
    assert len(normative) == 1
    assert "must report" in normative[0].text


def test_a_rule_whose_quote_is_really_in_the_document_is_extracted() -> None:
    answer = (
        "QUOTE: This field shall not be left blank for any outstanding facility.\n"
        "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
    )
    report = inducer([answer]).extract(document(), retrieve(declaration()), ROWS)
    assert len(report.extracted) == 1
    extracted = report.extracted[0]
    assert extracted.provenance.origin is Origin.DOCUMENT
    assert "shall not be left blank" in extracted.citation.quote
    assert extracted.citation.locator


def test_a_quote_that_is_not_in_the_document_discards_the_rule() -> None:
    """The check that turns the citation from decoration into a test. A rule
    invented wholesale cannot produce a quote that is really there."""
    answer = (
        "QUOTE: The obligor LEI must be validated against the GLEIF register daily.\n"
        "CONTROL: CHECK loans.obligor_lei IS VALID 'lei'"
    )
    report = inducer([answer]).extract(document(), retrieve(declaration()), ROWS)
    assert not report.extracted
    assert report.fabricated_quotes == 1
    assert report.fabrication_rate == 1.0


def test_a_reflowed_quote_still_counts_as_quoted() -> None:
    """A model that wraps a sentence across lines has still quoted it; one that
    changes a word has not, and that difference is the whole check."""
    answer = (
        "QUOTE: This field shall   not be left\n  blank for any outstanding facility.\n"
        "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
    )
    report = inducer([answer]).extract(document(), retrieve(declaration()), ROWS)
    assert len(report.extracted) == 1


def test_an_answer_with_no_quote_is_rejected_rather_than_trusted() -> None:
    report = inducer(["CHECK loans.obligor_lei IS NOT NULL"]).extract(
        document(), retrieve(declaration()), ROWS
    )
    assert not report.extracted
    assert "nothing to check the rule against" in report.rejections[0].detail


def test_a_rule_that_passes_the_citation_check_still_passes_every_gate() -> None:
    """A quote being real says nothing about whether the control compiles."""
    answer = (
        "QUOTE: This field shall not be left blank for any outstanding facility.\n"
        "CONTROL: CHECK loans.nonexistent IS NOT NULL"
    )
    report = inducer([answer]).extract(document(), retrieve(declaration()), ROWS)
    assert not report.extracted
    assert report.rejections


def test_the_fabrication_rate_is_published() -> None:
    """The number that matters, and the one nobody publishes."""
    report = inducer(["QUOTE: invented\nCONTROL: CHECK loans.obligor_lei IS NOT NULL"]).extract(
        document(), retrieve(declaration()), ROWS
    )
    assert "cited a passage that is not in the document" in report.describe()


def test_declining_is_the_healthy_majority_outcome() -> None:
    """Most of a document describes rather than requires, and an extractor that
    found a rule in every paragraph would be inventing them."""
    report = inducer(["NONE"]).extract(document(), retrieve(declaration()), ROWS)
    assert report.declined == 1
    assert not report.extracted


def test_a_rule_whose_source_has_changed_is_flagged_rather_than_deleted() -> None:
    """No longer supported by what the citation points at is a different thing
    from wrong, and needs a different response."""
    answer = (
        "QUOTE: This field shall not be left blank for any outstanding facility.\n"
        "CONTROL: CHECK loans.obligor_lei IS NOT NULL"
    )
    report = inducer([answer]).extract(document(), retrieve(declaration()), ROWS)
    amended = Document(
        name="FR Y-14Q instructions",
        text=TEXT + "\n\nField 25 has been added.",
        reference="fry14q-2026",
    )
    assert stale_citations(report.extracted, amended) == report.extracted
    assert stale_citations(report.extracted, document()) == ()
