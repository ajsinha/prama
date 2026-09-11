"""The semantic layer: declarations, bitemporality, and the relationship graph.

The tests that earn the bitemporal machinery its cost are in
``TestAmendVersusCorrect``. Conflating the two operations is the classic
bitemporal defect, and it is unrecoverable after the fact.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from prama.core.clock import utc_now
from prama.core.errors import ConflictError, NotFoundError
from prama.db import Database
from prama.db.temporal import Provenance
from prama.semantic.relationships import (
    MatchKey,
    OffsetUnit,
    RelationshipDeclaration,
    RelationshipKind,
    TimeOffset,
    Tolerance,
)
from prama.semantic.values import Frequency, Grain, Rhythm


async def _declare_dataset(uow, tenant_id: str, *, slug: str = "positions_eod", **extra):
    return await uow.datasets.create(
        tenant_id=tenant_id,
        name=extra.pop("name", "Positions EOD"),
        slug=slug,
        provenance=Provenance(authored_by="user-1", reason="initial declaration"),
        **extra,
    )


class TestDeclaration:
    async def test_a_dataset_can_be_declared_before_it_is_bound(
        self, started_database: Database, tenant_id: str
    ) -> None:
        # The whole point of the semantic layer: architects map the estate
        # before connectivity exists, and the gap is reportable.
        async with started_database.unit_of_work() as uow:
            _, version = await _declare_dataset(uow, tenant_id)
            assert version.shape == "unbound"
            assert version.is_bound is False
            assert [d.slug for d in await uow.datasets.unbound(tenant_id)] == ["positions_eod"]

    async def test_the_declaration_generates_its_derived_state(
        self, started_database: Database, tenant_id: str
    ) -> None:
        grain = Grain(
            ("account_id", "instrument_id", "as_of_date"),
            "one position per account per instrument per business day",
        )
        rhythm = Rhythm(
            Frequency.DAILY,
            arrival_by="06:30",
            calendar="TARGET2",
            expected_volume_min=900_000,
            expected_volume_max=1_200_000,
            volume_drivers=("trading_days", "month_end"),
        )
        async with started_database.unit_of_work() as uow:
            _, version = await _declare_dataset(
                uow,
                tenant_id,
                grain_json=grain.to_dict(),
                rhythm_json=rhythm.to_dict(),
                criticality=1,
                shape="feed",
            )
            assert version.has_grain and version.has_rhythm and version.is_tier_one
            # And the declaration survives the round trip through JSON text.
            assert Grain.from_dict(version.grain_json).arity == 3
            assert Rhythm.from_dict(version.rhythm_json).arrival_by == "06:30"

    async def test_declaration_is_attributable(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            _, version = await _declare_dataset(uow, tenant_id)
            assert version.authored_by == "user-1"
            assert version.change_reason == "initial declaration"
            assert version.is_approved is False  # authorship is not approval

    async def test_first_version_is_current(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, version = await _declare_dataset(uow, tenant_id)
            assert version.is_current
            assert (await uow.datasets.current(entity.id, tenant_id=tenant_id)).id == version.id


class TestAmendVersusCorrect:
    """The distinction the whole bitemporal design exists to preserve."""

    async def test_amend_records_that_the_world_changed(
        self, started_database: Database, tenant_id: str
    ) -> None:
        april = datetime(2026, 4, 1, tzinfo=UTC)
        march = datetime(2026, 3, 15, tzinfo=UTC)
        async with started_database.unit_of_work() as uow:
            entity, first = await _declare_dataset(
                uow,
                tenant_id,
                grain_json=Grain(("account_id", "as_of_date")).to_dict(),
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
            await uow.datasets.amend(
                entity.id,
                tenant_id=tenant_id,
                effective_from=april,
                grain_json=Grain(("account_id", "instrument_id", "as_of_date")).to_dict(),
                provenance=Provenance(authored_by="user-2", reason="added instrument split"),
            )

            # Both versions are still believed; each is true of its own period.
            in_march = await uow.datasets.valid_at(entity.id, march, tenant_id=tenant_id)
            now = await uow.datasets.current(entity.id, tenant_id=tenant_id)
            assert Grain.from_dict(in_march.grain_json).arity == 2
            assert Grain.from_dict(now.grain_json).arity == 3
            assert first.valid_to == april
            assert first.superseded_at is None  # it was never wrong

    async def test_correct_records_that_we_were_wrong(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, mistaken = await _declare_dataset(
                uow,
                tenant_id,
                name="Postions EOD",  # typo, as it happens
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
            corrected = await uow.datasets.correct(
                entity.id,
                tenant_id=tenant_id,
                name="Positions EOD",
                provenance=Provenance(authored_by="user-2", reason="typo in the name"),
            )
            # Validity is inherited: the name was never different in the world.
            assert corrected.valid_from == mistaken.valid_from
            assert corrected.valid_to == mistaken.valid_to
            # But we stopped believing the mistaken version.
            assert mistaken.superseded_at is not None
            assert corrected.superseded_at is None

    async def test_the_two_are_distinguishable_a_year_later(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The property that cannot be recovered if the distinction is lost."""
        async with started_database.unit_of_work() as uow:
            entity, _ = await _declare_dataset(
                uow, tenant_id, valid_from=datetime(2026, 1, 1, tzinfo=UTC)
            )
            await uow.datasets.amend(
                entity.id,
                tenant_id=tenant_id,
                effective_from=datetime(2026, 4, 1, tzinfo=UTC),
                purpose="amended",
            )
            await uow.datasets.correct(entity.id, description="corrected", tenant_id=tenant_id)

            history = await uow.datasets.history(entity.id, tenant_id=tenant_id)
            amended = [v for v in history if v.valid_to is not None and v.superseded_at is None]
            superseded = [v for v in history if v.superseded_at is not None]
            assert len(history) == 3
            assert len(amended) == 1  # closed validity, still believed
            assert len(superseded) == 1  # never true, no longer believed

    async def test_as_of_resolves_what_was_believed_then_not_what_is_believed_now(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The question an evidence replay asks.

        A control that ran before a correction must resolve the declaration that
        stood when it ran — otherwise the replay silently answers a different
        question and the divergence goes unnoticed.
        """
        async with started_database.unit_of_work() as uow:
            entity, mistaken = await _declare_dataset(
                uow,
                tenant_id,
                name="Wrong Name",
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
            )
            await uow.flush()
            when_the_control_ran = utc_now()
            # The correction comes later, as it does in life: someone noticed.
            await asyncio.sleep(0.01)
            await uow.datasets.correct(entity.id, name="Right Name", tenant_id=tenant_id)
            assert mistaken.superseded_at > when_the_control_ran

            believed_then = await uow.datasets.as_of(
                entity.id,
                tenant_id=tenant_id,
                valid_at=datetime(2026, 2, 1, tzinfo=UTC),
                known_at=when_the_control_ran,
            )
            believed_now = await uow.datasets.current(entity.id, tenant_id=tenant_id)
            assert believed_then.name == "Wrong Name"
            assert believed_now.name == "Right Name"

    async def test_an_amendment_cannot_predate_the_version_it_replaces(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, _ = await _declare_dataset(
                uow, tenant_id, valid_from=datetime(2026, 6, 1, tzinfo=UTC)
            )
            with pytest.raises(ConflictError, match="before the version it replaces"):
                await uow.datasets.amend(
                    entity.id,
                    tenant_id=tenant_id,
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                    purpose="x",
                )

    async def test_amending_a_nonexistent_entity_names_it(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            with pytest.raises(NotFoundError):
                await uow.datasets.amend(
                    "01AAAAAAAAAAAAAAAAAAAAAAAA", purpose="x", tenant_id=tenant_id
                )

    async def test_a_typo_in_a_field_name_is_refused_rather_than_silently_ignored(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, _ = await _declare_dataset(uow, tenant_id)
            with pytest.raises(ConflictError, match="unknown field"):
                await uow.datasets.amend(
                    entity.id, critcality=1, tenant_id=tenant_id
                )  # codespell:ignore

    async def test_retire_ends_validity_without_destroying_history(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            entity, _ = await _declare_dataset(uow, tenant_id)
            await uow.datasets.retire(
                entity.id, provenance=Provenance(reason="decommissioned"), tenant_id=tenant_id
            )
            assert await uow.datasets.current(entity.id, tenant_id=tenant_id) is None
            assert (
                len(await uow.datasets.history(entity.id, tenant_id=tenant_id)) == 1
            )  # still there


class TestAttributes:
    async def test_attributes_carry_interpretation_separately_from_definition(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            dataset, _ = await _declare_dataset(uow, tenant_id)
            _, attribute = await uow.attributes.create(
                tenant_id=tenant_id,
                identity_fields={"dataset_id": dataset.id},
                name="notional_amount",
                definition="The face value of the position.",
                interpretation="Gross of collateral; excludes intercompany.",
                semantic_type="monetary_amount",
                currency_attribute="currency",
                is_cde=True,
                obligations_json=["FRTB"],
            )
            assert attribute.is_cde is True
            assert attribute.is_constrained  # a semantic type generates controls
            assert "intercompany" in attribute.interpretation

    async def test_critical_data_elements_are_findable_estate_wide(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            dataset, _ = await _declare_dataset(uow, tenant_id)
            for name, cde in (("notional_amount", True), ("comment", False)):
                await uow.attributes.create(
                    tenant_id=tenant_id,
                    identity_fields={"dataset_id": dataset.id},
                    name=name,
                    is_cde=cde,
                )
            cdes = await uow.attributes.critical_data_elements(tenant_id)
            assert [a.name for a in cdes] == ["notional_amount"]

    async def test_attributes_are_ordered_for_a_dataset(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            dataset, _ = await _declare_dataset(uow, tenant_id)
            for ordinal, name in enumerate(["c", "a", "b"]):
                await uow.attributes.create(
                    tenant_id=tenant_id,
                    identity_fields={"dataset_id": dataset.id},
                    name=name,
                    ordinal=ordinal,
                )
            assert [a.name for a in await uow.attributes.for_dataset(dataset.id)] == ["c", "a", "b"]


class TestRelationships:
    async def test_a_reconciliation_declaration_becomes_a_stored_relationship(
        self, started_database: Database, tenant_id: str
    ) -> None:
        declaration = RelationshipDeclaration(
            kind=RelationshipKind.RECONCILES_WITH,
            from_dataset_id="a",
            to_dataset_id="b",
            match_keys=(MatchKey("account_code"), MatchKey("cost_centre")),
            compare=("amount",),
            tolerance=Tolerance(absolute=1.00, currency="EUR"),
            offset=TimeOffset(1, OffsetUnit.BUSINESS_DAYS, calendar="TARGET2"),
        )
        async with started_database.unit_of_work() as uow:
            sub, _ = await _declare_dataset(uow, tenant_id, slug="subledger", name="Sub-ledger")
            gl, _ = await _declare_dataset(uow, tenant_id, slug="gl", name="General Ledger")
            _, version = await uow.relationships.create(
                tenant_id=tenant_id,
                kind=declaration.kind.value,
                from_dataset_id=sub.id,
                to_dataset_id=gl.id,
                match_keys_json=[k.to_dict() for k in declaration.match_keys],
                compare_json=list(declaration.compare),
                tolerance_json=declaration.tolerance.to_dict(),
                offset_json=declaration.offset.to_dict(),
                status="confirmed",
                criticality=1,
                provenance=Provenance(authored_by="architect", reason="declared on the map"),
            )
            assert version.is_confirmed
            assert version.is_discovered is False
            restored = Tolerance.from_dict(version.tolerance_json)
            assert restored.permits(0.50, 1_000_000) is True
            assert restored.permits(1.50, 1_000_000) is False

    async def test_relationships_are_found_from_either_side(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            a, _ = await _declare_dataset(uow, tenant_id, slug="a", name="A")
            b, _ = await _declare_dataset(uow, tenant_id, slug="b", name="B")
            await uow.relationships.create(
                tenant_id=tenant_id,
                kind="derives_from",
                from_dataset_id=b.id,
                to_dataset_id=a.id,
                match_keys_json=[{"left": "account_id", "right": None}],
                tolerance_json={"relative": 0.0001},
                status="confirmed",
            )
            assert len(await uow.relationships.touching(tenant_id, a.id)) == 1
            assert len(await uow.relationships.touching(tenant_id, b.id)) == 1

    async def test_only_confirmed_relationships_are_eligible_to_generate_controls(
        self, started_database: Database, tenant_id: str
    ) -> None:
        # A discovered relationship is a suggestion; a control derived from one
        # must itself remain a proposal until a human confirms the relationship.
        async with started_database.unit_of_work() as uow:
            a, _ = await _declare_dataset(uow, tenant_id, slug="a", name="A")
            b, _ = await _declare_dataset(uow, tenant_id, slug="b", name="B")
            await uow.relationships.create(
                tenant_id=tenant_id,
                kind="references",
                from_dataset_id=a.id,
                to_dataset_id=b.id,
                match_keys_json=[{"left": "account_id"}],
                status="proposed",
                confidence=0.87,
                discovered_by="overlap_statistics",
                evidence_json={"key_overlap": 0.996},
            )
            assert await uow.relationships.confirmed(tenant_id) == []
            proposed = (await uow.relationships.of_kind(tenant_id, "references"))[0]
            assert proposed.is_discovered
            assert proposed.evidence_json["key_overlap"] == 0.996

    @pytest.mark.parametrize("kind", list(RelationshipKind))
    def test_every_kind_declares_what_it_generates_and_whether_trust_flows(
        self, kind: RelationshipKind
    ) -> None:
        assert kind.generates, f"{kind} generates nothing"
        assert kind.prompt, f"{kind} has no business-language prompt"
        assert isinstance(kind.carries_trust, bool)


class TestJourneysAndBindings:
    async def test_a_journey_may_contain_a_declared_black_box(
        self, started_database: Database, tenant_id: str
    ) -> None:
        """The case a lineage scanner cannot reach and a human describes in one
        sentence: a mainframe job with no dataset to point at."""
        async with started_database.unit_of_work() as uow:
            trade, _ = await _declare_dataset(uow, tenant_id, slug="trades", name="Trades")
            _, journey = await uow.journeys.create(
                tenant_id=tenant_id,
                name="Trade capture to FRTB",
                slug="frtb",
                criticality=1,
                steps_json=[
                    {"ordinal": 0, "kind": "dataset", "dataset_id": trade.id},
                    {
                        "ordinal": 1,
                        "kind": "black_box",
                        "description": "Overnight COBOL enrichment on the mainframe",
                        "expected_latency_seconds": 5400,
                    },
                ],
            )
            assert journey.step_count == 2
            assert journey.dataset_ids == [trade.id]
            assert [j.slug for j in await uow.journeys.containing(tenant_id, trade.id)] == ["frtb"]

    async def test_binding_drift_is_detectable_and_routed_by_declaration(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            dataset, _ = await _declare_dataset(uow, tenant_id)
            connection, _ = await uow.connections.create(
                tenant_id=tenant_id,
                name="Risk warehouse",
                slug="risk-wh",
                source_type="snowflake",
                credential_ref="vault://prama/risk-wh",
                health_state="healthy",
            )
            binding, version = await uow.bindings.create(
                tenant_id=tenant_id,
                target_kind="dataset",
                dataset_id=dataset.id,
                connection_id=connection.id,
                physical_ref_json={"schema": "RISK", "object": "POSITIONS_EOD"},
                status="confirmed",
                drift_state="intact",
            )
            assert version.is_intact and not version.has_drifted
            assert await uow.bindings.drifted(tenant_id) == []

            # The column vanishes beneath the declaration.
            await uow.bindings.amend(
                binding.id,
                tenant_id=tenant_id,
                drift_state="missing",
                provenance=Provenance(reason="re-examination found the object absent"),
            )
            drifted = await uow.bindings.drifted(tenant_id)
            assert len(drifted) == 1 and drifted[0].has_drifted

    async def test_a_connection_never_stores_a_secret(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            _, connection = await uow.connections.create(
                tenant_id=tenant_id,
                name="Core banking",
                slug="core",
                source_type="db2_zos",
                credential_ref="vault://prama/core",
                config_json={"host": "mainframe.internal", "port": 446},
            )
            serialised = str(connection.to_dict())
            assert "vault://" in connection.credential_ref
            assert "password" not in serialised.lower()


class TestConcepts:
    async def test_attributes_across_datasets_map_to_one_canonical_property(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            concept, _ = await uow.concepts.create(tenant_id=tenant_id, name="Party")
            prop, _ = await uow.concept_properties.create(
                tenant_id=tenant_id,
                identity_fields={"concept_id": concept.id},
                name="LEI",
                semantic_type="lei",
                is_identifier=True,
            )
            for slug in ("exposures", "counterparties"):
                dataset, _ = await _declare_dataset(uow, tenant_id, slug=slug, name=slug)
                await uow.attributes.create(
                    tenant_id=tenant_id,
                    identity_fields={"dataset_id": dataset.id},
                    name="counterparty_lei",
                    concept_property_id=prop.id,
                    semantic_type="lei",
                )
            mapped = await uow.attributes.mapped_to_property(prop.id)
            assert len(mapped) == 2  # author once, enforce everywhere

    async def test_properties_belong_to_their_concept(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            concept, _ = await uow.concepts.create(tenant_id=tenant_id, name="Instrument")
            for name in ("ISIN", "CUSIP"):
                await uow.concept_properties.create(
                    tenant_id=tenant_id,
                    identity_fields={"concept_id": concept.id},
                    name=name,
                    is_identifier=True,
                )
            assert [p.name for p in await uow.concept_properties.for_concept(concept.id)] == [
                "CUSIP",
                "ISIN",
            ]


class TestTenantIsolation:
    async def test_declarations_do_not_leak_across_tenants(
        self, started_database: Database
    ) -> None:
        async with started_database.unit_of_work() as uow:
            a = uow.tenants.create(slug="bank-a", display_name="Bank A")
            b = uow.tenants.create(slug="bank-b", display_name="Bank B")
            await uow.flush()
            await _declare_dataset(uow, str(a.id), slug="positions")
            assert len(await uow.datasets.list_current(str(a.id))) == 1
            assert await uow.datasets.list_current(str(b.id)) == []
            assert await uow.datasets.count_current(str(b.id)) == 0
