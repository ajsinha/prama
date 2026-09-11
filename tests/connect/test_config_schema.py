"""Configuration forms derived from connector code.

The property under test is not "the form has fields" but "the form cannot
disagree with the connector" — which is the only reason to derive it at all.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast

import pytest

from prama.connect.builtin import register_builtin
from prama.connect.config_schema import (
    ConfigSchemaDeriver,
    ConnectorConfigSchema,
    FieldPresentation,
    InputKind,
)
from prama.connect.registry import ConnectorRegistry
from prama.connect.sources.filesystem import FilesystemConnector
from prama.connect.sources.sqlite import SqliteConnector
from prama.core.errors import ValidationError


class TestDerivation:
    def test_fields_are_found_with_their_real_defaults(self) -> None:
        fields = ConfigSchemaDeriver().derive(SqliteConnector)
        assert fields["busy_timeout_seconds"].default == 5.0
        assert fields["include_views"].default is True

    def test_a_read_with_no_default_is_required(self) -> None:
        # The connector cannot work without it, so the form must say so.
        fields = ConfigSchemaDeriver().derive(SqliteConnector)
        assert fields["database_path"].required is True
        assert fields["busy_timeout_seconds"].required is False

    def test_a_new_option_appears_the_moment_the_code_reads_it(self) -> None:
        source = ast.parse(
            "class C:\n"
            "    def __init__(self, config):\n"
            "        self.a = config.get('brand_new_option', 7)\n"
        )
        fields = ConfigSchemaDeriver().derive_source(source)
        assert fields["brand_new_option"].default == 7

    def test_a_computed_default_is_recorded_but_not_rendered(self) -> None:
        source = ast.parse(
            "class C:\n"
            "    def __init__(self, config):\n"
            "        self.a = config.get('derived', compute())\n"
        )
        field = ConfigSchemaDeriver().derive_source(source)["derived"]
        assert field.required is False  # it has a default, just not a literal one
        assert field.default is None

    def test_a_non_literal_key_is_ignored_rather_than_guessed_at(self) -> None:
        # A deriver that followed indirection would be sometimes right and
        # sometimes silently wrong, which defeats the purpose.
        source = ast.parse(
            "class C:\n"
            "    def __init__(self, config, name):\n"
            "        self.a = config.get(name, 1)\n"
        )
        assert ConfigSchemaDeriver().derive_source(source) == {}

    def test_unrelated_get_calls_are_not_mistaken_for_configuration(self) -> None:
        source = ast.parse(
            "class C:\n"
            "    def __init__(self, config, headers):\n"
            "        self.a = headers.get('accept', 'json')\n"
        )
        assert ConfigSchemaDeriver().derive_source(source) == {}


class TestOverlay:
    def test_the_overlay_adds_presentation_only(self) -> None:
        schema = ConnectorConfigSchema.build(
            SqliteConnector,
            overlay={
                "database_path": FieldPresentation(
                    label="Database file", help="Opened read-only.", input_kind=InputKind.PATH
                )
            },
        )
        field = schema.field("database_path")
        assert field.display_label == "Database file"
        assert field.inferred_kind is InputKind.PATH
        assert field.required is True  # still derived from the code

    def test_the_overlay_cannot_invent_a_field(self) -> None:
        schema = ConnectorConfigSchema.build(
            SqliteConnector,
            overlay={"imaginary_option": FieldPresentation(label="Nope")},
        )
        assert schema.field("imaginary_option") is None
        assert schema.audit()  # and it is reported rather than ignored
        assert "never reads" in schema.audit()[0]

    def test_input_kinds_are_inferred_from_defaults_when_not_overlaid(self) -> None:
        schema = ConnectorConfigSchema.build(SqliteConnector)
        assert schema.field("include_views").inferred_kind is InputKind.BOOLEAN
        assert schema.field("busy_timeout_seconds").inferred_kind is InputKind.NUMBER

    def test_fields_are_grouped_and_ordered_for_a_human(self) -> None:
        registry = register_builtin(ConnectorRegistry())
        groups = registry.schema("filesystem").groups()
        assert list(groups) == ["connection", "advanced"]
        assert groups["connection"][0].name == "root_path"


class TestValidation:
    def test_a_missing_required_field_is_named(self) -> None:
        schema = ConnectorConfigSchema.build(SqliteConnector)
        with pytest.raises(ValidationError) as caught:
            schema.validate({})
        assert "database_path" in str(caught.value)
        assert "no default" in caught.value.remedy

    def test_a_complete_configuration_passes(self) -> None:
        ConnectorConfigSchema.build(SqliteConnector).validate({"database_path": "/tmp/x.db"})

    def test_a_secret_in_configuration_is_refused(self) -> None:
        schema = ConnectorConfigSchema.build(
            FilesystemConnector,
            extra_fields=(),
            overlay={"root_path": FieldPresentation(secret=True)},
        )
        with pytest.raises(ValidationError) as caught:
            schema.validate({"root_path": "actually-a-secret"})
        assert "credential_ref" in caught.value.remedy

    def test_a_secret_default_is_never_emitted(self) -> None:
        schema = ConnectorConfigSchema.build(
            SqliteConnector,
            overlay={"busy_timeout_seconds": FieldPresentation(secret=True)},
        )
        assert schema.field("busy_timeout_seconds").to_dict()["default"] is None


class TestRegistry:
    def test_the_catalogue_is_everything_a_source_picker_needs(self) -> None:
        registry = register_builtin(ConnectorRegistry())
        catalogue = {entry["key"]: entry for entry in registry.catalogue()}
        assert set(catalogue) == {
            "clickhouse",
            "filesystem",
            "jdbc",
            "mongodb",
            "objectstore",
            "postgresql",
            "rest",
            "snowflake",
            "sqlite",
        }
        assert catalogue["sqlite"]["kind"] == "relational"
        assert catalogue["sqlite"]["form"]["groups"]
        assert "pushdown.sql" in catalogue["sqlite"]["capabilities"]
        # A source with no query engine still needs a form, and its empty
        # capability list is the honest answer rather than a gap.
        assert catalogue["rest"]["kind"] == "api"
        assert catalogue["rest"]["form"]["groups"]
        assert catalogue["rest"]["capabilities"] == []
        # A source nobody has run still appears in the picker, and its warning
        # travels with it. Hiding it would be a different lie from overstating
        # it, and the person choosing a source is exactly who needs to know.
        assert "NOT YET VERIFIED" in catalogue["snowflake"]["description"]

    def test_no_builtin_overlay_disagrees_with_its_connector(self) -> None:
        """The check that makes the derived form worth deriving.

        A form that has drifted from its connector is the defect this design
        exists to prevent, so it fails the build rather than appearing as a
        subtly wrong input six months later.
        """
        assert register_builtin(ConnectorRegistry()).audit() == []

    def test_creating_a_connector_validates_before_connecting(self) -> None:
        # A missing field should be a message beside the input, not a driver
        # error twenty seconds into a connection attempt.
        registry = register_builtin(ConnectorRegistry())
        with pytest.raises(ValidationError):
            registry.create("sqlite", {})

    def test_an_unknown_connector_lists_what_is_available(self) -> None:
        from prama.core.errors import RegistryError

        registry = register_builtin(ConnectorRegistry())
        with pytest.raises(RegistryError) as caught:
            registry.get("teradata")
        assert "sqlite" in caught.value.remedy

    def test_connectors_are_findable_by_source_kind(self) -> None:
        from prama.connect import SourceKind

        registry = register_builtin(ConnectorRegistry())
        assert registry.of_kind(SourceKind.RELATIONAL) == [
            "clickhouse",
            "jdbc",
            "postgresql",
            "snowflake",
            "sqlite",
        ]
        assert registry.of_kind(SourceKind.FILESYSTEM) == ["filesystem"]
