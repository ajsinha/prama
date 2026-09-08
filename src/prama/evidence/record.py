"""The immutable fact: what was checked, against what data, and what was found.

An evidence record is the artefact a regulator, an auditor or a sceptical
colleague is actually shown. Everything else in Prama exists to produce it, and
two properties decide whether it is worth anything.

**It must be verifiable without Prama.** An audit trail that can only be checked
by the tool that wrote it is not an audit trail; it is the tool's own account of
itself. So a record is plain JSON with a documented hash, and the verification
is short enough to be reimplemented from the description in an afternoon — the
test suite does exactly that, in stdlib alone, and requires the two to agree.

**It must be small.** Evidence accumulates at the rate controls run, which for a
real estate is millions of records a day, kept for seven years. A record that
carried its failing rows inline would be a hundred times larger and the
retention cost would decide, quietly, that evidence is not affordable. So the
record holds counts and identities; the *samples* are a separate artefact,
referenced by hash and expiring on their own schedule.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

from prama.core.pjson import canonical

#: Bumped only when the *meaning* of a field changes. A record names the version
#: it was written under, so a record from 2026 is still read the way it was
#: written after the format has moved on.
EVIDENCE_VERSION = "1.0"

#: The hash a chain starts from. Sixty-four zeros, so a reader can tell the
#: first record from a record whose parent is missing.
GENESIS = "0" * 64

#: How much of an error's explanation the record keeps. Enough to name the
#: cause, not enough for a stack trace to crowd out the evidence.
DETAIL_LIMIT = 300


@dataclasses.dataclass(frozen=True, slots=True)
class SnapshotRef:
    """What data state was read, as the source described it."""

    kind: str = "wall_clock"
    identifier: str = ""
    exact: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "identifier": self.identifier, "exact": self.exact}


@dataclasses.dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """One control, one scope, one moment. Append-only and hash-linked."""

    #: Position in the chain. Contiguous, so a missing record is visible as a
    #: gap rather than only as a broken hash.
    sequence: int = 0
    #: The plan that ran — a content hash, so the record names what was
    #: checked and not merely which control row pointed at it.
    plan_id: str = ""
    #: The control declaration this plan came from, and its version.
    control_id: str = ""
    control_version: int = 1
    dataset: str = ""
    binding: str = ""
    snapshot: SnapshotRef = dataclasses.field(default_factory=SnapshotRef)
    #: What the run supplied. Part of the record because a control's verdict
    #: depends on it, and a replay that guessed them would be replaying a
    #: different control.
    parameters: dict[str, str] = dataclasses.field(default_factory=dict)
    engine: str = ""
    verdict: str = "error"
    metrics: dict[str, float] = dataclasses.field(default_factory=dict)
    #: Where the failing rows went, if they were kept. A hash, not the rows.
    samples_digest: str = ""
    sample_count: int = 0
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    #: Who or what caused this run.
    triggered_by: str = "schedule"
    tenant_id: str = ""
    #: Why, when the verdict is an error. Bounded, because a driver's stack
    #: trace would be several kilobytes and the record has a two-kilobyte
    #: budget — but present, because "error" with no reason is a verdict
    #: nobody can act on.
    detail: str = ""
    #: The previous record's ``record_hash``. GENESIS for the first.
    previous_hash: str = GENESIS
    evidence_version: str = EVIDENCE_VERSION

    # -- hashing -----------------------------------------------------------

    def content(self) -> dict[str, Any]:
        """Everything the hash covers.

        Every field except the hashes themselves. Nothing is excluded for
        convenience: a field left out of the hash is a field somebody can
        change without detection, and the whole point of the record is that
        nobody can.
        """
        return {
            "evidence_version": self.evidence_version,
            "sequence": self.sequence,
            "plan_id": self.plan_id,
            "control_id": self.control_id,
            "control_version": self.control_version,
            "dataset": self.dataset,
            "binding": self.binding,
            "snapshot": self.snapshot.to_dict(),
            "parameters": dict(sorted(self.parameters.items())),
            "engine": self.engine,
            "verdict": self.verdict,
            "metrics": {k: _number(v) for k, v in sorted(self.metrics.items())},
            "samples_digest": self.samples_digest,
            "sample_count": self.sample_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "triggered_by": self.triggered_by,
            "tenant_id": self.tenant_id,
            "detail": self.detail[:DETAIL_LIMIT],
        }

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(canonical(self.content())).hexdigest()

    @property
    def record_hash(self) -> str:
        """The link. ``sha256(previous_hash || content_hash)``, hex, ASCII.

        Deliberately the simplest construction that chains: concatenate the two
        hex digests and hash the ASCII. Anything cleverer would be a detail
        somebody reimplementing the verification could get wrong, and a
        verification that is hard to reproduce is one nobody performs.
        """
        return hashlib.sha256((self.previous_hash + self.content_hash).encode("ascii")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content(),
            "previous_hash": self.previous_hash,
            "content_hash": self.content_hash,
            "record_hash": self.record_hash,
        }

    def to_json(self) -> str:
        from prama.core.pjson import dumps

        return dumps(self.to_dict(), sort_keys=True)

    @property
    def size_bytes(self) -> int:
        return len(self.to_json().encode("utf-8"))

    # -- reading back ------------------------------------------------------

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceRecord:
        snapshot = payload.get("snapshot") or {}
        return cls(
            sequence=int(payload.get("sequence", 0)),
            plan_id=str(payload.get("plan_id", "")),
            control_id=str(payload.get("control_id", "")),
            control_version=int(payload.get("control_version", 1)),
            dataset=str(payload.get("dataset", "")),
            binding=str(payload.get("binding", "")),
            snapshot=SnapshotRef(
                kind=str(snapshot.get("kind", "wall_clock")),
                identifier=str(snapshot.get("identifier", "")),
                exact=bool(snapshot.get("exact", False)),
            ),
            parameters={str(k): str(v) for k, v in (payload.get("parameters") or {}).items()},
            engine=str(payload.get("engine", "")),
            verdict=str(payload.get("verdict", "error")),
            metrics={str(k): float(v) for k, v in (payload.get("metrics") or {}).items()},
            samples_digest=str(payload.get("samples_digest", "")),
            sample_count=int(payload.get("sample_count", 0)),
            started_at=str(payload.get("started_at", "")),
            finished_at=str(payload.get("finished_at", "")),
            duration_ms=int(payload.get("duration_ms", 0)),
            triggered_by=str(payload.get("triggered_by", "schedule")),
            tenant_id=str(payload.get("tenant_id", "")),
            detail=str(payload.get("detail", "")),
            previous_hash=str(payload.get("previous_hash", GENESIS)),
            evidence_version=str(payload.get("evidence_version", EVIDENCE_VERSION)),
        )


def _number(value: Any) -> float | int:
    """Metrics as the narrowest exact form.

    A count written as 8.0 and the same count written as 8 must hash the same,
    or an evidence chain breaks when a driver changes how it returns integers —
    which has nothing to do with the data and everything to do with a library
    upgrade.
    """
    number = float(value)
    return int(number) if number.is_integer() else number
