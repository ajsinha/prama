"""The bitemporal access protocol.

Four operations, and the distinction between two of them is the whole reason
this machinery exists:

* **create** — the first version of a declaration.
* **amend** — *the world changed.* The grain really was one thing until 1 April
  and something else afterwards. Closes the current validity period and opens a
  new one. Both versions remain true, of their own periods.
* **correct** — *we were wrong.* The grain was never what we recorded. Supersedes
  the current version without touching validity, so the mistaken belief remains
  visible in the transaction-time axis. An evidence record produced while the
  mistake stood still resolves to the mistaken version, which is what makes the
  replay honest.
* **read** — at any point on either axis.

Conflating amend and correct is the single most common bitemporal defect, and it
is unrecoverable after the fact: once the distinction is lost, no query can tell
a genuine historical change from a data-entry error.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import select

from prama.core.clock import utc_now
from prama.core.errors import ConflictError, NotFoundError
from prama.db.dao.base import Dao
from prama.db.models import Base
from prama.db.temporal import Provenance, TemporalQuery, Versioned

#: The identity model: a stable row that never changes.
E = TypeVar("E", bound=Base)
#: The version model. Bound to ``Versioned`` rather than ``Base`` so the temporal
#: columns are visible to the type checker — every version model inherits both,
#: and it is the temporal half that this class actually manipulates.
V = TypeVar("V", bound=Versioned)


class VersionedDao(Dao[E], Generic[E, V]):
    """Bitemporal access for one identity/version model pair.

    Subclasses declare the pair and the foreign-key column that joins them;
    everything else — versioning, supersession, temporal reads, history — is
    inherited, so the protocol cannot be implemented slightly differently for
    each object type.
    """

    version_model: type[V]
    #: Attribute on the version model that points at the identity row.
    entity_key: str
    #: Column on the identity model carrying the tenant.
    tenant_key: str = "tenant_id"

    # -- creation ----------------------------------------------------------

    async def create(
        self,
        *,
        tenant_id: str,
        identity_fields: dict[str, Any] | None = None,
        provenance: Provenance | None = None,
        valid_from: datetime | None = None,
        **declaration: Any,
    ) -> tuple[E, V]:
        """Create an identity and its first version."""
        now = utc_now()
        entity = self.model(tenant_id=tenant_id, created_at=now, **(identity_fields or {}))
        self._session.add(entity)
        await self._guarded_flush()

        # Reached dynamically: this class is generic over model pairs it never
        # imports, so the constructors and the identity column are not statically
        # known here even though every concrete pair provides them.
        version = cast(
            V,
            cast(Any, self.version_model)(
                version=1,
                valid_from=valid_from or now,
                recorded_at=now,
                **{self.entity_key: cast(Any, entity).id},
                **declaration,
            ),
        )
        (provenance or Provenance()).apply_to(version)
        self._session.add(version)
        await self._guarded_flush()
        return entity, version

    # -- change ------------------------------------------------------------

    async def amend(
        self,
        entity_id: str,
        *,
        tenant_id: str,
        provenance: Provenance | None = None,
        effective_from: datetime | None = None,
        **changes: Any,
    ) -> V:
        """Record that the world changed.

        The current version's validity is closed at *effective_from* and a new
        version opens there. Both remain believed: neither was ever wrong.
        """
        current = await self.current(entity_id, tenant_id=tenant_id)
        if current is None:
            raise NotFoundError(
                f"{self.model.__name__} {entity_id!r} has no current version to amend",
                remedy="Create the declaration before amending it.",
                context={"entity": entity_id},
            )
        now = utc_now()
        effective = effective_from or now
        if effective < current.valid_from:
            raise ConflictError(
                "an amendment cannot take effect before the version it replaces began",
                remedy=(
                    "Choose a later effective date, or correct the earlier version instead "
                    "if it was simply wrong."
                ),
                context={
                    "entity": entity_id,
                    "effective_from": effective.isoformat(),
                    "current_valid_from": current.valid_from.isoformat(),
                },
            )
        current.valid_to = effective
        # Close the old version *before* the successor is inserted. The schema's
        # partial unique index permits exactly one current row per entity, and
        # the flush order is otherwise the ORM's business rather than ours.
        await self._guarded_flush()
        successor = self._clone(current, version=current.version + 1, changes=changes)
        successor.valid_from = effective
        successor.valid_to = None
        successor.recorded_at = now
        successor.superseded_at = None
        (provenance or Provenance()).apply_to(successor)
        self._session.add(successor)
        await self._guarded_flush()
        return successor

    async def correct(
        self,
        entity_id: str,
        *,
        tenant_id: str,
        provenance: Provenance | None = None,
        **changes: Any,
    ) -> V:
        """Record that we were wrong.

        The current version is superseded — we stop believing it — while its
        validity period is inherited unchanged by the correction. The mistaken
        version stays queryable on the transaction-time axis, which is what lets
        an evidence record from before the correction still resolve to what was
        believed when it ran.
        """
        current = await self.current(entity_id, tenant_id=tenant_id)
        if current is None:
            raise NotFoundError(
                f"{self.model.__name__} {entity_id!r} has no current version to correct",
                remedy="Create the declaration before correcting it.",
                context={"entity": entity_id},
            )
        now = utc_now()
        current.superseded_at = now
        await self._guarded_flush()  # see amend(): one current row at a time
        corrected = self._clone(current, version=current.version + 1, changes=changes)
        corrected.valid_from = current.valid_from
        corrected.valid_to = current.valid_to
        corrected.recorded_at = now
        corrected.superseded_at = None
        (provenance or Provenance()).apply_to(corrected)
        self._session.add(corrected)
        await self._guarded_flush()
        return corrected

    async def retire(
        self, entity_id: str, *, tenant_id: str, provenance: Provenance | None = None
    ) -> V | None:
        """End a declaration's validity without deleting anything.

        Nothing in the semantic layer is ever destroyed: a retired dataset's
        history is still needed to interpret evidence produced while it existed.
        """
        current = await self.current(entity_id, tenant_id=tenant_id)
        if current is None:
            return None
        current.valid_to = utc_now()
        if provenance is not None:
            current.change_reason = provenance.reason
        await self._guarded_flush()
        return current

    # -- reads -------------------------------------------------------------

    def _scoped(self, entity_id: str, tenant_id: str) -> Any:
        """The base select for one entity, restricted to one tenant.

        The tenant lives on the identity row, not the version row, so every
        by-id read joins back to it. Doing that here rather than in each method
        is the point: a scope you have to remember is not a scope. See
        ``docs/reviews/2026-09-11-adversarial-review.md`` finding S2 — these
        methods previously took only an id, so any caller holding an
        identifier from another estate read and wrote another tenant's rows.
        """
        return (
            select(self.version_model)
            .join(
                self.model,
                self._identity_id == getattr(self.version_model, self.entity_key),
            )
            .where(
                getattr(self.version_model, self.entity_key) == entity_id,
                getattr(self.model, self.tenant_key) == tenant_id,
            )
        )

    async def tenant_of(self, entity_id: str) -> str | None:
        """Which estate owns this entity, or ``None`` if it does not exist.

        A *derivation*, not a check. The scoped reads below answer "may this
        caller see it"; this one answers "whose is it", and is for the trusted
        local paths — the CLI — that operate on an identifier without having
        been told a tenant. Never use it to satisfy a caller-supplied
        ``tenant_id``: that turns the scope into a tautology.
        """
        stmt = select(getattr(self.model, self.tenant_key)).where(self._identity_id == entity_id)
        return cast(str | None, (await self._session.execute(stmt)).scalars().one_or_none())

    async def current(self, entity_id: str, *, tenant_id: str) -> V | None:
        """The present declaration: still true, still believed."""
        await self._guarded_flush()
        stmt = TemporalQuery.current(self._scoped(entity_id, tenant_id), self.version_model)
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def require_current(self, entity_id: str, *, tenant_id: str) -> V:
        version = await self.current(entity_id, tenant_id=tenant_id)
        if version is None:
            raise NotFoundError(
                f"{self.model.__name__} {entity_id!r} has no current version",
                remedy="Check the identifier, or list the declared objects first.",
                context={"entity": entity_id},
            )
        return version

    async def valid_at(self, entity_id: str, moment: datetime, *, tenant_id: str) -> V | None:
        """What we believe *today* was true at *moment*."""
        await self._guarded_flush()
        stmt = TemporalQuery.believed_now_valid_at(
            self._scoped(entity_id, tenant_id), self.version_model, moment
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def as_of(
        self, entity_id: str, valid_at: datetime, known_at: datetime, *, tenant_id: str
    ) -> V | None:
        """True at *valid_at*, as believed at *known_at*.

        The question an evidence replay asks, and the only one that gives an
        honest answer about a control that ran before a correction.
        """
        await self._guarded_flush()
        stmt = TemporalQuery.as_of(
            self._scoped(entity_id, tenant_id), self.version_model, valid_at, known_at
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def history(self, entity_id: str, *, tenant_id: str) -> list[V]:
        """Every version, oldest first — the audit view."""
        await self._guarded_flush()
        stmt = TemporalQuery.all_versions(self._scoped(entity_id, tenant_id), self.version_model)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_current(self, tenant_id: str, *, limit: int = 100, offset: int = 0) -> list[V]:
        """Current versions of every entity in a tenant."""
        await self._guarded_flush()
        stmt = (
            TemporalQuery.current(
                select(self.version_model)
                .join(
                    self.model,
                    self._identity_id == getattr(self.version_model, self.entity_key),
                )
                .where(getattr(self.model, self.tenant_key) == tenant_id),
                self.version_model,
            )
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_current(self, tenant_id: str) -> int:
        await self._guarded_flush()
        stmt = TemporalQuery.current(
            select(self.version_model)
            .join(
                self.model,
                self._identity_id == getattr(self.version_model, self.entity_key),
            )
            .where(getattr(self.model, self.tenant_key) == tenant_id),
            self.version_model,
        )
        return await self.count(stmt)

    # -- internals ---------------------------------------------------------

    @property
    def _identity_id(self) -> Any:
        """The identity model's primary-key column.

        Reached dynamically because this class is generic over model pairs it
        does not import; every identity model carries ``id`` from
        ``UlidPrimaryKey``.
        """
        return self.model.id  # type: ignore[attr-defined]

    def _clone(self, source: V, *, version: int, changes: dict[str, Any]) -> V:
        """Copy a version's declaration, applying *changes*.

        Copying rather than mutating is what makes the store append-only. The
        bitemporal and identity columns are excluded and set by the caller,
        because getting one of them wrong here would be invisible and permanent.
        """
        excluded = {
            "id",
            "version",
            "valid_from",
            "valid_to",
            "recorded_at",
            "superseded_at",
            "authored_by",
            "approved_by",
            "approved_at",
            "change_reason",
        }
        table = cast(Any, source).__table__
        fields = {
            column.name: getattr(source, column.name)
            for column in table.columns
            if column.name not in excluded
        }
        unknown = set(changes) - set(fields)
        if unknown:
            raise ConflictError(
                f"unknown field(s) for {self.version_model.__name__}: {sorted(unknown)}",
                remedy="Check the field names; a typo here would silently change nothing.",
                context={"unknown": sorted(unknown)},
            )
        fields.update(changes)
        clone = cast(V, cast(Any, self.version_model)(**fields))
        clone.version = version
        return clone


def is_versioned(model: type[Any]) -> bool:
    """Whether *model* carries the bitemporal columns."""
    return issubclass(model, Versioned)
