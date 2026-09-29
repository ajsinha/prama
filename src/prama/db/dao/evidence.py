"""The evidence ledger's access layer.

Append-only, and the appending is the interesting part. Three things have to be
true at once and only one of them can be enforced by the caller:

* **The chain must not fork.** Two writers appending at the same moment must
  not both claim sequence *n*. That is enforced by a unique index on
  ``(tenant_id, sequence)``, so the loser gets an integrity error rather than a
  ledger with two records in the same position — a condition no later
  verification can repair, because both records are internally consistent.
* **The caller must not choose the link.** Sequence and previous hash are set
  here, from the current head, exactly as :class:`prama.evidence.ledger.Ledger`
  does it. A caller that could choose them could write a record that looked
  linked and was not.
* **The hashes must be stored, not recomputed.** A reader has to be able to
  detect that stored content no longer hashes to its stored hash. Recomputing
  on read would make tampering invisible, which is the one failure this whole
  subsystem exists to prevent.

There is no update method and no delete method. Erasure is the single exception
and it is not a delete: content is blanked, the original content hash is kept,
and the chain still verifies across the gap.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from sqlalchemy import func, select

from prama.core.errors import ConflictError, NotFoundError
from prama.db.dao.base import Dao
from prama.db.models.evidence import EvAnchor, EvRecord, EvRun, EvSample
from prama.evidence.ledger import Verification, verify
from prama.evidence.record import GENESIS, EvidenceRecord, SnapshotRef, Tombstone


def _as_stored(row: EvRecord) -> dict[str, Any]:
    """A row in the exact shape :func:`prama.evidence.ledger.verify` consumes.

    The content fields come from the row and the three hashes come from their
    stored columns. That combination is the whole point: verification compares
    what is stored against what the stored content hashes to, and a mismatch is
    the only signal that a row has been altered underneath the platform.

    Going through :class:`EvidenceRecord` here instead would be a silent
    disaster. Its ``content_hash`` is a *computed property*, so a reconstructed
    record hashes whatever it currently holds — tampered content included — and
    every check would pass. That defect was written, shipped into this file,
    and caught by the tampering test below; the test exists because the mistake
    is this easy to make.
    """
    record = _to_record(row)
    payload: dict[str, Any] = {
        **record.content(),
        "previous_hash": row.previous_hash,
        "content_hash": row.content_hash,
        "record_hash": row.record_hash,
    }
    if row.tombstone_json:
        payload["tombstone"] = dict(row.tombstone_json)
    return payload


def _to_record(row: EvRecord) -> EvidenceRecord:
    """A stored row as the domain object, for reading and display.

    Not for verification: see :func:`_as_stored`. The hashes on the object
    returned here are recomputed from its content, which is right for a record
    the platform just built and wrong for one it just read.
    """
    snapshot = row.snapshot_json or {}
    return EvidenceRecord(
        sequence=row.sequence,
        plan_id=row.plan_id,
        control_id=row.control_id,
        control_version=row.control_version,
        dataset=row.dataset,
        binding=row.binding,
        snapshot=SnapshotRef(
            kind=str(snapshot.get("kind", "wall_clock")),
            identifier=str(snapshot.get("identifier", "")),
            exact=bool(snapshot.get("exact", False)),
        ),
        parameters={str(k): str(v) for k, v in (row.parameters_json or {}).items()},
        engine=row.engine,
        coverage=row.coverage,
        verdict=row.verdict,
        metrics={str(k): float(v) for k, v in (row.metrics_json or {}).items()},
        samples_digest=row.samples_digest,
        sample_count=row.sample_count,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        triggered_by=row.triggered_by,
        tenant_id=row.tenant_id,
        detail=row.detail,
        dimensions=tuple(row.dimensions_json or ()),
        criticality=row.criticality,
        tombstone=Tombstone.from_dict(row.tombstone_json) if row.tombstone_json else None,
        previous_hash=row.previous_hash,
        evidence_version=row.evidence_version,
    )


def _to_row(record: EvidenceRecord, *, run_id: str | None) -> EvRecord:
    return EvRecord(
        tenant_id=record.tenant_id,
        sequence=record.sequence,
        run_id=run_id,
        plan_id=record.plan_id,
        control_id=record.control_id,
        control_version=record.control_version,
        dataset=record.dataset,
        binding=record.binding,
        snapshot_json=record.snapshot.to_dict(),
        parameters_json=dict(record.parameters),
        engine=record.engine,
        coverage=record.coverage,
        verdict=record.verdict,
        metrics_json=dict(record.metrics),
        samples_digest=record.samples_digest,
        sample_count=record.sample_count,
        started_at=record.started_at,
        finished_at=record.finished_at,
        duration_ms=record.duration_ms,
        triggered_by=record.triggered_by,
        detail=record.detail,
        dimensions_json=list(record.dimensions),
        criticality=record.criticality,
        tombstone_json=record.tombstone.to_dict() if record.tombstone else None,
        previous_hash=record.previous_hash,
        content_hash=record.content_hash,
        record_hash=record.record_hash,
        evidence_version=record.evidence_version,
    )


class EvidenceDao(Dao[EvRecord]):
    """The chain, in the database."""

    model = EvRecord

    async def delete(self, entity: EvRecord) -> None:
        """Refused. Overridden because the base DAO provides one.

        This is the hole the append-only guarantee would otherwise have: a
        method inherited from ``Dao`` that nobody wrote for this class, that
        does exactly what a caller under time pressure wants, and that would
        look entirely reasonable in review. Deleting a record breaks every hash
        after it, so the answer is never "delete" — it is either erase, which
        keeps the chain, or archive-then-truncate under a retention policy,
        which moves the whole prefix at once.
        """
        raise ConflictError(
            f"an evidence record cannot be deleted (sequence {entity.sequence})",
            remedy=(
                "Deleting one record breaks every hash after it. To satisfy a "
                "right-to-erasure request use erase(), which blanks the content and "
                "keeps the chain verifiable. To reclaim space, archive the prefix "
                "under the retention policy."
            ),
            context={"sequence": entity.sequence, "tenant": entity.tenant_id},
        )

    # -- appending ---------------------------------------------------------

    async def head(self, tenant_id: str) -> str:
        """The hash everything so far reduces to, or GENESIS."""
        await self._session.flush()
        stmt = (
            select(EvRecord.record_hash)
            .where(EvRecord.tenant_id == tenant_id)
            .order_by(EvRecord.sequence.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() or GENESIS

    async def next_sequence(self, tenant_id: str) -> int:
        await self._session.flush()
        stmt = select(func.max(EvRecord.sequence)).where(EvRecord.tenant_id == tenant_id)
        highest = (await self._session.execute(stmt)).scalar_one_or_none()
        return 0 if highest is None else int(highest) + 1

    async def append(
        self, record: EvidenceRecord, *, tenant_id: str = "", run_id: str | None = None
    ) -> EvidenceRecord:
        """Link a record to the current head and store it.

        The sequence and previous hash are taken from the ledger, never from
        the caller. If two writers race, the unique index on
        ``(tenant_id, sequence)`` makes one of them fail — which is the right
        outcome: a forked chain is a condition no later verification can
        repair, because both branches are internally consistent.
        """
        tenant = tenant_id or record.tenant_id
        if not tenant:
            raise ConflictError(
                "an evidence record needs a tenant",
                remedy="Every chain is per-tenant; supply the tenant it belongs to.",
            )
        linked = dataclasses.replace(
            record,
            tenant_id=tenant,
            sequence=await self.next_sequence(tenant),
            previous_hash=await self.head(tenant),
        )
        self.add(_to_row(linked, run_id=run_id))
        await self._session.flush()
        return linked

    async def extend(
        self,
        records: list[EvidenceRecord],
        *,
        tenant_id: str = "",
        run_id: str | None = None,
    ) -> list[EvidenceRecord]:
        return [await self.append(r, tenant_id=tenant_id, run_id=run_id) for r in records]

    # -- reading -----------------------------------------------------------

    async def chain(self, tenant_id: str, *, limit: int = 10000) -> list[EvidenceRecord]:
        """The chain in sequence order, which is the only order it verifies in."""
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(EvRecord.tenant_id == tenant_id)
            .order_by(EvRecord.sequence)
            .limit(limit)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def as_stored(self, tenant_id: str, *, limit: int = 10000) -> list[dict[str, Any]]:
        """The chain as it is stored, for verification and for export.

        Distinct from :meth:`chain` on purpose. ``chain`` returns domain
        objects whose hashes are recomputed; this returns the stored hashes
        alongside the stored content, which is the only form in which tampering
        can be detected.
        """
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(EvRecord.tenant_id == tenant_id)
            .order_by(EvRecord.sequence)
            .limit(limit)
        )
        return [_as_stored(row) for row in (await self._session.execute(stmt)).scalars()]

    async def verify(self, tenant_id: str) -> Verification:
        """Check the chain as stored. The question an auditor actually asks."""
        return verify(await self.as_stored(tenant_id))

    async def in_period(self, tenant_id: str, start: str, end: str) -> list[EvidenceRecord]:
        """Records finished within a period, in sequence order.

        Sequence order rather than time order, because that is the order the
        chain links in and therefore the order a Merkle root over them has to
        be built in. Sorting by timestamp would give a different root for the
        same set whenever two records finished in the same second.
        """
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(
                EvRecord.tenant_id == tenant_id,
                EvRecord.finished_at >= start,
                EvRecord.finished_at <= end,
            )
            .order_by(EvRecord.sequence)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def period_root(self, tenant_id: str, start: str, end: str) -> tuple[str, int]:
        """One hash standing for a period's evidence, and how many records it covers.

        The hash an attestation binds itself to. Published somewhere Prama
        cannot reach, it turns "our records are internally consistent" into
        "our records are what they were when this was signed".
        """
        from prama.evidence.ledger import merkle_root

        records = await self.in_period(tenant_id, start, end)
        return merkle_root([record.record_hash for record in records]), len(records)

    async def since(self, tenant_id: str, sequence: int) -> list[EvidenceRecord]:
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(EvRecord.tenant_id == tenant_id, EvRecord.sequence >= sequence)
            .order_by(EvRecord.sequence)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def for_dataset(
        self, tenant_id: str, dataset: str, *, limit: int = 500
    ) -> list[EvidenceRecord]:
        """Most recent first: what a person looking at a dataset wants."""
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(EvRecord.tenant_id == tenant_id, EvRecord.dataset == dataset)
            .order_by(EvRecord.finished_at.desc(), EvRecord.sequence.desc())
            .limit(limit)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def for_control(
        self, control_id: str, *, tenant_id: str, limit: int = 500
    ) -> list[EvidenceRecord]:
        """This estate's evidence for one control, newest first.

        The tenant is required, and this is why: the by-parent reads on these
        DAOs took a parent id and nothing else, so a caller holding an
        identifier from another estate read that estate's rows in full — a 200
        with the data, not a 404 (QA finding F-02, and this method in round 2).
        The tenant sweep in `tests/security/test_tenant_isolation.py` could not
        see it, because it probes methods whose *first* parameter is
        `tenant_id`, and this one had no tenant parameter at all.

        An evidence record carries `detail`, which is the sampled data that
        explains a verdict. It is the most confidential thing the product
        stores, so a read of it is the last place an estate boundary should be
        optional.
        """
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(EvRecord.control_id == control_id, EvRecord.tenant_id == tenant_id)
            .order_by(EvRecord.finished_at.desc(), EvRecord.sequence.desc())
            .limit(limit)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def for_run(self, run_id: str, *, tenant_id: str) -> list[EvidenceRecord]:
        """This estate's evidence from one run, in sequence order.

        Scoped for the same reason as :meth:`for_control`.
        """
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(EvRecord.run_id == run_id, EvRecord.tenant_id == tenant_id)
            .order_by(EvRecord.sequence)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def search(
        self,
        tenant_id: str,
        *,
        control_id: str | None = None,
        dataset: str | None = None,
        verdict: str | None = None,
        run_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvidenceRecord]:
        """This estate's records matching every filter given, newest first.

        ``since`` and ``until`` bound ``finished_at``, inclusively, as ISO-8601
        text — which sorts chronologically, so the comparison is the database's.
        """
        await self._session.flush()
        stmt = select(EvRecord).where(EvRecord.tenant_id == tenant_id)
        if control_id:
            stmt = stmt.where(EvRecord.control_id == control_id)
        if dataset:
            stmt = stmt.where(EvRecord.dataset == dataset)
        if verdict:
            stmt = stmt.where(EvRecord.verdict == verdict)
        if run_id:
            stmt = stmt.where(EvRecord.run_id == run_id)
        if since:
            stmt = stmt.where(EvRecord.finished_at >= since)
        if until:
            stmt = stmt.where(EvRecord.finished_at <= until)
        stmt = stmt.order_by(EvRecord.sequence.desc()).limit(limit).offset(offset)
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def at(self, tenant_id: str, sequence: int) -> EvidenceRecord | None:
        """This estate's record at one position, for reading; None if there is none."""
        row = await self.row_at(tenant_id, sequence)
        return None if row is None else _to_record(row)

    async def failing(self, tenant_id: str, *, limit: int = 200) -> list[EvidenceRecord]:
        """Records whose verdict is not a pass.

        ``error`` and ``skipped`` are included with ``fail`` on purpose: a
        control that could not run has no verdict, and a list of "problems"
        that quietly omitted it would report the controls that did run as
        though they were all of them.
        """
        await self._session.flush()
        stmt = (
            select(EvRecord)
            .where(
                EvRecord.tenant_id == tenant_id,
                EvRecord.verdict.in_(("fail", "error", "skipped", "indeterminate")),
            )
            .order_by(EvRecord.finished_at.desc(), EvRecord.sequence.desc())
            .limit(limit)
        )
        return [_to_record(row) for row in (await self._session.execute(stmt)).scalars()]

    async def count_for(self, tenant_id: str) -> int:
        """How many records this tenant's chain holds.

        Named apart from the base ``count`` rather than overriding it: the
        base takes a statement and this takes a tenant, and a subclass that
        changes what a shared name means is a subclass whose callers get the
        wrong one without noticing.
        """
        await self._session.flush()
        stmt = select(func.count()).select_from(EvRecord).where(EvRecord.tenant_id == tenant_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def last_run_at(self, tenant_id: str) -> dict[str, str]:
        """When each control last produced a record, by control id.

        Every record counts, including errors: a control that has been failing
        to execute every hour has *run* every hour, and treating it as never
        run would make the scheduler retry it continuously while the source is
        down — turning one broken control into a load problem.
        """
        await self._session.flush()
        stmt = (
            select(EvRecord.control_id, func.max(EvRecord.finished_at))
            .where(EvRecord.tenant_id == tenant_id, EvRecord.control_id != "")
            .group_by(EvRecord.control_id)
        )
        return {
            str(control_id): str(finished)
            for control_id, finished in (await self._session.execute(stmt)).all()
            if finished
        }

    async def latest_per_control(self, tenant_id: str) -> dict[str, EvidenceRecord]:
        """The current state of each control, and only the current one.

        A scorecard built from every record would weight a control that runs
        hourly sixty times as heavily as one that runs daily, which measures
        the schedule rather than the data.
        """
        latest: dict[str, EvidenceRecord] = {}
        for record in await self.chain(tenant_id):
            key = record.control_id or record.plan_id
            if not key:
                continue
            existing = latest.get(key)
            if existing is None or record.sequence > existing.sequence:
                latest[key] = record
        return latest

    # -- erasure -----------------------------------------------------------

    async def row_at(self, tenant_id: str, sequence: int) -> EvRecord | None:
        """The stored row at one position.

        Exposed because erasure needs it and because a caller verifying a chain
        needs to compare stored hashes against stored content — which requires
        the row, not the reconstructed record.
        """
        await self._session.flush()
        stmt = select(EvRecord).where(
            EvRecord.tenant_id == tenant_id, EvRecord.sequence == sequence
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def erase(
        self, tenant_id: str, sequence: int, *, by: str, authority: str = "", at: str = ""
    ) -> EvidenceRecord:
        """Blank a record's content, keeping the chain intact.

        The only write path that touches an existing row, and it is not a
        delete: the original content hash is preserved, so everything before
        and after still links and the erasure is visible as a tombstone rather
        than as a hole nobody can account for.
        """
        row = await self.row_at(tenant_id, sequence)
        if row is None:
            raise NotFoundError(
                f"there is no evidence record at sequence {sequence}",
                remedy="Check the sequence; a gap is itself a finding worth investigating.",
                context={"tenant": tenant_id, "sequence": sequence},
            )
        erased = _to_record(row).erase(by=by, authority=authority, at=at)
        row.plan_id = erased.plan_id
        row.control_id = erased.control_id
        row.dataset = erased.dataset
        row.binding = erased.binding
        row.snapshot_json = erased.snapshot.to_dict()
        row.parameters_json = {}
        row.metrics_json = {}
        row.samples_digest = ""
        row.sample_count = 0
        row.detail = ""
        row.tombstone_json = erased.tombstone.to_dict() if erased.tombstone else None
        # Untouched on purpose. The chain is built from these, and rewriting
        # them would break every record after this one to satisfy one request.
        assert row.content_hash == erased.content_hash
        assert row.record_hash == erased.record_hash
        await self._session.flush()
        return erased


class EvidenceRunDao(Dao[EvRun]):
    """Executions, so "last night's run" is a thing that can be named."""

    model = EvRun

    async def start(
        self,
        *,
        tenant_id: str,
        triggered_by: str = "schedule",
        actor_id: str | None = None,
        engine: str = "",
        started_at: str = "",
    ) -> EvRun:
        run = EvRun(
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            actor_id=actor_id,
            engine=engine,
            started_at=started_at,
            status="running",
        )
        self.add(run)
        await self._session.flush()
        return run

    async def finish(
        self, run_id: str, *, finished_at: str, status: str = "complete", detail: str = ""
    ) -> EvRun:
        run = await self.require(run_id)
        run.finished_at = finished_at
        run.status = status
        run.detail = detail
        run.record_count = await self._count_records(run_id)
        await self._session.flush()
        return run

    async def _count_records(self, run_id: str) -> int:
        stmt = select(func.count()).select_from(EvRecord).where(EvRecord.run_id == run_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def recent(self, tenant_id: str, *, limit: int = 50) -> list[EvRun]:
        await self._session.flush()
        stmt = (
            select(EvRun)
            .where(EvRun.tenant_id == tenant_id)
            .order_by(EvRun.started_at.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def unfinished(self, tenant_id: str) -> list[EvRun]:
        """Runs that started and never reported.

        A first-class query rather than an operational curiosity: their
        controls have no verdict, and every screen built on "the latest
        evidence" is silently missing them.
        """
        await self._session.flush()
        stmt = (
            select(EvRun)
            .where(EvRun.tenant_id == tenant_id, EvRun.status == "running")
            .order_by(EvRun.started_at)
        )
        return list((await self._session.execute(stmt)).scalars())


class SampleDao(Dao[EvSample]):
    """Failing rows, on their own retention clock."""

    model = EvSample

    async def put(
        self,
        *,
        tenant_id: str,
        digest: str,
        rows: list[dict[str, Any]],
        masked: tuple[str, ...] = (),
        created_at: str,
        expires_at: str | None = None,
    ) -> EvSample:
        """Store a sample set, or return the one already stored.

        The digest is the identity, so the same failing rows recorded twice are
        one set. Overwriting would be equally correct and strictly worse: it
        would reset the expiry clock on personal data every time the same
        failure recurred.
        """
        existing = await self.get(digest)
        if existing is not None:
            return existing
        sample = EvSample(
            digest=digest,
            tenant_id=tenant_id,
            rows_json=rows,
            masked_json=list(masked),
            row_count=len(rows),
            created_at=created_at,
            expires_at=expires_at,
        )
        self.add(sample)
        await self._session.flush()
        return sample

    async def expired(self, now: str) -> list[EvSample]:
        await self._session.flush()
        stmt = select(EvSample).where(EvSample.expires_at.is_not(None), EvSample.expires_at <= now)
        return list((await self._session.execute(stmt)).scalars())

    async def forget(self, digest: str) -> bool:
        """Delete one sample set.

        Deleting samples is allowed where deleting records is not, and the
        asymmetry is the point: the rows are the personal data and the record
        is the audit trail. A record whose samples have expired still says
        truthfully that a control failed and how many rows failed it — it
        simply can no longer show which.
        """
        sample = await self.get(digest)
        if sample is None:
            return False
        await self._session.delete(sample)
        await self._session.flush()
        return True


class AnchorDao(Dao[EvAnchor]):
    """Receipts from a witness outside Prama, beside the chain they witness."""

    model = EvAnchor

    async def record(
        self,
        *,
        tenant_id: str,
        sequence: int,
        digest: str,
        kind: str,
        authority: str,
        status: str,
        requested_at: str,
        witnessed_at: str | None = None,
        token: str = "",
        detail: str = "",
    ) -> EvAnchor:
        row = EvAnchor(
            tenant_id=tenant_id,
            sequence=sequence,
            digest=digest,
            kind=kind,
            authority=authority,
            status=status,
            requested_at=requested_at,
            witnessed_at=witnessed_at,
            token=token,
            detail=detail,
        )
        self.add(row)
        await self._session.flush()
        return row

    async def at(self, tenant_id: str, sequence: int) -> EvAnchor | None:
        """The latest attempt at a position, anchored or not."""
        stmt = (
            select(EvAnchor)
            .where(EvAnchor.tenant_id == tenant_id, EvAnchor.sequence == sequence)
            .order_by(EvAnchor.requested_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def for_tenant(
        self, tenant_id: str, *, first: int = 0, last: int | None = None
    ) -> list[EvAnchor]:
        """Every attempt, in chain order, optionally within a range of positions."""
        stmt = select(EvAnchor).where(EvAnchor.tenant_id == tenant_id, EvAnchor.sequence >= first)
        if last is not None:
            stmt = stmt.where(EvAnchor.sequence <= last)
        stmt = stmt.order_by(EvAnchor.sequence, EvAnchor.requested_at)
        return list((await self._session.execute(stmt)).scalars())
