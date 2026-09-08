"""Rules extracted from documents, with the passage they came from.

`FR-IND-012`. A data dictionary, a regulatory instruction, a filing manual —
the rules are already written down, in prose, in a PDF nobody has read since
the last audit. Extracting them is worth doing and is the single most
hallucination-prone thing in this system, because the output is plausible
whether or not the document says it.

**So the citation is checked, not collected.** A model asked to extract a rule
is also asked to quote the passage it came from, and the quote must appear
*verbatim in the document* or the rule is rejected. That turns the citation
from decoration into a test: a rule invented wholesale cannot produce a quote
that is really there, and a rule that misreads a real passage at least points
at the passage somebody can dispute.

It is not a complete defence — a model can quote a passage accurately and draw
the wrong rule from it — and it is not meant to be. It removes the failure
mode where the document is never opened and the rule is generated from the
model's memory of similar documents, which is the one that produces confident
rules about a regulation the customer does not report under.

**The document is hashed as read.** A rule whose source has changed underneath
it is not necessarily wrong, but it is no longer supported by what the citation
points at, and somebody should look.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Iterator, Sequence
from typing import Any

from prama.core.provenance import Citation, Origin, Provenance, identity
from prama.induce.llm import Retrieved
from prama.induce.validate import Gate, Rejection, Validated, Validator
from prama.llm.providers import PQL_CONTROL_GRAMMAR
from prama.llm.spi import ModelProvider, Request
from prama.semantic.values import Sensitivity

#: Passages shorter than this carry no rule. A heading is not an instruction.
MINIMUM_PASSAGE = 40

#: Words that mark a passage as normative rather than descriptive. Crude, and
#: crude is right: the cost of passing a descriptive passage to the model is
#: one call, and the cost of filtering out a normative one is a rule nobody
#: ever finds.
OBLIGATION_WORDS = (
    "must",
    "shall",
    "required",
    "mandatory",
    "may not",
    "cannot",
    "should not",
    "is not permitted",
    "at least",
    "no more than",
    "exactly",
    "always",
    "never",
)

SYSTEM = """\
You extract data quality rules from documents and express them in PQL.

You will be given one passage and the columns of a dataset. Reply with exactly
two things, in this order and nothing else:

QUOTE: the sentence from the passage that states the rule, copied exactly,
character for character. Do not paraphrase, tidy, or shorten it.
CONTROL: the PQL control.

If the passage states no rule about the columns you were given, reply with
exactly NONE. A passage describing what a field means is not a rule. Extracting
one anyway produces a control nobody asked for on a column somebody else owns.

The quote is checked against the document. A quote that is not in it verbatim
causes the rule to be discarded, however good the control is.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class Passage:
    """One piece of a document, and where in it."""

    text: str
    locator: str

    @property
    def looks_normative(self) -> bool:
        lowered = self.text.lower()
        return any(word in lowered for word in OBLIGATION_WORDS)


@dataclasses.dataclass(frozen=True, slots=True)
class Document:
    """A document as read, so a rule can point at it and be checked."""

    name: str
    text: str
    #: A URI, a filename, a document management id.
    reference: str = ""

    @property
    def content_hash(self) -> str:
        """The document exactly as it was when rules were drawn from it."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:32]

    def contains(self, quote: str) -> bool:
        """Whether a quote really appears here.

        Whitespace is normalised and nothing else. A model that reflows a
        sentence across lines has still quoted it; one that changes a word has
        not, and that difference is the whole check.
        """
        return _normalise(quote) in _normalise(self.text)

    def passages(self) -> Iterator[Passage]:
        """Split into paragraphs, numbered so a citation can point at one."""
        index = 0
        for block in re.split(r"\n\s*\n", self.text):
            cleaned = block.strip()
            if not cleaned:
                continue
            index += 1
            if len(cleaned) < MINIMUM_PASSAGE:
                continue
            yield Passage(text=cleaned, locator=self._locate(cleaned, index))

    @staticmethod
    def _locate(block: str, index: int) -> str:
        """A human-usable locator: a section number if the text has one.

        "Schedule H.1, field 23" sends somebody to the right page; "paragraph
        41" sends them to a scroll bar.
        """
        # ``field`` and ``item`` are here because they are what regulatory
        # instructions actually use — "Field 23" is the locator a reader will
        # search the PDF for, and an earlier pattern without them sent every
        # citation in a filing manual to "paragraph 3".
        heading = re.match(
            r"^((?:section|schedule|table|part|annex|paragraph|clause|field|item|line)"
            r"\s+[\w.\-]+|\d+(?:\.\d+)+)",
            block,
            re.IGNORECASE,
        )
        return heading.group(1) if heading else f"paragraph {index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "reference": self.reference,
            "content_hash": self.content_hash,
            "length": len(self.text),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Extracted:
    """A rule taken from a document, with the passage that supports it."""

    validated: Validated
    citation: Citation
    provenance: Provenance
    identity: str

    @property
    def content(self) -> str:
        return self.validated.content

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "validated": self.validated.to_dict(),
            "citation": self.citation.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ExtractionReport:
    document: str
    extracted: tuple[Extracted, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    #: Passages the model declined to draw a rule from. The healthy majority:
    #: most of a document describes rather than requires, and a extractor that
    #: found a rule in every paragraph would be inventing them.
    declined: int = 0
    #: Quotes that were not in the document. The number that matters, and the
    #: one nobody publishes.
    fabricated_quotes: int = 0
    considered: int = 0

    @property
    def fabrication_rate(self) -> float:
        return self.fabricated_quotes / self.considered if self.considered else 0.0

    def describe(self) -> str:
        return (
            f"{self.document}: {len(self.extracted)} rules from {self.considered} "
            f"normative passages; {self.declined} passages stated no rule; "
            f"{self.fabricated_quotes} answers cited a passage that is not in the "
            f"document ({self.fabrication_rate:.0%})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "extracted": [e.to_dict() for e in self.extracted],
            "rejections": [r.to_dict() for r in self.rejections],
            "declined": self.declined,
            "fabricated_quotes": self.fabricated_quotes,
            "fabrication_rate": round(self.fabrication_rate, 4),
            "considered": self.considered,
            "summary": self.describe(),
        }


class DocumentInducer:
    """Reads a document and proposes the rules it states."""

    def __init__(
        self,
        provider: ModelProvider,
        validator: Validator,
        *,
        system: str = SYSTEM,
    ) -> None:
        self._provider = provider
        self._validator = validator
        self._system = system

    def extract(
        self,
        document: Document,
        retrieved: Retrieved,
        rows: Sequence[dict[str, Any]] = (),
        *,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> ExtractionReport:
        extracted: list[Extracted] = []
        rejections: list[Rejection] = []
        declined = 0
        fabricated = 0
        considered = 0

        for passage in document.passages():
            if not passage.looks_normative:
                continue
            considered += 1
            response = self._provider.ask(
                Request(
                    system=self._system,
                    prompt=(
                        f"{retrieved.render()}\n\nPassage from {document.name}"
                        f" ({passage.locator}):\n{passage.text}"
                    ),
                    sensitivity=sensitivity,
                    grammar=PQL_CONTROL_GRAMMAR,
                    context={"document": document.name, "locator": passage.locator},
                )
            )
            if not response.ok or response.text.strip().upper() == "NONE":
                declined += 1
                continue

            quote, control_text = _split(response.text)
            if not quote or not control_text:
                rejections.append(
                    Rejection(
                        gate=Gate.PARSE,
                        detail=(
                            "the answer did not carry both a quote and a control, so "
                            "there is nothing to check the rule against"
                        ),
                        candidate=response.text,
                    )
                )
                continue

            if not document.contains(quote):
                # The check that turns the citation from decoration into a
                # test. A rule invented wholesale cannot produce a quote that
                # is really in the document.
                fabricated += 1
                continue

            outcome = self._validator.validate(control_text, rows)
            if isinstance(outcome, Rejection):
                rejections.append(outcome)
                continue

            citation = Citation(
                document=document.name,
                quote=quote,
                locator=passage.locator,
                document_hash=document.content_hash,
            )
            extracted.append(
                Extracted(
                    validated=outcome,
                    citation=citation,
                    identity=identity(
                        retrieved.dataset,
                        "induce.document",
                        document.reference or document.name,
                        outcome.content,
                    ),
                    provenance=Provenance(
                        origin=Origin.DOCUMENT,
                        rule="induce.document",
                        source_ref=document.reference or document.name,
                        statement=outcome.control.describe(),
                        citation=citation,
                        observations=(
                            f"the quoted passage appears verbatim in {document.name}",
                            f"document hash {document.content_hash} as read",
                        ),
                    ),
                )
            )

        return ExtractionReport(
            document=document.name,
            extracted=tuple(extracted),
            rejections=tuple(rejections),
            declined=declined,
            fabricated_quotes=fabricated,
            considered=considered,
        )


def stale_citations(extracted: Sequence[Extracted], document: Document) -> tuple[Extracted, ...]:
    """Rules whose source document has changed since they were drawn from it.

    Not necessarily wrong — most edits touch a different paragraph — but no
    longer supported by what the citation points at, which is a different
    thing from being wrong and needs a different response: somebody reads the
    new passage rather than deleting the rule.
    """
    return tuple(
        rule
        for rule in extracted
        if rule.citation.document == document.name
        and rule.citation.document_hash != document.content_hash
    )


def _split(text: str) -> tuple[str, str]:
    """Pull the quote and the control out of the model's answer."""
    quote_match = re.search(r"QUOTE:\s*(.+?)(?=\n\s*CONTROL:|\Z)", text, re.DOTALL)
    control_match = re.search(r"CONTROL:\s*(.+)", text, re.DOTALL)
    quote = quote_match.group(1).strip() if quote_match else ""
    control = control_match.group(1).strip() if control_match else ""
    return quote.strip('"“”'), control


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
