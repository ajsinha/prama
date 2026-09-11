"""Declaration services, approval policy, conflict detection and maturity.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.db import Database
from prama.semantic.conflict import ConflictDetector, ConflictKind
from prama.semantic.maturity import EstateFacts, MaturityAssessor, MaturityStage
from prama.semantic.policy import ApprovalPolicy, ApprovalRequirement
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.services import (
    DatasetService,
    EstateService,
    RelationshipService,
    relationship_kinds,
    slugify,
)
from prama.semantic.values import Criticality, Frequency, Grain, Rhythm


class TestSlugify:
    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            ("Positions EOD", "positions_eod"),
            ("Sub-ledger / GL", "sub_ledger_gl"),
            ("  Trades  ", "trades"),
            ("Café Positions", "cafe_positions"),
        ],
    )
    def test_derives_a_stable_identifier(self, name: str, slug: str) -> None:
        assert slugify(name) == slug

    def test_a_name_with_no_usable_characters_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no characters usable"):
            slugify("!!!")


class TestApprovalPolicy:
    def test_tier_one_requires_a_second_person(self) -> None:
        policy = ApprovalPolicy()
        assert policy.for_criticality(Criticality.TIER_1) is ApprovalRequirement.MAKER_CHECKER
        with pytest.raises(ValidationError, match="cannot be approved by its own author"):
            policy.check(criticality=1, authored_by="alice", approved_by="alice")
        policy.check(criticality=1, authored_by="alice", approved_by="bob")

    def test_tier_one_without_any_approver_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="requires approval"):
            ApprovalPolicy().check(criticality=1, authored_by="alice", approved_by=None)

    def test_lower_tiers_are_deliberately_permissive(self) -> None:
        # Demanding two signatures for a Tier-4 comment trains people to click
        # through approvals, which is worse than having none.
        ApprovalPolicy().check(criticality=4, authored_by="alice", approved_by=None)
        ApprovalPolicy().check(criticality=3, authored_by="alice", approved_by=None)


class TestDatasetService:
    async def test_declare_then_find_by_slug(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            await service.declare(
                tenant_id=tenant_id,
                name="Positions EOD",
                authored_by="alice",
                grain=Grain(("account_id", "as_of_date")),
                rhythm=Rhythm(Frequency.DAILY, arrival_by="06:30", calendar="TARGET2"),
            )
            found = await uow.datasets.by_slug(tenant_id, "positions_eod")
            assert found is not None and found.has_grain and found.has_rhythm

    async def test_a_duplicate_name_is_refused_with_the_slug_named(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            await service.declare(tenant_id=tenant_id, name="Positions EOD")
            with pytest.raises(ConflictError, match="already exists"):
                await service.declare(tenant_id=tenant_id, name="positions eod")

    async def test_tier_one_declaration_needs_maker_checker(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            with pytest.raises(ValidationError, match="requires approval"):
                await service.declare(
                    tenant_id=tenant_id,
                    name="FRTB Feeder",
                    criticality=1,
                    authored_by="alice",
                )
            _, version = await service.declare(
                tenant_id=tenant_id,
                name="FRTB Feeder",
                criticality=1,
                authored_by="alice",
                approved_by="bob",
            )
            assert version.lifecycle_state == "active"

    async def test_an_unapproved_declaration_stays_proposed(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            _, version = await DatasetService(uow).declare(
                tenant_id=tenant_id, name="Draft Dataset", authored_by="alice"
            )
            assert version.lifecycle_state == "proposed"

    async def test_an_unexplained_amendment_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            entity, _ = await service.declare(tenant_id=tenant_id, name="Positions")
            with pytest.raises(ValidationError, match="must say why"):
                await service.amend(
                    tenant_id=tenant_id, dataset_id=str(entity.id), reason="  ", purpose="x"
                )

    async def test_every_declaration_writes_an_audit_event(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, _ = await DatasetService(uow).declare(
                tenant_id=tenant_id, name="Positions", authored_by="alice"
            )
        async with started_database.unit_of_work() as uow:
            events = await uow.audit.for_object(tenant_id, "dataset", str(entity.id))
            assert [e.action for e in events] == ["dataset.declared"]
            assert events[0].actor_id == "alice"

    async def test_attributes_cannot_be_declared_on_a_missing_dataset(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError):
                await DatasetService(uow).declare_attribute(
                    tenant_id=tenant_id, dataset_id="01AAAAAAAAAAAAAAAAAAAAAAAA", name="x"
                )

    async def test_duplicate_attribute_names_are_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            dataset, _ = await service.declare(tenant_id=tenant_id, name="Positions")
            await service.declare_attribute(
                tenant_id=tenant_id, dataset_id=str(dataset.id), name="notional"
            )
            with pytest.raises(ConflictError, match="already declared"):
                await service.declare_attribute(
                    tenant_id=tenant_id, dataset_id=str(dataset.id), name="notional"
                )


class TestRelationshipService:
    async def _two_datasets(self, uow, tenant_id: str):
        service = DatasetService(uow)
        a, _ = await service.declare(tenant_id=tenant_id, name="Sub-ledger")
        b, _ = await service.declare(tenant_id=tenant_id, name="General Ledger")
        return str(a.id), str(b.id)

    async def test_declaring_a_reconciliation_records_what_it_generates(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            sub, gl = await self._two_datasets(uow, tenant_id)
            entity, version = await RelationshipService(uow).declare(
                tenant_id=tenant_id,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=sub,
                    to_dataset_id=gl,
                    match_keys=(MatchKey("account_code"),),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="EUR"),
                ),
                authored_by="architect",
            )
            assert version.is_confirmed
        async with started_database.unit_of_work() as uow:
            events = await uow.audit.for_object(tenant_id, "relationship", str(entity.id))
            assert "reconciliation" in events[0].detail_json["generates"]

    async def test_relating_a_missing_dataset_is_refused(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            sub, _ = await self._two_datasets(uow, tenant_id)
            with pytest.raises(NotFoundError, match="to dataset"):
                await RelationshipService(uow).declare(
                    tenant_id=tenant_id,
                    declaration=RelationshipDeclaration(
                        kind=RelationshipKind.REFERENCES,
                        from_dataset_id=sub,
                        to_dataset_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
                        match_keys=(MatchKey("k"),),
                    ),
                )

    async def test_a_discovered_relationship_is_never_confirmed_automatically(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            a, b = await self._two_datasets(uow, tenant_id)
            service = RelationshipService(uow)
            entity, version = await service.propose_discovered(
                tenant_id=tenant_id,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.REFERENCES,
                    from_dataset_id=a,
                    to_dataset_id=b,
                    match_keys=(MatchKey("account_id"),),
                ),
                discovered_by="overlap_statistics",
                confidence=0.94,
                evidence={"key_overlap": 0.996, "rows_sampled": 250_000},
            )
            assert version.status == "proposed"
            assert await uow.relationships.confirmed(tenant_id) == []

            confirmed = await service.confirm(
                tenant_id=tenant_id, relationship_id=str(entity.id), confirmed_by="steward"
            )
            assert confirmed.is_confirmed
            # The evidence survives confirmation: why it was suggested stays visible.
            assert confirmed.evidence_json["key_overlap"] == 0.996

    async def test_rejection_is_recorded_rather_than_deleted(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            a, b = await self._two_datasets(uow, tenant_id)
            service = RelationshipService(uow)
            entity, _ = await service.propose_discovered(
                tenant_id=tenant_id,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.REFERENCES,
                    from_dataset_id=a,
                    to_dataset_id=b,
                    match_keys=(MatchKey("k"),),
                ),
                discovered_by="naming_similarity",
                confidence=0.4,
                evidence={},
            )
            await service.reject(
                tenant_id=tenant_id,
                relationship_id=str(entity.id),
                rejected_by="steward",
                reason="different account namespaces",
            )
            current = await uow.relationships.current(str(entity.id), tenant_id=tenant_id)
            assert current.status == "rejected"
            # Re-proposing something already rejected is how trust is lost.
            assert len(await uow.relationships.history(str(entity.id), tenant_id=tenant_id)) == 2

    def test_every_kind_is_offered_in_business_language(self) -> None:
        kinds = relationship_kinds()
        assert len(kinds) == 13
        assert all(k["prompt"] and k["generates"] for k in kinds)


class TestConflictDetection:
    class _Attr:
        def __init__(self, attribute_id, name, **kw):
            self.attribute_id = attribute_id
            self.name = name
            self.semantic_type = kw.get("semantic_type")
            self.unit = kw.get("unit")
            self.optionality = kw.get("optionality", "optional")
            self.sensitivity = kw.get("sensitivity", "internal")
            self.value_domain_json = kw.get("value_domain_json")
            self.definition = kw.get("definition", "defined")

    def test_a_single_claimant_cannot_conflict_with_itself(self) -> None:
        attrs = [self._Attr("a1", "lei", semantic_type="lei")]
        assert ConflictDetector().detect("p1", "Party.LEI", attrs) == []

    def test_agreement_produces_no_conflict(self) -> None:
        attrs = [
            self._Attr("a1", "counterparty_lei", semantic_type="lei"),
            self._Attr("a2", "party_lei", semantic_type="lei"),
        ]
        assert ConflictDetector().detect("p1", "Party.LEI", attrs) == []

    def test_a_unit_mismatch_is_critical(self) -> None:
        # The expensive one: two attributes that agree on everything except that
        # one is in thousands will reconcile for years and be wrong by 1000x.
        attrs = [
            self._Attr("a1", "notional", unit="EUR"),
            self._Attr("a2", "notional_k", unit="EUR_thousands"),
        ]
        conflicts = ConflictDetector().detect("p1", "Exposure.Notional", attrs)
        assert [c.kind for c in conflicts] == [ConflictKind.UNIT]
        assert conflicts[0].severity == "critical"
        assert "notional" in conflicts[0].render()

    def test_value_domains_are_compared_by_what_they_constrain(self) -> None:
        same = [
            self._Attr(
                "a1", "ccy", value_domain_json={"kind": "codelist", "codelist_ref": "iso4217"}
            ),
            self._Attr(
                "a2", "currency", value_domain_json={"kind": "codelist", "codelist_ref": "iso4217"}
            ),
        ]
        assert ConflictDetector().detect("p", "Money.Currency", same) == []
        different = [
            same[0],
            self._Attr(
                "a3", "ccy", value_domain_json={"kind": "codelist", "codelist_ref": "internal_ccy"}
            ),
        ]
        kinds = [c.kind for c in ConflictDetector().detect("p", "Money.Currency", different)]
        assert ConflictKind.VALUE_DOMAIN in kinds

    def test_partial_definition_is_flagged(self) -> None:
        attrs = [
            self._Attr("a1", "lei", definition="The counterparty's LEI."),
            self._Attr("a2", "lei", definition="   "),
        ]
        kinds = [c.kind for c in ConflictDetector().detect("p", "Party.LEI", attrs)]
        assert ConflictKind.DEFINITION_ABSENT in kinds

    def test_worst_severity_is_reported(self) -> None:
        detector = ConflictDetector()
        attrs = [
            self._Attr("a1", "x", unit="EUR", optionality="mandatory"),
            self._Attr("a2", "y", unit="USD", optionality="optional"),
        ]
        assert detector.worst_severity(detector.detect("p", "P.x", attrs)) == "critical"

    async def test_conflicts_are_found_across_the_real_estate(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            concept, _ = await uow.concepts.create(tenant_id=tenant_id, name="Exposure")
            prop, _ = await uow.concept_properties.create(
                tenant_id=tenant_id,
                identity_fields={"concept_id": concept.id},
                name="Notional",
            )
            service = DatasetService(uow)
            for name, unit in (("Book A", "EUR"), ("Book B", "EUR_thousands")):
                dataset, _ = await service.declare(tenant_id=tenant_id, name=name)
                await service.declare_attribute(
                    tenant_id=tenant_id,
                    dataset_id=str(dataset.id),
                    name="notional",
                    unit=unit,
                    concept_property_id=str(prop.id),
                    definition="notional",
                )
            conflicts = await EstateService(uow).conflicts(tenant_id)
            assert [c.kind for c in conflicts] == [ConflictKind.UNIT]
            assert conflicts[0].property_name == "Exposure.Notional"


class TestMaturity:
    def test_an_empty_domain_scores_zero_without_dividing_by_zero(self) -> None:
        score = MaturityAssessor().assess("empty", EstateFacts())
        assert score.percent == 0
        assert score.stage is MaturityStage.DISCOVERED

    def test_a_fully_declared_estate_approaches_full_marks(self) -> None:
        facts = EstateFacts(
            datasets=10,
            datasets_owned=10,
            datasets_with_grain=10,
            datasets_with_rhythm=10,
            datasets_bound=10,
            attributes=100,
            attributes_defined=100,
            attributes_mapped_to_concepts=100,
            tier_one_datasets=2,
            tier_one_datasets_with_grain=2,
            relationships_confirmed=5,
            journeys=2,
            journey_datasets=10,
        )
        score = MaturityAssessor().assess("mature", facts)
        assert score.percent == 100
        assert score.stage is MaturityStage.JOURNEYED
        assert score.actions == ()

    def test_relationships_carry_the_greatest_weight(self) -> None:
        # They generate the highest-value controls and nothing else can.
        from prama.semantic.maturity import STAGE_WEIGHTS

        assert STAGE_WEIGHTS[MaturityStage.RELATED] == max(STAGE_WEIGHTS.values())

    def test_next_actions_lead_with_tier_one_grain(self) -> None:
        facts = EstateFacts(
            datasets=40,
            datasets_owned=40,
            datasets_with_grain=12,
            datasets_with_rhythm=8,
            datasets_bound=30,
            attributes=800,
            attributes_defined=200,
            tier_one_datasets=6,
            tier_one_datasets_with_grain=2,
            relationships_confirmed=3,
        )
        actions = MaturityAssessor().assess("credit-risk", facts).actions
        assert "Tier-1" in actions[0].headline
        assert actions[0].estimated_controls > 0

    def test_the_score_explains_itself(self) -> None:
        score = MaturityAssessor().assess("x", EstateFacts(datasets=2, datasets_owned=1))
        assert len(score.explain()) == 6
        assert all("weight" in line for line in score.explain())

    async def test_maturity_is_computed_from_a_real_estate(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            await service.declare(
                tenant_id=tenant_id,
                name="Positions",
                owner_id="alice",
                grain=Grain(("account_id",)),
            )
            await service.declare(tenant_id=tenant_id, name="Trades")
            estate = EstateService(uow)
            facts = await estate.gather_facts(tenant_id)
            assert facts.datasets == 2
            assert facts.datasets_with_grain == 1
            assert facts.datasets_owned == 1

            gaps = await estate.coverage_gaps(tenant_id)
            assert sorted(gaps["unbound"]) == ["Positions", "Trades"]
            assert gaps["unowned"] == ["Trades"]
