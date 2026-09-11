"""How long evidence is kept, where, and how it is let go.

Evidence accumulates at the rate controls run and is kept for as long as a
regulator says. For a real estate that is millions of records a day held for
seven years, and the cost of that decides — quietly, in a spreadsheet nobody
shows anybody — whether evidence is affordable at all. So retention is tiered,
and the tiers are about *access*, not about importance.

* **Hot** — queryable. What a dashboard reads and an investigation starts from.
* **Warm** — compacted and slower. Still online, still verifiable, no longer
  indexed for interactive use.
* **Cold** — a WORM export in object storage with an immutability policy.
  Retrievable in hours, cheap in years, and the tier a regulator actually cares
  about because nothing can alter it including us.
* **Expired** — past its retention. Deleted, and the deletion is itself
  recorded, because a chain that shortens without explanation is
  indistinguishable from one that was tampered with.

The **WORM bundle** is the artefact that leaves. It is self-describing and
self-verifying: newline-delimited records, a manifest naming the period, the
count, the chain head, the Merkle root and the version of the verification
algorithm. Somebody handed one on a disk can check it with nothing but a
SHA-256 implementation, which is the whole point of the format.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from datetime import datetime
from typing import Any

from prama.core.clock import Clock, SystemClock
from prama.core.errors import ValidationError
from prama.core.pjson import dumps
from prama.evidence.ledger import Ledger, merkle_root, verify
from prama.evidence.record import EVIDENCE_VERSION, EvidenceRecord
from prama.security.egress import Gate

#: The version of the verification procedure a bundle was written under, so a
#: bundle opened in ten years names the algorithm that checks it.
BUNDLE_VERSION = "1.0"


class Tier(enum.Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    EXPIRED = "expired"

    @property
    def is_queryable(self) -> bool:
        return self is Tier.HOT

    @property
    def is_online(self) -> bool:
        return self in (Tier.HOT, Tier.WARM)

    @property
    def explanation(self) -> str:
        return {
            Tier.HOT: "queryable; what a dashboard reads and an investigation starts from",
            Tier.WARM: "online and verifiable, no longer indexed for interactive use",
            Tier.COLD: "a WORM export nothing can alter, including us",
            Tier.EXPIRED: "past its retention and deleted, with the deletion recorded",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long each tier holds, declared per tenant or per dataset class."""

    hot_days: int = 90
    warm_days: int = 365
    cold_days: int = 2555  # seven years
    #: Whether anything is deleted at all. A regulated estate often says no,
    #: and a policy that silently deleted because the default said so would be
    #: a compliance failure caused by a default.
    expire: bool = False

    def __post_init__(self) -> None:
        if not (self.hot_days <= self.warm_days <= self.cold_days):
            raise ValidationError(
                "the retention tiers are out of order",
                remedy=(
                    "Hot must be no longer than warm, and warm no longer than cold. "
                    "Evidence moves outward as it ages; it does not move back."
                ),
                context={
                    "hot": self.hot_days,
                    "warm": self.warm_days,
                    "cold": self.cold_days,
                },
            )

    def tier_at(self, age_days: float) -> Tier:
        if age_days <= self.hot_days:
            return Tier.HOT
        if age_days <= self.warm_days:
            return Tier.WARM
        if age_days <= self.cold_days or not self.expire:
            # Past cold and not expiring: it stays cold rather than
            # disappearing. A policy that deleted because it ran off the end of
            # its own table would be the worst kind of data loss — accidental,
            # silent and permanent.
            return Tier.COLD
        return Tier.EXPIRED

    def describe(self) -> str:
        ending = (
            f"and deleted after {self.cold_days:,} days"
            if self.expire
            else f"and kept indefinitely beyond {self.cold_days:,} days"
        )
        return (
            f"Queryable for {self.hot_days} days, online for {self.warm_days}, "
            f"in WORM storage thereafter, {ending}."
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Manifest:
    """What a bundle contains, and how to check it.

    Written beside the records rather than inside them, so a reader can see the
    shape of what they have before parsing a million lines — and so the count
    and the chain head are stated independently of the records they describe,
    which is what makes a truncated bundle detectable.
    """

    bundle_version: str = BUNDLE_VERSION
    evidence_version: str = EVIDENCE_VERSION
    tenant_id: str = ""
    from_sequence: int = 0
    to_sequence: int = 0
    records: int = 0
    erased: int = 0
    chain_head: str = ""
    merkle_root: str = ""
    #: SHA-256 of the records file, so the manifest and the records cannot
    #: drift apart without it being obvious.
    payload_digest: str = ""
    written_at: str = ""
    #: How to check it, in one sentence, for whoever opens this in ten years.
    verification: str = (
        "Each line is one JSON record. Recompute each record's content_hash as "
        "SHA-256 of its fields excluding previous_hash, content_hash and "
        "record_hash, serialised as JSON with keys sorted at every level and no "
        "insignificant whitespace. Recompute record_hash as SHA-256 of the ASCII "
        "concatenation of previous_hash and content_hash. Each record's "
        "previous_hash must equal the previous record's record_hash; the first "
        "must be sixty-four zeros. A record carrying a tombstone has had its "
        "content erased: its stored content_hash is the hash the content had, "
        "and only its place in the chain can be checked."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_version": self.bundle_version,
            "evidence_version": self.evidence_version,
            "tenant_id": self.tenant_id,
            "from_sequence": self.from_sequence,
            "to_sequence": self.to_sequence,
            "records": self.records,
            "erased": self.erased,
            "chain_head": self.chain_head,
            "merkle_root": self.merkle_root,
            "payload_digest": self.payload_digest,
            "written_at": self.written_at,
            "verification": self.verification,
        }

    def to_json(self) -> str:
        return dumps(self.to_dict(), sort_keys=True, indent=True)


@dataclasses.dataclass(frozen=True, slots=True)
class Bundle:
    """A period of evidence, ready to be written somewhere nothing can alter it."""

    manifest: Manifest
    payload: str

    @property
    def size_bytes(self) -> int:
        return len(self.payload.encode("utf-8"))

    def files(self) -> dict[str, str]:
        """What to write, by name. Two files, so neither can hide the other."""
        return {"manifest.json": self.manifest.to_json(), "evidence.ndjson": self.payload}

    def check(self) -> tuple[bool, str]:
        """Whether this bundle is internally consistent.

        Checks the manifest against the payload as well as the chain, because
        the failure that matters for an archive is not a forged record — it is
        a truncated file, and only the manifest's count reveals that.
        """
        import json

        lines = [line for line in self.payload.splitlines() if line.strip()]
        if len(lines) != self.manifest.records:
            return (
                False,
                f"the manifest says {self.manifest.records} record(s) and the file "
                f"holds {len(lines)}; this bundle is incomplete",
            )
        digest = hashlib.sha256(self.payload.encode("utf-8")).hexdigest()
        if digest != self.manifest.payload_digest:
            return False, "the records do not match the digest in the manifest"
        result = verify(json.loads(line) for line in lines)
        if not result.is_intact:
            return False, result.render()
        if result.head != self.manifest.chain_head:
            return False, "the chain head does not match the manifest"
        return True, (
            f"{self.manifest.records} record(s), chain intact, Merkle root "
            f"{self.manifest.merkle_root[:16]}…"
        )


class Archivist:
    """Moves evidence outward as it ages, and packages what leaves."""

    def __init__(
        self, policy: RetentionPolicy | None = None, *, clock: Clock | None = None
    ) -> None:
        self._policy = policy or RetentionPolicy()
        self._clock = clock or SystemClock()

    @property
    def policy(self) -> RetentionPolicy:
        return self._policy

    def tier_of(self, record: EvidenceRecord) -> Tier:
        """Where this record belongs today."""
        if not record.finished_at:
            return Tier.HOT
        try:
            written = datetime.fromisoformat(record.finished_at)
        except ValueError:
            # A record whose timestamp cannot be read stays hot rather than
            # being aged out on a guess. Deleting evidence because its date did
            # not parse is not a trade anybody would make deliberately.
            return Tier.HOT
        age = (self._clock.now() - written).total_seconds() / 86400
        return self._policy.tier_at(age)

    def plan(self, ledger: Ledger) -> dict[str, list[EvidenceRecord]]:
        """What sits in each tier now."""
        tiers: dict[str, list[EvidenceRecord]] = {t.value: [] for t in Tier}
        for record in ledger:
            tiers[self.tier_of(record).value].append(record)
        return tiers

    def bundle(
        self,
        records: list[EvidenceRecord],
        *,
        tenant_id: str = "",
        gate: Gate | None = None,
        archive_region: str = "",
        jurisdiction: str = "",
    ) -> Bundle:
        """Package records for WORM storage.

        ``gate`` is the residency check, applied here rather than at whatever
        writes the archive: this is the last point that knows whose evidence
        this is and what period it covers. Refused wholesale — a bundle missing
        the records that could not cross would verify perfectly and be missing
        records, which is the one failure the manifest's count exists to catch.
        """
        if gate is not None:
            gate.require(
                "evidence-export",
                destination=archive_region,
                jurisdiction=jurisdiction,
                subject=f"the evidence bundle for {tenant_id or 'this tenant'}",
            )
        if not records:
            raise ValidationError(
                "there is nothing to bundle",
                remedy=(
                    "Bundle a period that contains evidence. An empty bundle would "
                    "look like a period in which nothing ran, which is a different "
                    "and much more alarming claim."
                ),
            )
        payload = "\n".join(r.to_json() for r in records)
        chain = verify(r.to_dict() for r in records)
        return Bundle(
            manifest=Manifest(
                tenant_id=tenant_id,
                from_sequence=records[0].sequence,
                to_sequence=records[-1].sequence,
                records=len(records),
                erased=sum(1 for r in records if r.is_erased),
                chain_head=chain.head,
                merkle_root=merkle_root([r.record_hash for r in records]),
                payload_digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                written_at=self._clock.now().isoformat(),
            ),
            payload=payload,
        )

    def erase(
        self,
        ledger: Ledger,
        sequences: list[int],
        *,
        by: str,
        authority: str = "",
    ) -> list[EvidenceRecord]:
        """Satisfy a right-to-erasure request without breaking the chain.

        Returns the whole ledger's records with the named ones tombstoned. The
        caller writes them back, because whether an erasure is applied to hot
        storage alone or propagated into WORM bundles already written is a
        legal question and not one this class should answer by default.
        """
        wanted = set(sequences)
        at = self._clock.now().isoformat()
        return [
            r.erase(by=by, authority=authority, at=at) if r.sequence in wanted else r
            for r in ledger
        ]

    def report(self, ledger: Ledger) -> dict[str, Any]:
        tiers = self.plan(ledger)
        return {
            "policy": self._policy.describe(),
            "counts": {name: len(records) for name, records in tiers.items()},
            "erased": sum(1 for r in ledger if r.is_erased),
            "summary": (
                f"{len(ledger)} record(s): "
                + ", ".join(f"{len(records)} {name}" for name, records in tiers.items() if records)
                + f". {self._policy.describe()}"
            ),
        }
