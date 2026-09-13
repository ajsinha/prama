"""Semantic-layer data access.

One DAO per declared object, each inheriting the bitemporal protocol from
``VersionedDao`` so that create, amend, correct and read behave identically for
every object type. What each subclass adds is only what is genuinely specific:
the lookups its own screens need.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from prama.db.dao.versioned import VersionedDao
from prama.db.models import (
    SemAttribute,
    SemAttributeVersion,
    SemBinding,
    SemBindingVersion,
    SemConcept,
    SemConceptProperty,
    SemConceptPropertyVersion,
    SemConceptVersion,
    SemConnection,
    SemConnectionVersion,
    SemDataset,
    SemDatasetVersion,
    SemDomain,
    SemDomainVersion,
    SemJourney,
    SemJourneyVersion,
    SemRelationship,
    SemRelationshipVersion,
)
from prama.db.temporal import TemporalQuery


class DomainDao(VersionedDao[SemDomain, SemDomainVersion]):
    model = SemDomain
    version_model = SemDomainVersion
    entity_key = "domain_id"

    async def by_name(self, tenant_id: str, name: str) -> SemDomainVersion | None:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemDomainVersion)
            .join(SemDomain, SemDomain.id == SemDomainVersion.domain_id)
            .where(SemDomain.tenant_id == tenant_id, SemDomainVersion.name == name),
            SemDomainVersion,
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()


class DatasetDao(VersionedDao[SemDataset, SemDatasetVersion]):
    model = SemDataset
    version_model = SemDatasetVersion
    entity_key = "dataset_id"

    async def by_slug(self, tenant_id: str, slug: str) -> SemDatasetVersion | None:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemDatasetVersion)
            .join(SemDataset, SemDataset.id == SemDatasetVersion.dataset_id)
            .where(SemDataset.tenant_id == tenant_id, SemDatasetVersion.slug == slug),
            SemDatasetVersion,
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def in_domain(self, tenant_id: str, domain_id: str) -> list[SemDatasetVersion]:
        return await self._current_where(tenant_id, SemDatasetVersion.domain_id == domain_id)

    async def unbound(self, tenant_id: str) -> list[SemDatasetVersion]:
        """Declared but not yet connected — a first-class state, and a report.

        These are the gaps between what the business says exists and what Prama
        can actually reach. No physical-first tool can produce this list at all,
        because it only knows what it crawled.
        """
        return await self._current_where(tenant_id, SemDatasetVersion.shape == "unbound")

    async def by_criticality(self, tenant_id: str, tier: int) -> list[SemDatasetVersion]:
        return await self._current_where(tenant_id, SemDatasetVersion.criticality == tier)

    async def _current_where(self, tenant_id: str, *conditions: Any) -> list[SemDatasetVersion]:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemDatasetVersion)
            .join(SemDataset, SemDataset.id == SemDatasetVersion.dataset_id)
            .where(SemDataset.tenant_id == tenant_id, *conditions),
            SemDatasetVersion,
        ).order_by(SemDatasetVersion.name)
        return list((await self._session.execute(stmt)).scalars().all())


class AttributeDao(VersionedDao[SemAttribute, SemAttributeVersion]):
    model = SemAttribute
    version_model = SemAttributeVersion
    entity_key = "attribute_id"

    async def for_dataset(self, dataset_id: str, *, tenant_id: str) -> list[SemAttributeVersion]:
        """Every current attribute of one dataset, in declared order.

        The tenant is required, and this is why: the by-parent reads on these
        DAOs took a parent id and nothing else, so a caller holding an
        identifier from another estate read that estate's rows in full — a 200
        with the data, not a 404 (QA finding F-02). Sibling methods on the same
        classes, `critical_data_elements` and `drifted`, always filtered; these
        four did not, and the tenant sweep in
        `tests/security/test_tenant_isolation.py` could not see them because it
        probes methods whose *first* parameter is `tenant_id`.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemAttributeVersion)
            .join(SemAttribute, SemAttribute.id == SemAttributeVersion.attribute_id)
            .where(
                SemAttribute.dataset_id == dataset_id,
                SemAttribute.tenant_id == tenant_id,
            ),
            SemAttributeVersion,
        ).order_by(SemAttributeVersion.ordinal, SemAttributeVersion.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def critical_data_elements(self, tenant_id: str) -> list[SemAttributeVersion]:
        """Every CDE in the tenant — the population that attracts the strictest
        controls, mandatory attestation and the longest evidence retention."""
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemAttributeVersion)
            .join(SemAttribute, SemAttribute.id == SemAttributeVersion.attribute_id)
            .where(SemAttribute.tenant_id == tenant_id, SemAttributeVersion.is_cde.is_(True)),
            SemAttributeVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def mapped_to_property(
        self, property_id: str, *, tenant_id: str
    ) -> list[SemAttributeVersion]:
        """Every attribute in this estate claiming to be the same canonical property.

        The input to conflict detection: if two of these disagree about units or
        value domain, the estate holds two meanings for one concept.

        The tenant is required, and this is why: the by-parent reads on these
        DAOs took a parent id and nothing else, so a caller holding an
        identifier from another estate read that estate's rows in full — a 200
        with the data, not a 404 (QA finding F-02, and this method in round 2).
        The tenant sweep in `tests/security/test_tenant_isolation.py` could not
        see it, because it probes methods whose *first* parameter is
        `tenant_id`, and this one had no tenant parameter at all.

        A shared concept library is the point of the product, so two estates
        mapping onto the same property id is the normal case, not a collision.
        That makes a property id something an outsider can plausibly hold, and
        holding it must not be enough to read another estate's attributes.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemAttributeVersion)
            .join(SemAttribute, SemAttribute.id == SemAttributeVersion.attribute_id)
            .where(
                SemAttributeVersion.concept_property_id == property_id,
                SemAttribute.tenant_id == tenant_id,
            ),
            SemAttributeVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())


class ConceptDao(VersionedDao[SemConcept, SemConceptVersion]):
    model = SemConcept
    version_model = SemConceptVersion
    entity_key = "concept_id"

    async def by_name(self, tenant_id: str, name: str) -> SemConceptVersion | None:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemConceptVersion)
            .join(SemConcept, SemConcept.id == SemConceptVersion.concept_id)
            .where(SemConcept.tenant_id == tenant_id, SemConceptVersion.name == name),
            SemConceptVersion,
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()


class ConceptPropertyDao(VersionedDao[SemConceptProperty, SemConceptPropertyVersion]):
    model = SemConceptProperty
    version_model = SemConceptPropertyVersion
    entity_key = "property_id"

    async def for_concept(
        self, concept_id: str, *, tenant_id: str
    ) -> list[SemConceptPropertyVersion]:
        """Every current property of one concept.

        The tenant is required, and this is why: the by-parent reads on these
        DAOs took a parent id and nothing else, so a caller holding an
        identifier from another estate read that estate's rows in full — a 200
        with the data, not a 404 (QA finding F-02). Sibling methods on the same
        classes, `critical_data_elements` and `drifted`, always filtered; these
        four did not, and the tenant sweep in
        `tests/security/test_tenant_isolation.py` could not see them because it
        probes methods whose *first* parameter is `tenant_id`.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemConceptPropertyVersion)
            .join(
                SemConceptProperty,
                SemConceptProperty.id == SemConceptPropertyVersion.property_id,
            )
            .where(
                SemConceptProperty.concept_id == concept_id,
                SemConceptProperty.tenant_id == tenant_id,
            ),
            SemConceptPropertyVersion,
        ).order_by(SemConceptPropertyVersion.name)
        return list((await self._session.execute(stmt)).scalars().all())


class RelationshipDao(VersionedDao[SemRelationship, SemRelationshipVersion]):
    model = SemRelationship
    version_model = SemRelationshipVersion
    entity_key = "relationship_id"

    async def touching(self, tenant_id: str, dataset_id: str) -> list[SemRelationshipVersion]:
        """Every relationship in which this dataset takes part, either side.

        The estate map's edge query, and the starting point for both impact
        analysis and root-cause navigation.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemRelationshipVersion)
            .join(
                SemRelationship,
                SemRelationship.id == SemRelationshipVersion.relationship_id,
            )
            .where(
                SemRelationship.tenant_id == tenant_id,
                (SemRelationshipVersion.from_dataset_id == dataset_id)
                | (SemRelationshipVersion.to_dataset_id == dataset_id),
            ),
            SemRelationshipVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def of_kind(self, tenant_id: str, kind: str) -> list[SemRelationshipVersion]:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemRelationshipVersion)
            .join(
                SemRelationship,
                SemRelationship.id == SemRelationshipVersion.relationship_id,
            )
            .where(SemRelationship.tenant_id == tenant_id, SemRelationshipVersion.kind == kind),
            SemRelationshipVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def confirmed(self, tenant_id: str) -> list[SemRelationshipVersion]:
        """Only confirmed relationships may generate activatable controls."""
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemRelationshipVersion)
            .join(
                SemRelationship,
                SemRelationship.id == SemRelationshipVersion.relationship_id,
            )
            .where(
                SemRelationship.tenant_id == tenant_id,
                SemRelationshipVersion.status == "confirmed",
            ),
            SemRelationshipVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())


class JourneyDao(VersionedDao[SemJourney, SemJourneyVersion]):
    model = SemJourney
    version_model = SemJourneyVersion
    entity_key = "journey_id"

    async def by_slug(self, tenant_id: str, slug: str) -> SemJourneyVersion | None:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemJourneyVersion)
            .join(SemJourney, SemJourney.id == SemJourneyVersion.journey_id)
            .where(SemJourney.tenant_id == tenant_id, SemJourneyVersion.slug == slug),
            SemJourneyVersion,
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def containing(self, tenant_id: str, dataset_id: str) -> list[SemJourneyVersion]:
        """Journeys a dataset appears in — the blast radius, in business terms."""
        journeys = await self.list_current(tenant_id, limit=10_000)
        return [j for j in journeys if dataset_id in j.dataset_ids]


class ConnectionDao(VersionedDao[SemConnection, SemConnectionVersion]):
    model = SemConnection
    version_model = SemConnectionVersion
    entity_key = "connection_id"

    async def by_slug(self, tenant_id: str, slug: str) -> SemConnectionVersion | None:
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemConnectionVersion)
            .join(SemConnection, SemConnection.id == SemConnectionVersion.connection_id)
            .where(SemConnection.tenant_id == tenant_id, SemConnectionVersion.slug == slug),
            SemConnectionVersion,
        )
        return (await self._session.execute(stmt)).scalars().one_or_none()

    async def unhealthy(self, tenant_id: str) -> list[SemConnectionVersion]:
        return [c for c in await self.list_current(tenant_id, limit=10_000) if not c.is_usable]


class BindingDao(VersionedDao[SemBinding, SemBindingVersion]):
    model = SemBinding
    version_model = SemBindingVersion
    entity_key = "binding_id"

    async def for_dataset(self, dataset_id: str, *, tenant_id: str) -> list[SemBindingVersion]:
        """Every current binding of one dataset.

        The tenant is required, and this is why: the by-parent reads on these
        DAOs took a parent id and nothing else, so a caller holding an
        identifier from another estate read that estate's rows in full — a 200
        with the data, not a 404 (QA finding F-02). Sibling methods on the same
        classes, `critical_data_elements` and `drifted`, always filtered; these
        four did not, and the tenant sweep in
        `tests/security/test_tenant_isolation.py` could not see them because it
        probes methods whose *first* parameter is `tenant_id`.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemBindingVersion)
            .join(SemBinding, SemBinding.id == SemBindingVersion.binding_id)
            .where(
                SemBindingVersion.dataset_id == dataset_id,
                SemBinding.tenant_id == tenant_id,
            ),
            SemBindingVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def for_attribute(self, attribute_id: str, *, tenant_id: str) -> SemBindingVersion | None:
        """The current binding of one attribute, if it has one.

        The tenant is required, and this is why: the by-parent reads on these
        DAOs took a parent id and nothing else, so a caller holding an
        identifier from another estate read that estate's rows in full — a 200
        with the data, not a 404 (QA finding F-02). Sibling methods on the same
        classes, `critical_data_elements` and `drifted`, always filtered; these
        four did not, and the tenant sweep in
        `tests/security/test_tenant_isolation.py` could not see them because it
        probes methods whose *first* parameter is `tenant_id`.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemBindingVersion)
            .join(SemBinding, SemBinding.id == SemBindingVersion.binding_id)
            .where(
                SemBindingVersion.attribute_id == attribute_id,
                SemBinding.tenant_id == tenant_id,
            ),
            SemBindingVersion,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def drifted(self, tenant_id: str) -> list[SemBindingVersion]:
        """Bindings whose physical target has moved beneath the declaration.

        Each one is an incident for the **business owner of the declaration**,
        not for an engineer — the declaration is theirs, and only a platform
        holding a declared model can detect this at all.
        """
        await self._session.flush()
        stmt = TemporalQuery.current(
            select(SemBindingVersion)
            .join(SemBinding, SemBinding.id == SemBindingVersion.binding_id)
            .where(
                SemBinding.tenant_id == tenant_id,
                SemBindingVersion.drift_state.in_(["missing", "retyped", "renamed"]),
            ),
            SemBindingVersion,
        )
        return list((await self._session.execute(stmt)).scalars().all())
