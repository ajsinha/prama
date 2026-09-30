"""The configuration engine adopted from DishtaYantra's properties_configurator.py.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from prama.core.config import (
    ConfigParseError,
    ConfigurationBuilder,
    PropertiesConfigurator,
    flatten_yaml,
    load_configuration,
    parse_config_file,
)
from prama.core.errors import ConfigError


class TestTheParserAsDishtaYantraHasIt:
    def test_yaml_flattens_to_dotted_strings_with_lists_joined_and_indexed(self) -> None:
        flat = flatten_yaml({"db": {"port": 5432, "tls": True, "hosts": ["a", "b"], "x": None}})
        assert flat == {
            "db.port": "5432",
            "db.tls": "true",
            "db.hosts": "a,b",
            "db.hosts.0": "a",
            "db.hosts.1": "b",
            "db.x": "",
        }

    def test_a_list_of_mappings_is_indexed_only(self) -> None:
        flat = flatten_yaml({"roots": [{"path": "/a"}, {"path": "/b"}]})
        assert flat == {"roots.0.path": "/a", "roots.1.path": "/b"}

    def test_the_typed_view_keeps_what_yaml_wrote(self) -> None:
        assert flatten_yaml({"db": {"port": 5432, "hosts": ["a"]}}, typed=True) == {
            "db.port": 5432,
            "db.hosts": ["a"],
        }

    def test_properties_files_accept_both_separators_and_three_comment_styles(
        self, tmp_path: Path
    ) -> None:
        props = tmp_path / "app.properties"
        props.write_text("# c\n! c\n// c\ndb.host = h\ndb.port: 5432\n")
        assert parse_config_file(props) == {"db.host": "h", "db.port": "5432"}

    def test_a_malformed_properties_line_is_refused_not_skipped(self, tmp_path: Path) -> None:
        """A line nobody reads is a setting somebody believes they made."""
        props = tmp_path / "app.properties"
        props.write_text("db.host = h\nthis is not a setting\n")
        with pytest.raises(ConfigParseError, match=":2 is not a key/value line"):
            parse_config_file(props)


class TestResolution:
    def _config(self, values: dict, environ: dict | None = None):  # type: ignore[no-untyped-def]
        return (
            ConfigurationBuilder()
            .with_mapping(values, name="test")
            .with_environment(environ or {})
            .build()
        )

    def test_a_nested_reference_resolves_from_the_inside_out(self) -> None:
        """DishtaYantra's algorithm: the innermost placeholder first."""
        config = self._config(
            {"env": "prod", "db": {"prod": {"host": "p.example"}, "url": "${db.${env}.host}"}}
        )
        assert config.get_str("db.url") == "p.example"

    def test_a_default_keeps_everything_after_the_first_colon(self) -> None:
        config = self._config({"url": "${SERVICE_URL:http://localhost:8080/api}"})
        assert config.get_str("url") == "http://localhost:8080/api"

    def test_the_environment_wins_over_configuration_in_a_placeholder(self) -> None:
        config = self._config({"host": "file", "url": "${host}"}, {"host": "env"})
        assert config.get_str("url") == "env"

    def test_unresolved_is_still_an_error_not_a_literal(self) -> None:
        """DishtaYantra leaves the placeholder in place; Prama refuses."""
        with pytest.raises(ConfigError, match="no value for"):
            self._config({"password": "${DB_PASSWORD}"})

    def test_an_escaped_placeholder_is_not_resolved_even_nested(self) -> None:
        config = self._config({"a": "b", "text": "$${a} and ${a}"})
        assert config.get_str("text") == "${a} and b"


class TestPropertiesConfigurator:
    def test_precedence_is_file_then_environment_then_command_line(self, tmp_path: Path) -> None:
        conf = tmp_path / "application.yaml"
        conf.write_text("db:\n  host: file-host\n  port: 5432\n  user: file-user\n")
        props = PropertiesConfigurator(
            [conf], environ={"db.port": "6000"}, argv=["--db.user=cli-user", "ignored"]
        )
        assert props.get("db.host") == "file-host"
        assert props.get_source("db.host") == f"file:{conf}"
        assert (props.get_int("db.port"), props.get_source("db.port")) == (6000, "env")
        assert (props.get("db.user"), props.get_source("db.user")) == ("cli-user", "commandline")

    def test_the_local_overlay_follows_its_file_and_wins(self, tmp_path: Path) -> None:
        (tmp_path / "application.yaml").write_text("secret: ''\nname: prama\n")
        (tmp_path / "application.local.yaml").write_text("secret: s3cr3t\n")
        props = PropertiesConfigurator(str(tmp_path / "application.yaml"), environ={}, argv=[])
        assert props.get("secret") == "s3cr3t" and props.get("name") == "prama"

    def test_changes_are_noticed_and_reloaded_on_request(self, tmp_path: Path) -> None:
        """What DishtaYantra's reload thread did, without a thread of its own."""
        conf = tmp_path / "application.yaml"
        conf.write_text("level: info\n")
        props = PropertiesConfigurator([conf], environ={}, argv=[])
        assert not props.changed()
        time.sleep(0.01)
        conf.write_text("level: debug\n")
        os.utime(conf, (time.time() + 5, time.time() + 5))
        assert props.changed()
        props.reload()
        assert props.get("level") == "debug" and not props.changed()

    def test_content_in_text_and_json_resolves_against_the_properties(self) -> None:
        props = PropertiesConfigurator(properties={"host": "h", "port": "1"}, environ={}, argv=[])
        assert props.resolve_string_content("http://${host}:${port}/") == "http://h:1/"
        assert props.resolve_string_json_content('{"url": "${host}"}') == {"url": "h"}
        assert props.get_properties_by_pattern(r"^ho") == {"host": "h"}


class TestTheViewOfPramasConfiguration:
    def test_config_properties_reads_the_same_values_the_dishtayantra_way(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "application.yaml"
        conf.write_text("server:\n  port: 5977\nruns:\n  roots: [a, b]\n")
        props = load_configuration(conf, environ={}).properties()
        assert props.get("server.port") == "5977" and props.get_int("server.port") == 5977
        assert props.get_list("runs.roots") == ["a", "b"] and props.get("runs.roots.1") == "b"
        assert props.get_source("server.port") == str(conf)
        assert props.get_source("database.dialect") == "built-in defaults"
        assert props.resolve_string_content("port ${server.port}") == "port 5977"
