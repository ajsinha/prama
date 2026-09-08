"""GitOps: round-trip fidelity and bidirectional drift.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ValidationError
from prama.db import Database
from prama.semantic.gitops import (
    GITOPS_VERSION,
    DriftDetector,
    DriftDirection,
    EstateSerialiser,
)
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.service import DatasetService, RelationshipService
from prama.semantic.values import Frequency, Grain, Rhythm


class TestSerialisation:
    async def test_a_dataset_round_trips_through_yaml(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            service = DatasetService(uow)
            dataset, version = await service.declare(
                tenant_id=tenant_id,
                name="Positions EOD",
                description="Daily end-of-day positions.",
                owner_id="alice",
                criticality=2,
                authored_by="alice",
                approved_by="bob",  # Tier 2 requires review
                shape="feed",
                grain=Grain(
                    ("account_id", "instrument_id", "as_of_date"),
                    "one position per account per instrument per business day",
                ),
                rhythm=Rhythm(
                    Frequency.DAILY,
                    arrival_by="06:30",
                    calendar="TARGET2",
                    volume_drivers=("trading_days", "month_end"),
                ),
                tags=["risk", "frtb"],
            )
            await service.declare_attribute(
                tenant_id=tenant_id,
                dataset_id=str(dataset.id),
                name="notional_amount",
                definition="Face value of the position.",
                interpretation="Gross of collateral; excludes intercompany.",
                semantic_type="monetary_amount",
                is_cde=True,
                obligations=["FRTB"],
            )
            attributes = await uow.attributes.for_dataset(str(dataset.id))

            serialiser = EstateSerialiser()
            document = serialiser.dataset_document(version, attributes)
            text = serialiser.dump(document)
            restored = serialiser.load(text)

        assert restored == document
        assert restored["metadata"]["slug"] == "positions_eod"
        assert restored["spec"]["grain"]["attributes"] == [
            "account_id",
            "instrument_id",
            "as_of_date",
        ]
        assert restored["spec"]["rhythm"]["volume_drivers"] == ["trading_days", "month_end"]
        assert restored["attributes"][0]["cde"] is True
        assert "intercompany" in restored["attributes"][0]["interpretation"]

    async def test_empty_values_are_omitted_so_diffs_stay_readable(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            _, version = await DatasetService(uow).declare(tenant_id=tenant_id, name="Bare Dataset")
            document = EstateSerialiser().dataset_document(version, [])
        # A document full of nulls is a document nobody reads.
        assert "jurisdiction" not in document["spec"]
        assert "purpose" not in document["spec"]
        assert document["spec"]["criticality"] == 4

    async def test_a_relationship_serialises_by_slug_not_by_opaque_id(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            datasets = DatasetService(uow)
            sub, sub_v = await datasets.declare(tenant_id=tenant_id, name="Sub-ledger")
            gl, gl_v = await datasets.declare(tenant_id=tenant_id, name="General Ledger")
            _, version = await RelationshipService(uow).declare(
                tenant_id=tenant_id,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=str(sub.id),
                    to_dataset_id=str(gl.id),
                    match_keys=(MatchKey("account_code"), MatchKey("cost_centre")),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="EUR"),
                ),
            )
            slugs = {str(sub.id): sub_v.slug, str(gl.id): gl_v.slug}
            document = EstateSerialiser().relationship_document(version, slug_of=slugs)

        # A reviewer reads slugs, not ULIDs.
        assert document["spec"]["from"] == "sub_ledger"
        assert document["spec"]["to"] == "general_ledger"
        assert document["spec"]["tolerance"]["absolute"] == 1.0

    async def test_a_journey_serialises_black_box_steps(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            dataset, dv = await DatasetService(uow).declare(tenant_id=tenant_id, name="Trades")
            _, journey = await uow.journeys.create(
                tenant_id=tenant_id,
                name="Trade to FRTB",
                slug="frtb",
                steps_json=[
                    {"ordinal": 0, "kind": "dataset", "dataset_id": str(dataset.id)},
                    {
                        "ordinal": 1,
                        "kind": "black_box",
                        "description": "Overnight COBOL enrichment",
                    },
                ],
            )
            document = EstateSerialiser().journey_document(
                journey, slug_of={str(dataset.id): dv.slug}
            )
        assert document["spec"]["steps"][0]["dataset"] == "trades"
        assert "dataset_id" not in document["spec"]["steps"][0]
        assert document["spec"]["steps"][1]["kind"] == "black_box"

    async def test_a_connection_serialises_its_reference_and_never_a_secret(
        self, started_database: Database, tenant_id: str
    ) -> None:
        async with started_database.unit_of_work() as uow:
            _, connection = await uow.connections.create(
                tenant_id=tenant_id,
                name="Risk warehouse",
                slug="risk_wh",
                source_type="snowflake",
                credential_ref="vault://prama/risk-wh",
                config_json={"account": "acme", "warehouse": "RISK_WH"},
            )
            text = EstateSerialiser().dump(EstateSerialiser().connection_document(connection))
        assert "vault://prama/risk-wh" in text
        assert "password" not in text.lower()
        assert "secret" not in text.lower()


class TestDocumentValidation:
    def test_a_non_mapping_document_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must be a mapping"):
            EstateSerialiser().load("- just\n- a list\n")

    def test_a_missing_kind_is_named(self) -> None:
        with pytest.raises(ValidationError, match="'kind'"):
            EstateSerialiser().load(f"apiVersion: prama/v{GITOPS_VERSION}\nmetadata: {{slug: x}}\n")

    def test_a_future_layout_version_is_refused_rather_than_guessed_at(self) -> None:
        with pytest.raises(ValidationError, match="layout version"):
            EstateSerialiser().load("apiVersion: prama/v99\nkind: Dataset\nmetadata: {slug: x}\n")

    def test_invalid_yaml_reports_the_syntax_error(self) -> None:
        with pytest.raises(ValidationError, match="invalid YAML"):
            EstateSerialiser().load("apiVersion: [unclosed\n")

    def test_the_manifest_records_what_an_export_contained(self) -> None:
        text = EstateSerialiser().manifest(
            tenant="acme-bank", counts={"datasets": 42, "relationships": 17}
        )
        restored = EstateSerialiser().load(text)
        assert restored["contents"] == {"datasets": 42, "relationships": 17}


class TestDriftDetection:
    def test_identical_states_are_in_sync(self) -> None:
        state = {"positions_eod": {"name": "Positions EOD", "criticality": 1}}
        drifts = DriftDetector().compare(state, dict(state), kind="Dataset")
        assert drifts == []
        assert "in sync" in DriftDetector.summarise(drifts)

    def test_drift_is_reported_in_both_directions(self) -> None:
        store = {"a": {"name": "A"}, "shared": {"name": "Shared"}}
        repository = {"b": {"name": "B"}, "shared": {"name": "Shared"}}
        drifts = DriftDetector().compare(store, repository, kind="Dataset")
        directions = {d.identifier: d.direction for d in drifts}
        assert directions["a"] is DriftDirection.ONLY_IN_STORE
        assert directions["b"] is DriftDirection.ONLY_IN_GIT
        assert "shared" not in directions

    def test_a_differing_field_is_named(self) -> None:
        drifts = DriftDetector().compare(
            {"x": {"name": "X", "criticality": 1}},
            {"x": {"name": "X", "criticality": 3}},
            kind="Dataset",
        )
        assert drifts[0].direction is DriftDirection.DIFFERENT
        assert drifts[0].fields == ("criticality",)
        assert "criticality" in drifts[0].render()

    def test_versioning_columns_are_not_compared(self) -> None:
        # They are the store's business, not the repository's.
        drifts = DriftDetector().compare(
            {"x": {"name": "X", "version": 7, "recorded_at": "2026-01-01"}},
            {"x": {"name": "X"}},
            kind="Dataset",
        )
        assert drifts == []

    def test_representation_differences_are_not_drift(self) -> None:
        # An absent key and an explicit null mean the same thing to a reviewer.
        drifts = DriftDetector().compare(
            {"x": {"name": "X", "purpose": None, "tags": []}},
            {"x": {"name": "X"}},
            kind="Dataset",
        )
        assert drifts == []

    def test_nested_ordering_is_not_drift(self) -> None:
        drifts = DriftDetector().compare(
            {"x": {"tolerance": {"absolute": 1.0, "currency": "EUR"}}},
            {"x": {"tolerance": {"currency": "EUR", "absolute": 1.0}}},
            kind="Relationship",
        )
        assert drifts == []

    def test_neither_side_wins_automatically(self) -> None:
        """Both edits are legitimate; the disagreement is surfaced, not resolved."""
        drifts = DriftDetector().compare(
            {"x": {"owner": "alice"}}, {"x": {"owner": "bob"}}, kind="Dataset"
        )
        summary = DriftDetector.summarise(drifts)
        assert "declared differently" in summary
        assert "resolved" not in summary


class TestPaths:
    def test_domain_scoped_objects_live_under_their_domain(self) -> None:
        serialiser = EstateSerialiser()
        assert serialiser.path_for("Dataset", "positions_eod", domain="credit_risk") == (
            "prama/domains/credit_risk/datasets/positions_eod.yaml"
        )
        assert serialiser.path_for("Connection", "risk_wh") == ("prama/connections/risk_wh.yaml")
