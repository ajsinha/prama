"""Configuration subsystem.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from prama.core.config import ConfigurationBuilder, load_configuration
from prama.core.config.coercion import Coercer
from prama.core.config.resolver import PlaceholderResolver
from prama.core.config.sources import deep_merge, expand_dotted
from prama.core.errors import (
    ConfigError,
    ConfigMissingError,
    ConfigTypeError,
    SecretMissingError,
)


class TestLayering:
    def test_later_source_overrides_earlier_key_by_key(self) -> None:
        config = (
            ConfigurationBuilder()
            .with_defaults({"database": {"dialect": "sqlite", "pool": {"size": 10}}})
            .with_mapping({"database": {"pool": {"size": 40}}}, name="overlay")
            .build()
        )
        # The override touched one key; the sibling survived.
        assert config.get_int("database.pool.size") == 40
        assert config.get_str("database.dialect") == "sqlite"

    def test_environment_beats_file(self, tmp_path: Path) -> None:
        path = tmp_path / "application.yaml"
        path.write_text("database:\n  dialect: sqlite\n")
        config = load_configuration(path, environ={"PRAMA_DATABASE__DIALECT": "postgres"})
        assert config.get_str("database.dialect") == "postgres"

    def test_cli_beats_environment(self, tmp_path: Path) -> None:
        path = tmp_path / "application.yaml"
        path.write_text("logging:\n  level: INFO\n")
        config = load_configuration(
            path,
            overrides=["logging.level=DEBUG"],
            environ={"PRAMA_LOGGING__LEVEL": "WARNING"},
        )
        assert config.get_str("logging.level") == "DEBUG"

    def test_local_overlay_is_loaded_automatically(self, tmp_path: Path) -> None:
        (tmp_path / "application.yaml").write_text("security:\n  session_secret: ''\n")
        (tmp_path / "application.local.yaml").write_text("security:\n  session_secret: s3cr3t\n")
        config = load_configuration(tmp_path / "application.yaml", environ={})
        assert config.require_secret("security.session_secret") == "s3cr3t"

    def test_provenance_names_the_winning_source(self, tmp_path: Path) -> None:
        path = tmp_path / "application.yaml"
        path.write_text("app:\n  name: FromFile\n")
        config = load_configuration(path, environ={})
        assert config.provenance("app.name") == str(path)

    def test_missing_named_file_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError) as caught:
            load_configuration(tmp_path / "nope.yaml", environ={})
        assert caught.value.code == "CONFIG.FILE_MISSING"

    def test_absent_default_file_is_not_an_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        config = load_configuration(environ={})
        assert config.get_str("database.dialect") == "sqlite"  # from built-in defaults


class TestPlaceholders:
    def test_environment_then_configuration(self) -> None:
        resolver = PlaceholderResolver({"DB_HOST": "db.internal"})
        result = resolver.resolve_tree(
            {"paths": {"data": "/var/prama"}, "a": "${DB_HOST}", "b": "${paths.data}/evidence"}
        )
        assert result["a"] == "db.internal"
        assert result["b"] == "/var/prama/evidence"

    def test_default_is_used_when_unset(self) -> None:
        assert PlaceholderResolver({}).resolve_tree({"p": "${NOPE:5432}"})["p"] == "5432"

    def test_unresolved_without_default_is_an_error_not_empty_string(self) -> None:
        with pytest.raises(ConfigError) as caught:
            PlaceholderResolver({}).resolve_tree({"p": "${MISSING}"})
        assert caught.value.code == "CONFIG.PLACEHOLDER_UNRESOLVED"

    def test_doubled_dollar_escapes(self) -> None:
        assert PlaceholderResolver({}).resolve_tree({"p": "$${LITERAL}"})["p"] == "${LITERAL}"

    def test_cycle_is_reported_with_the_chain(self) -> None:
        with pytest.raises(ConfigError) as caught:
            PlaceholderResolver({}).resolve_tree({"a": "${b}", "b": "${a}"})
        assert caught.value.code == "CONFIG.PLACEHOLDER_CYCLE"
        assert "->" in str(caught.value)

    def test_non_string_values_are_untouched(self) -> None:
        assert PlaceholderResolver({}).resolve_tree({"n": 5, "f": 1.5, "b": True})["n"] == 5


class TestCoercion:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("on", True), ("OFF", False), ("yes", True), ("0", False), (1, True), (True, True)],
    )
    def test_booleans(self, raw: object, expected: bool) -> None:
        assert Coercer("k").to_bool(raw) is expected

    def test_a_non_boolean_string_is_refused_not_treated_as_truthy(self) -> None:
        # "false" is truthy in Python; silently accepting it is the classic defect.
        with pytest.raises(ConfigTypeError):
            Coercer("k").to_bool("maybe")

    @pytest.mark.parametrize(
        ("raw", "seconds"),
        [("500ms", 0.5), ("30s", 30.0), ("5m", 300.0), ("2h", 7200.0), ("1d", 86400.0), (7, 7.0)],
    )
    def test_durations(self, raw: object, seconds: float) -> None:
        assert Coercer("k").to_duration_seconds(raw) == seconds

    @pytest.mark.parametrize(
        ("raw", "size"),
        [("1024", 1024), ("512kb", 512_000), ("256mb", 256_000_000), ("4gib", 4 * 1024**3)],
    )
    def test_byte_sizes_distinguish_decimal_from_binary(self, raw: str, size: int) -> None:
        assert Coercer("k").to_bytes(raw) == size

    def test_comma_separated_string_becomes_a_list(self) -> None:
        assert Coercer("k").to_list("a, b ,c") == ["a", "b", "c"]


class TestSecrets:
    def test_empty_shipped_secret_refuses_rather_than_defaulting(self) -> None:
        config = ConfigurationBuilder().with_defaults({"security": {"session_secret": ""}}).build()
        with pytest.raises(SecretMissingError) as caught:
            config.require_secret("security.session_secret")
        assert "application.local.yaml" in caught.value.remedy

    def test_flatten_redacts_by_default(self) -> None:
        config = (
            ConfigurationBuilder()
            .with_defaults({"security": {"session_secret": "hunter2"}, "app": {"name": "Prama"}})
            .build()
        )
        flat = config.flatten()
        assert flat["security.session_secret"] == "***"
        assert flat["app.name"] == "Prama"


class TestBinding:
    def test_binds_a_section_to_a_dataclass_with_coercion(self) -> None:
        @dataclasses.dataclass(frozen=True)
        class Sub:
            size: int
            pre_ping: bool
            name: str = "default"

        config = (
            ConfigurationBuilder().with_defaults({"pool": {"size": "40", "pre_ping": "no"}}).build()
        )
        bound = config.bind("pool", Sub)
        assert bound == Sub(size=40, pre_ping=False, name="default")

    def test_missing_required_field_names_the_key(self) -> None:
        @dataclasses.dataclass(frozen=True)
        class Sub:
            required: str

        config = ConfigurationBuilder().with_defaults({"pool": {}}).build()
        with pytest.raises(ConfigMissingError) as caught:
            config.bind("pool", Sub)
        assert "pool.required" in str(caught.value)


class TestMergeHelpers:
    def test_dotted_keys_expand(self) -> None:
        assert expand_dotted({"a.b.c": 1, "a.d": 2}) == {"a": {"b": {"c": 1}, "d": 2}}

    def test_scalar_versus_section_conflict_is_reported(self) -> None:
        with pytest.raises(ConfigError) as caught:
            expand_dotted({"a": 1, "a.b": 2})
        assert caught.value.code == "CONFIG.KEY_CONFLICT"

    def test_lists_replace_rather_than_concatenate(self) -> None:
        # Concatenation looks helpful and makes removing a default impossible.
        merged = deep_merge({"x": [1, 2, 3]}, {"x": [9]})
        assert merged["x"] == [9]


class TestServerPort:
    """The listener is stated once, in configuration, and it is 5900."""

    def test_default_port_is_5900(self) -> None:
        from prama.core.config import load_configuration

        assert load_configuration().get_int("server.port") == 5900

    def test_serve_takes_its_port_from_configuration_not_argparse(self) -> None:
        import argparse

        from prama.cli.commands import ServeCommand

        parser = argparse.ArgumentParser()
        ServeCommand().configure(parser)
        # A literal default here would be a second authority that drifts.
        assert parser.parse_args([]).port is None
