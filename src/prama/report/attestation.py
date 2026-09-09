"""Attestation: a named person's statement about a period, and its seal.

The artefact an RDARR or SOX-style sign-off actually requires, and the one
demonstration that closes deals. It is also the easiest thing in this product
to make dishonest, so most of this file is about what an attestation is not
allowed to leave out.

**What it is.** A person says: *I have reviewed the controls on this scope for
this period.* That is the whole claim. It is not "the data was correct" and it
is not "everything passed" — an attestation over an estate with failures is a
perfectly valid attestation, because the attester is signing that they looked,
not that they liked what they saw.

**What it must name, or it is unfalsifiable.**

* The exact **scope and period**. "The controls were fine" with no boundary is
  a sentence nobody can check and nobody can be held to.
* The **Merkle root** of the evidence it covers. Without it the attestation
  floats free of the records, and evidence written afterwards is
  indistinguishable from evidence written before.
* What did **not** pass, and what did not **run**. An attestation over 40%
  coverage that does not say 40% is worse than no attestation: it converts an
  unexamined estate into a signed one.

**Immutability.** A signed attestation is never edited. A correction is a new
attestation that supersedes it, carrying the reason — because the fact that
somebody signed the first one is itself part of the record.

**On the word "signed".** The seal is an HMAC over the content hash. It says
*this was sealed by a holder of the key*, and it says nothing at all to
somebody who does not hold the key. An asymmetric signature would say more;
this does not, and the distinction is stated here rather than left for a
regulator to discover.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
from typing import Any

from prama.core.pjson import canonical

#: Bumped only when the meaning of a field changes. An attestation names the
#: version it was made under, so one from 2026 is still read the way it was
#: written after the format has moved on.
ATTESTATION_VERSION = "1.0"


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    """How much of the scope was actually examined.

    Every number here is one an attester would rather not print, which is
    exactly why the format requires them. A sign-off over an estate whose
    controls half failed to execute is a sign-off over the half that ran, and
    the difference has to be on the page.
    """

    controls_in_scope: int
    controls_run: int
    passed: int
    failed: int
    #: Ran, and could not establish a verdict — a screen without its residual.
    not_established: int = 0
    #: Did not run at all: the source refused, the control would not compile.
    errored: int = 0
    #: Live controls no pass reached, because nothing scheduled them.
    never_ran: int = 0

    @property
    def rate(self) -> float:
        """The share of scope that produced a verdict at all."""
        return self.controls_run / self.controls_in_scope if self.controls_in_scope else 0.0

    @property
    def is_complete(self) -> bool:
        return self.controls_run == self.controls_in_scope and self.controls_in_scope > 0

    @property
    def is_clean(self) -> bool:
        """Whether everything that ran, passed.

        Deliberately *not* the same question as whether the attestation can be
        signed. It can be signed either way; the reader needs to know which.
        """
        return self.failed == 0 and self.errored == 0 and self.not_established == 0

    def describe(self) -> str:
        parts = [f"{self.controls_run} of {self.controls_in_scope} control(s) produced a verdict"]
        if not self.is_complete:
            parts.append(f"this covers {self.rate:.0%} of the scope")
        parts.append(f"{self.passed} passed")
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.not_established:
            parts.append(f"{self.not_established} could not be established")
        if self.errored:
            parts.append(f"{self.errored} could not be executed")
        if self.never_ran:
            parts.append(f"{self.never_ran} never ran at all")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {**dataclasses.asdict(self), "rate": round(self.rate, 6)}


@dataclasses.dataclass(frozen=True, slots=True)
class Exception_:  # noqa: N801 - trailing underscore avoids shadowing the builtin
    """One thing the attester is signing *despite*.

    Named ``Exception_`` because that is the word the audit world uses and the
    word a reader will look for. Every failure and every unestablished control
    in the period appears here — an attestation that summarised them into a
    count would be asking somebody to sign for things they were not shown.
    """

    control_id: str
    dataset: str
    verdict: str
    detail: str = ""
    #: What the attester said about it. Blank is permitted and is itself
    #: informative: an exception signed without a word is one nobody explained.
    disposition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class Attestation:
    """One person's statement about one scope for one period."""

    #: Who is signing. Not a role — a person. A control attested by "the team"
    #: is a control nobody attested.
    attester_id: str
    attester_name: str
    #: What they are attesting to. A sentence in their own words, kept verbatim
    #: and printed on the artefact.
    statement: str
    scope: str
    period_start: str
    period_end: str
    coverage: Coverage
    #: The Merkle root of the evidence records in the period. This is what ties
    #: the signature to the facts: without it the attestation floats free, and
    #: evidence written afterwards is indistinguishable from evidence written
    #: before.
    evidence_root: str
    evidence_records: int
    exceptions: tuple[Exception_, ...] = ()
    signed_at: str = ""
    tenant_id: str = ""
    #: Set when this replaces an earlier attestation. A signed attestation is
    #: never edited: the fact that somebody signed the first one is part of the
    #: record.
    supersedes: str = ""
    supersedes_because: str = ""
    version: str = ATTESTATION_VERSION

    def content(self) -> dict[str, Any]:
        """Everything the seal covers.

        Every field except the seal itself. Nothing is left out for
        convenience: a field outside the hash is a field somebody can change
        after the signature, which is the only thing a signature is for.
        """
        return {
            "version": self.version,
            "attester_id": self.attester_id,
            "attester_name": self.attester_name,
            "statement": self.statement,
            "scope": self.scope,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "coverage": self.coverage.to_dict(),
            "evidence_root": self.evidence_root,
            "evidence_records": self.evidence_records,
            "exceptions": [item.to_dict() for item in self.exceptions],
            "signed_at": self.signed_at,
            "tenant_id": self.tenant_id,
            "supersedes": self.supersedes,
            "supersedes_because": self.supersedes_because,
        }

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(canonical(self.content())).hexdigest()

    @property
    def is_clean(self) -> bool:
        return self.coverage.is_clean and not self.exceptions

    @property
    def is_qualified(self) -> bool:
        """Whether this sign-off carries exceptions or incomplete coverage.

        The word an auditor uses, and the distinction that matters: a qualified
        attestation is still an attestation. Presenting one as unqualified is
        the fraud; refusing to allow one would simply mean nobody attests.
        """
        return not self.is_clean or not self.coverage.is_complete

    def seal(self, key: bytes) -> str:
        """An HMAC over the content hash.

        Says: this content was sealed by a holder of the key. It says nothing
        to somebody who does not hold the key — an asymmetric signature would,
        and calling this "signed" without that sentence would let the word
        imply more than it delivers.
        """
        return hmac.new(key, self.content_hash.encode("ascii"), hashlib.sha256).hexdigest()

    def verify(self, key: bytes, seal: str) -> bool:
        return hmac.compare_digest(self.seal(key), seal)

    def describe(self) -> str:
        """The attestation as a sentence, qualified where it should be."""
        qualifier = "with exceptions" if self.is_qualified else "without exception"
        return (
            f"{self.attester_name} attests, {qualifier}, that they reviewed "
            f"{self.scope} for {self.period_start} to {self.period_end}. "
            f"{self.coverage.describe()}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content(),
            "content_hash": self.content_hash,
            "is_qualified": self.is_qualified,
            "summary": self.describe(),
        }
