"""Sessions and the unit of work.

A ``UnitOfWork`` owns one transaction and the repositories that act within it.
Services take a unit of work, not a session: they never see SQLAlchemy, which is
what keeps the layering test honest, and they cannot accidentally commit half of
a change because commit is the boundary's decision, not theirs.

    async with database.unit_of_work() as uow:
        tenant = await uow.tenants.get(tenant_id)
        await uow.audit.record(event)
        # commit on clean exit, rollback on any exception

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from prama.core.errors import DatabaseError
from prama.core.log import get_logger
from prama.db.engine import EngineFactory

if TYPE_CHECKING:
    from prama.db.dao import (
        AnchorDao,
        ApiKeyDao,
        AttestationDao,
        AttributeDao,
        AuditDao,
        BindingDao,
        BreakDao,
        ConceptDao,
        ConceptPropertyDao,
        ConnectionDao,
        ControlDao,
        DatasetDao,
        DomainDao,
        EvidenceDao,
        EvidenceRunDao,
        JourneyDao,
        PrincipalDao,
        RejectionDao,
        RelationshipDao,
        RoleDao,
        SampleDao,
        SettingDao,
        TenantDao,
    )
    from prama.db.dao.alert import AlertDao
    from prama.db.dao.code import CodeDao
    from prama.db.dao.comment import CommentDao
    from prama.db.dao.delegate import DelegateUploadDao
    from prama.db.dao.fleet import FleetDao
    from prama.db.dao.glossary import GlossaryDao
    from prama.db.dao.lineage import LineageDao
    from prama.db.dao.llm import LlmDao
    from prama.db.dao.llm_governance import LlmGovernanceDao
    from prama.db.dao.metadata import MetadataDao
    from prama.db.dao.semantic_index import SemanticIndexDao
    from prama.db.dao.steward import StewardDao
    from prama.db.dao.usage import UsageDao

_log = get_logger(__name__)


class SessionManager:
    """Creates async sessions bound to the configured engine."""

    def __init__(self, factory: EngineFactory) -> None:
        self._factory = factory
        self._maker: async_sessionmaker[AsyncSession] | None = None

    def maker(self) -> async_sessionmaker[AsyncSession]:
        if self._maker is None:
            self._maker = async_sessionmaker(
                bind=self._factory.async_engine(),
                expire_on_commit=False,  # objects stay usable after the boundary closes
                autoflush=False,  # flush is explicit; surprise SQL is a debugging tax
            )
        return self._maker

    def session(self) -> AsyncSession:
        return self.maker()()


class UnitOfWork:
    """One transaction, and the DAOs that act inside it.

    DAOs are created lazily and cached, so a unit of work that touches one
    table does not construct six objects. Services receive a unit of work and
    never a session, which is what keeps SQLAlchemy confined to this package.
    """

    def __init__(self, session: AsyncSession, factory: EngineFactory) -> None:
        self._session = session
        self._factory = factory
        self._daos: dict[str, Any] = {}
        self._closed = False

    # -- data access objects ----------------------------------------------

    def _refuse_if_closed(self, what: str) -> None:
        """A closed unit of work says so, rather than SQLAlchemy saying it.

        `close()` set `_closed` and nothing read it, so using a unit of work
        after its `async with` block surfaced SQLAlchemy's own "Instance is not
        bound to a Session" or "This session is closed" — above `prama.db`,
        which the layering rule forbids. QA round 4, `DB-086`.

        The message matters more than the type here. The cause is almost always
        the same mistake — a value read outside the block that created it — and
        the stdlib-flavoured wording sends people looking at the database.
        """
        if self._closed:
            raise DatabaseError(
                f"this unit of work is closed; {what} cannot be used",
                code="DB.UNIT_OF_WORK_CLOSED",
                remedy=(
                    "A unit of work lives for the duration of its `async with` block. "
                    "Do the reads and writes inside it, and take plain values out — "
                    "not DAOs, and not ORM instances, which detach when it closes."
                ),
                context={"used": what},
            )

    def _dao(self, name: str, cls: type[Any]) -> Any:
        self._refuse_if_closed(name)
        if name not in self._daos:
            self._daos[name] = cls(self._session, self._factory.dialect)
        return self._daos[name]

    @property
    def tenants(self) -> TenantDao:
        from prama.db.dao import TenantDao

        return self._dao("tenants", TenantDao)  # type: ignore[no-any-return]

    @property
    def principals(self) -> PrincipalDao:
        from prama.db.dao import PrincipalDao

        return self._dao("principals", PrincipalDao)  # type: ignore[no-any-return]

    @property
    def roles(self) -> RoleDao:
        from prama.db.dao import RoleDao

        return self._dao("roles", RoleDao)  # type: ignore[no-any-return]

    @property
    def api_keys(self) -> ApiKeyDao:
        from prama.db.dao import ApiKeyDao

        return self._dao("api_keys", ApiKeyDao)  # type: ignore[no-any-return]

    @property
    def audit(self) -> AuditDao:
        from prama.db.dao import AuditDao

        return self._dao("audit", AuditDao)  # type: ignore[no-any-return]

    @property
    def alerts(self) -> AlertDao:
        from prama.db.dao.alert import AlertDao

        return self._dao("alerts", AlertDao)  # type: ignore[no-any-return]

    @property
    def fleet(self) -> FleetDao:
        from prama.db.dao.fleet import FleetDao

        return self._dao("fleet", FleetDao)  # type: ignore[no-any-return]

    @property
    def semantic_index(self) -> SemanticIndexDao:
        from prama.db.dao.semantic_index import SemanticIndexDao

        return self._dao("semantic_index", SemanticIndexDao)  # type: ignore[no-any-return]

    @property
    def usage(self) -> UsageDao:
        from prama.db.dao.usage import UsageDao

        return self._dao("usage", UsageDao)  # type: ignore[no-any-return]

    @property
    def comments(self) -> CommentDao:
        from prama.db.dao.comment import CommentDao

        return self._dao("comments", CommentDao)  # type: ignore[no-any-return]

    @property
    def metadata(self) -> MetadataDao:
        from prama.db.dao.metadata import MetadataDao

        return self._dao("metadata", MetadataDao)  # type: ignore[no-any-return]

    @property
    def glossary(self) -> GlossaryDao:
        from prama.db.dao.glossary import GlossaryDao

        return self._dao("glossary", GlossaryDao)  # type: ignore[no-any-return]

    @property
    def llm_governance(self) -> LlmGovernanceDao:
        from prama.db.dao.llm_governance import LlmGovernanceDao

        return self._dao("llm_governance", LlmGovernanceDao)  # type: ignore[no-any-return]

    @property
    def delegate_uploads(self) -> DelegateUploadDao:
        from prama.db.dao.delegate import DelegateUploadDao

        return self._dao("delegate_uploads", DelegateUploadDao)  # type: ignore[no-any-return]

    @property
    def stewards(self) -> StewardDao:
        from prama.db.dao.steward import StewardDao

        return self._dao("stewards", StewardDao)  # type: ignore[no-any-return]

    @property
    def code(self) -> CodeDao:
        from prama.db.dao.code import CodeDao

        return self._dao("code", CodeDao)  # type: ignore[no-any-return]

    @property
    def lineage(self) -> LineageDao:
        from prama.db.dao.lineage import LineageDao

        return self._dao("lineage", LineageDao)  # type: ignore[no-any-return]

    @property
    def llm(self) -> LlmDao:
        from prama.db.dao.llm import LlmDao

        return self._dao("llm", LlmDao)  # type: ignore[no-any-return]

    @property
    def settings(self) -> SettingDao:
        from prama.db.dao import SettingDao

        return self._dao("settings", SettingDao)  # type: ignore[no-any-return]

    # -- semantic layer ----------------------------------------------------
    #
    # One property per declared object. Each is lazy, so a unit of work that
    # touches one table does not construct fifteen DAOs.

    @property
    def domains(self) -> DomainDao:
        from prama.db.dao import DomainDao

        return self._dao("domains", DomainDao)  # type: ignore[no-any-return]

    @property
    def datasets(self) -> DatasetDao:
        from prama.db.dao import DatasetDao

        return self._dao("datasets", DatasetDao)  # type: ignore[no-any-return]

    @property
    def attributes(self) -> AttributeDao:
        from prama.db.dao import AttributeDao

        return self._dao("attributes", AttributeDao)  # type: ignore[no-any-return]

    @property
    def concepts(self) -> ConceptDao:
        from prama.db.dao import ConceptDao

        return self._dao("concepts", ConceptDao)  # type: ignore[no-any-return]

    @property
    def concept_properties(self) -> ConceptPropertyDao:
        from prama.db.dao import ConceptPropertyDao

        return self._dao("concept_properties", ConceptPropertyDao)  # type: ignore[no-any-return]

    @property
    def relationships(self) -> RelationshipDao:
        from prama.db.dao import RelationshipDao

        return self._dao("relationships", RelationshipDao)  # type: ignore[no-any-return]

    @property
    def journeys(self) -> JourneyDao:
        from prama.db.dao import JourneyDao

        return self._dao("journeys", JourneyDao)  # type: ignore[no-any-return]

    @property
    def connections(self) -> ConnectionDao:
        from prama.db.dao import ConnectionDao

        return self._dao("connections", ConnectionDao)  # type: ignore[no-any-return]

    @property
    def bindings(self) -> BindingDao:
        from prama.db.dao import BindingDao

        return self._dao("bindings", BindingDao)  # type: ignore[no-any-return]

    @property
    def attestations(self) -> AttestationDao:
        from prama.db.dao import AttestationDao

        return self._dao("attestations", AttestationDao)  # type: ignore[no-any-return]

    @property
    def breaks(self) -> BreakDao:
        from prama.db.dao import BreakDao

        return self._dao("breaks", BreakDao)  # type: ignore[no-any-return]

    # -- controls -----------------------------------------------------------

    @property
    def controls(self) -> ControlDao:
        from prama.db.dao import ControlDao

        return self._dao("controls", ControlDao)  # type: ignore[no-any-return]

    @property
    def rejections(self) -> RejectionDao:
        from prama.db.dao import RejectionDao

        return self._dao("rejections", RejectionDao)  # type: ignore[no-any-return]

    # -- the evidence ledger ----------------------------------------------
    #
    # Reached through the same unit of work as everything else, so a run that
    # writes evidence and updates the platform commits or rolls back as one.
    # The *tables* are separate (EvidenceBase, no foreign keys out of the
    # ledger); the transaction is not, because a control result recorded
    # without the run it belongs to — or a run recorded without its results —
    # is worse than neither.

    @property
    def evidence(self) -> EvidenceDao:
        from prama.db.dao import EvidenceDao

        return self._dao("evidence", EvidenceDao)  # type: ignore[no-any-return]

    @property
    def evidence_runs(self) -> EvidenceRunDao:
        from prama.db.dao import EvidenceRunDao

        return self._dao("evidence_runs", EvidenceRunDao)  # type: ignore[no-any-return]

    @property
    def samples(self) -> SampleDao:
        from prama.db.dao import SampleDao

        return self._dao("samples", SampleDao)  # type: ignore[no-any-return]

    @property
    def anchors(self) -> AnchorDao:
        from prama.db.dao import AnchorDao

        return self._dao("anchors", AnchorDao)  # type: ignore[no-any-return]

    # -- transaction boundary ---------------------------------------------

    async def flush(self) -> None:
        """Push pending changes without ending the transaction."""
        self._refuse_if_closed("flush()")
        await self._guarded(self._session.flush)

    async def commit(self) -> None:
        self._refuse_if_closed("commit()")
        await self._guarded(self._session.commit)

    async def rollback(self) -> None:
        self._refuse_if_closed("rollback()")
        await self._session.rollback()

    async def close(self) -> None:
        if not self._closed:
            await self._session.close()
            self._closed = True

    async def _guarded(self, operation: Any) -> None:
        """Delegates to `prama.db.guard.guarded`.

        The translation used to live here in full, and the versioned DAOs
        flushed around it — so the one path that most needs a `ConflictError`,
        a concurrent amendment, did not get one. Shared rather than copied.
        """
        from prama.db.guard import guarded

        await guarded(self._session, operation)

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            await self.close()
