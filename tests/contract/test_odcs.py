"""ODCS import and export.

A data contract and a Prama declaration are the same idea reached from two
directions, and most of these tests are about the fields where they are not.

An importer that silently discarded half a contract produces a declaration that
looks complete and generates a third of the controls it should — so what does
not come across is asserted to be *reported*, not merely absent.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.contract.odcs import ODCS_VERSION, dump, load
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.semantic.values import Criticality, Optionality


def contract(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "apiVersion": ODCS_VERSION,
        "kind": "DataContract",
        "dataProduct": "positions",
        "criticality": "critical",
        "description": {"purpose": "End of day positions", "usage": "Risk aggregation"},
        "tags": ["risk"],
        "schema": [
            {
                "name": "positions_eod",
                "description": "EOD positions",
                "properties": [
                    {
                        "name": "account_id",
                        "logicalType": "string",
                        "required": True,
                        "criticalDataElement": True,
                        "description": "the account",
                    },
                    {
                        "name": "notional",
                        "logicalType": "number",
                        "required": True,
                        "precision": 18,
                        "scale": 2,
                    },
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestImport:
    def test_the_dataset_and_its_attributes_come_across(self) -> None:
        result = load(contract())
        assert result.declaration is not None
        assert result.declaration.name == "positions_eod"
        assert [a.name for a in result.declaration.attributes] == [
            "account_id",
            "notional",
        ]

    def test_required_becomes_mandatory(self) -> None:
        [account, _] = load(contract()).declaration.attributes
        assert account.optionality is Optionality.MANDATORY

    def test_absent_required_becomes_optional_rather_than_mandatory(self) -> None:
        """The safe direction. Importing an unstated field as mandatory
        generates a completeness control nobody agreed to, and it fires
        immediately."""
        document = contract()
        document["schema"][0]["properties"][0].pop("required")
        [account, _] = load(document).declaration.attributes
        assert account.optionality is Optionality.OPTIONAL

    def test_a_critical_data_element_is_carried(self) -> None:
        [account, _] = load(contract()).declaration.attributes
        assert account.is_cde

    def test_criticality_maps_to_a_tier(self) -> None:
        assert load(contract()).declaration.criticality is Criticality.TIER_1
        assert load(contract(criticality="low")).declaration.criticality is Criticality.TIER_4


class TestWhatDoesNotComeAcross:
    def test_an_unknown_type_is_kept_as_text_and_reported(self) -> None:
        """A type quietly coerced is a control generated against the wrong
        family."""
        document = contract()
        document["schema"][0]["properties"].append({"name": "shape", "logicalType": "geospatial"})
        result = load(document)
        assert any("geospatial" in note for note in result.ignored)
        assert result.declaration.attributes[-1].semantic_type == ""

    def test_fields_prama_has_no_home_for_are_named(self) -> None:
        result = load(contract(slaProperties=[{"property": "freshness"}]))
        assert any("slaProperties" in note for note in result.ignored)

    def test_a_second_schema_object_is_named_rather_than_dropped(self) -> None:
        """A contract describing four tables imported as one is three datasets
        nobody declared."""
        document = contract()
        document["schema"].append({"name": "trades", "properties": []})
        result = load(document)
        assert any("further schema object" in note for note in result.ignored)

    def test_defaults_are_distinguished_from_statements(self) -> None:
        """A defaulted value appears on a screen as though somebody chose it.
        ODCS has no grain and no rhythm, and a declaration that quietly carried
        Prama's defaults for them would be claiming decisions nobody made."""
        result = load(contract())
        assert any("grain" in note for note in result.defaulted)
        assert any("rhythm" in note for note in result.defaulted)
        assert not result.is_complete

    def test_the_summary_leads_with_the_defaults(self) -> None:
        described = load(contract(slaProperties=[{"property": "freshness"}])).describe()
        assert "hold defaults rather than statements" in described
        assert described.index("defaults") < described.index("not imported")

    def test_a_contract_with_no_schema_imports_nothing_and_says_why(self) -> None:
        result = load({"apiVersion": ODCS_VERSION, "kind": "DataContract"})
        assert result.declaration is None
        assert "no schema" in result.describe()


class TestExport:
    def test_it_produces_a_versioned_document(self) -> None:
        document = dump(load(contract()).declaration)
        assert document["apiVersion"] == ODCS_VERSION
        assert document["kind"] == "DataContract"

    def test_prama_only_fields_are_omitted_rather_than_invented(self) -> None:
        """Custom keys for grain and interpretation would produce a document
        that validates nowhere and that a consumer's tooling silently drops."""
        declaration = DatasetDeclaration(
            name="positions_eod",
            grain=("account_id",),
            attributes=(AttributeDeclaration(name="a", interpretation="signed, gross of fees"),),
        )
        document = dump(declaration)
        rendered = repr(document)
        assert "grain" not in rendered
        assert "interpretation" not in rendered
        assert "signed, gross of fees" not in rendered

    def test_a_mandatory_attribute_exports_as_required(self) -> None:
        declaration = DatasetDeclaration(
            name="d",
            attributes=(
                AttributeDeclaration(name="a", optionality=Optionality.MANDATORY),
                AttributeDeclaration(name="b", optionality=Optionality.OPTIONAL),
            ),
        )
        properties = dump(declaration)["schema"][0]["properties"]
        assert properties[0]["required"] is True
        assert properties[1]["required"] is False


class TestRoundTrip:
    """Exported and re-imported must be the same declaration.

    Anything surviving one direction and not the other is a field somebody
    loses on the first migration, so this is asserted rather than hoped for.
    """

    def test_the_fields_odcs_carries_survive_a_round_trip(self) -> None:
        original = load(contract()).declaration
        returned = load(dump(original)).declaration

        assert returned.name == original.name
        assert returned.criticality == original.criticality
        assert [a.name for a in returned.attributes] == [a.name for a in original.attributes]
        assert [a.optionality for a in returned.attributes] == [
            a.optionality for a in original.attributes
        ]
        assert [a.is_cde for a in returned.attributes] == [a.is_cde for a in original.attributes]

    def test_numeric_precision_and_scale_survive(self) -> None:
        original = load(contract()).declaration
        returned = load(dump(original)).declaration
        assert returned.attributes[1].numeric_precision == 18
        assert returned.attributes[1].numeric_scale == 2

    def test_a_second_round_trip_changes_nothing_further(self) -> None:
        """Stability, not just symmetry. A mapping that loses a little each time
        looks correct on the first comparison."""
        once = dump(load(contract()).declaration)
        twice = dump(load(once).declaration)
        assert once == twice

    def test_what_does_not_survive_is_what_the_importer_said(self) -> None:
        """The honest closing of the loop: grain is defaulted on import and
        omitted on export, and both halves say so rather than one of them
        quietly restoring it."""
        declaration = DatasetDeclaration(name="d", grain=("account_id",))
        returned = load(dump(declaration))
        assert not returned.declaration.grain
        assert any("grain" in note for note in returned.defaulted)
