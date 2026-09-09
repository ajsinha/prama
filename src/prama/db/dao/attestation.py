"""Attestations: recorded, superseded, never edited.

The DAO has no update method and its ``delete`` refuses, for the same reason
the evidence ledger's does: the fact that somebody signed something is part of
the record, and a correction that overwrote the original would erase the more
interesting half of the history.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from sqlalchemy import select

from prama.core.errors import ConflictError, NotFoundError
from prama.db.dao.base import Dao
from prama.db.models.attestation import AttAttestation
from prama.report.attestation import Attestation, Coverage, Exception_


def _to_value(row: AttAttestation) -> Attestation:
    coverage = row.coverage_json or {}
    return Attestation(
        attester_id=row.attester_id,
        attester_name=row.attester_name,
        statement=row.statement,
        scope=row.scope,
        period_start=row.period_start,
        period_end=row.period_end,
        coverage=Coverage(
            controls_in_scope=int(coverage.get("controls_in_scope", 0)),
            controls_run=int(coverage.get("controls_run", 0)),
            passed=int(coverage.get("passed", 0)),
            failed=int(coverage.get("failed", 0)),
            not_established=int(coverage.get("not_established", 0)),
            errored=int(coverage.get("errored", 0)),
            never_ran=int(coverage.get("never_ran", 0)),
        ),
        evidence_root=row.evidence_root,
        evidence_records=row.evidence_records,
        exceptions=tuple(
            Exception_(
                control_id=str(item.get("control_id", "")),
                dataset=str(item.get("dataset", "")),
                verdict=str(item.get("verdict", "")),
                detail=str(item.get("detail", "")),
                disposition=str(item.get("disposition", "")),
            )
            for item in (row.exceptions_json or ())
        ),
        signed_at=row.signed_at,
        tenant_id=row.tenant_id,
        supersedes=row.supersedes or "",
        supersedes_because=row.supersedes_because,
        version=row.version,
    )


class AttestationDao(Dao[AttAttestation]):
    """Signed statements, in the order they were signed."""

    model = AttAttestation

    async def delete(self, entity: AttAttestation) -> None:
        """Refused. Overridden because the base DAO provides one.

        The fact that somebody signed something is part of the record. A
        correction supersedes; nothing is removed.
        """
        raise ConflictError(
            f"an attestation cannot be deleted (signed {entity.signed_at})",
            remedy=(
                "Sign a new one naming this as superseded, with the reason. The "
                "original stays, because the fact that it was signed is itself part "
                "of the record."
            ),
            context={"attestation": str(entity.id)},
        )

    async def sign(
        self, attestation: Attestation, *, seal: str, supersedes: str | None = None
    ) -> AttAttestation:
        """Record a signed attestation, optionally replacing an earlier one.

        The supersession is written on *both* rows: the new one names what it
        replaces, and the old one is marked so a reader who lands on it learns
        it was replaced rather than having to go looking for a newer one.
        """
        row = AttAttestation(
            tenant_id=attestation.tenant_id,
            attester_id=attestation.attester_id,
            attester_name=attestation.attester_name,
            statement=attestation.statement,
            scope=attestation.scope,
            period_start=attestation.period_start,
            period_end=attestation.period_end,
            coverage_json=attestation.coverage.to_dict(),
            exceptions_json=[item.to_dict() for item in attestation.exceptions],
            evidence_root=attestation.evidence_root,
            evidence_records=attestation.evidence_records,
            content_hash=attestation.content_hash,
            seal=seal,
            signed_at=attestation.signed_at,
            supersedes=supersedes,
            supersedes_because=attestation.supersedes_because,
            version=attestation.version,
        )
        self.add(row)
        await self._session.flush()

        if supersedes:
            earlier = await self.get(supersedes)
            if earlier is None:
                raise NotFoundError(
                    f"there is no attestation {supersedes!r} to supersede",
                    remedy="Check the identifier; nothing was replaced.",
                    context={"supersedes": supersedes},
                )
            # The only write to an existing row, and it adds a pointer rather
            # than changing anything the seal covers.
            earlier.superseded_by = str(row.id)
            await self._session.flush()
        return row

    async def current(self, tenant_id: str, *, limit: int = 200) -> list[AttAttestation]:
        """Attestations nothing has replaced, most recent period first."""
        await self._session.flush()
        stmt = (
            select(AttAttestation)
            .where(
                AttAttestation.tenant_id == tenant_id,
                AttAttestation.superseded_by.is_(None),
            )
            .order_by(AttAttestation.period_end.desc(), AttAttestation.signed_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def history(self, tenant_id: str, scope: str) -> list[AttAttestation]:
        """Everything ever signed for one scope, superseded rows included."""
        await self._session.flush()
        stmt = (
            select(AttAttestation)
            .where(AttAttestation.tenant_id == tenant_id, AttAttestation.scope == scope)
            .order_by(AttAttestation.signed_at)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def in_tenant(self, attestation_id: str, tenant_id: str) -> AttAttestation:
        """The attestation, provided it belongs to this tenant.

        A separate method rather than a check in the route, because it is the
        kind of check that gets written on one screen and forgotten on the next
        — and the screen it gets forgotten on is the one that prints the pack.
        A row belonging to somebody else is reported as absent, not as
        forbidden: which identifiers exist in another tenant is itself not this
        caller's business.
        """
        row = await self.require(attestation_id)
        if row.tenant_id != tenant_id:
            raise NotFoundError(
                f"there is no attestation {attestation_id!r}",
                remedy="Check the identifier against the attestation list.",
                context={"attestation": attestation_id},
            )
        return row

    async def value(self, attestation_id: str) -> Attestation:
        """The stored row as the value object, for verification and printing."""
        row = await self.require(attestation_id)
        return _to_value(row)

    async def verify(self, attestation_id: str, key: bytes) -> tuple[bool, bool]:
        """Whether the content still hashes to its stored hash, and the seal holds.

        Two answers, not one. A tampered row fails the first; a row sealed with
        a different key fails the second. Reporting a single boolean would make
        "somebody edited this" indistinguishable from "this came from another
        deployment", which are different incidents.
        """
        row = await self.require(attestation_id)
        rebuilt = _to_value(row)
        intact = rebuilt.content_hash == row.content_hash
        sealed = bool(row.seal) and intact and rebuilt.verify(key, row.seal)
        return intact, sealed
