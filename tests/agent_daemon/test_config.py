"""``agent.yaml``: parsed, validated whole, and never holding a credential.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from prama_agent.config import load_config, parse_config, server_settings
from prama_kernel.agent.residency import SampleDisposition
from prama_kernel.errors import ConfigError

EXAMPLE = """
server:
  url: https://prama.example.com
  ca_bundle: /etc/ssl/certs/prama-ca.pem
state_dir: state
sources:
  warehouse:
    engine: sqlite
    path: data/warehouse.db
  lake:
    engine: duckdb
    path: /srv/lake.duckdb
    datasets: [positions]
  ledger:
    engine: postgresql
    dsn: host=db.internal dbname=ledger user=prama_ro
    password_env: LEDGER_PASSWORD
residency:
  samples: mask
  may_send: [trade_id, ccy]
  never_send: [account_id]
  investigate_at: the zone's DQ workbench
poll:
  min_seconds: 10
  max_seconds: 120
spool:
  capacity: 1000
  batch_size: 100
logging:
  level: debug
  format: text
"""


def minimal(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "server": {"url": "https://prama.example.com"},
        "state_dir": "/var/lib/prama-agent",
        "sources": {"w": {"engine": "sqlite", "path": "/srv/w.db"}},
        "residency": {"samples": "withhold"},
    }
    raw.update(changes)
    return raw


def test_the_documented_example_parses(tmp_path: Path) -> None:
    path = tmp_path / "agent.yaml"
    path.write_text(EXAMPLE)
    config = load_config(path)
    assert config.server.url == "https://prama.example.com"
    assert config.state_dir == tmp_path / "state"  # relative to the file, not the cwd
    assert config.source("warehouse").path == str(tmp_path / "data" / "warehouse.db")
    assert config.source("ledger").engine == "postgres"  # postgresql is an alias
    assert config.residency.samples is SampleDisposition.MASK
    assert config.residency.may_send == ("trade_id", "ccy")
    assert config.poll.min_seconds == 10 and config.spool_capacity == 1000
    assert config.report_batch == 100 and config.log_level == "DEBUG"
    # Capabilities derive from the sources: an agent with an unconfined source
    # is not confined, and the engines include the names the server uses.
    assert config.engines == ("duckdb", "pg", "postgres", "postgresql", "sqlite")
    assert config.datasets == ()


def test_the_zone_defaults_to_the_enrolled_one_unless_written() -> None:
    assert not parse_config(minimal()).zone_declared
    declared = parse_config(minimal(residency={"samples": "withhold", "zone": "eu"}))
    assert declared.zone_declared and declared.residency.zone == "eu"


@pytest.mark.parametrize(
    ("source", "complaint"),
    [
        ({"engine": "postgres", "dsn": "host=db user=u", "password": "hunter2"}, "inline"),
        ({"engine": "postgres", "dsn": "postgresql://u:hunter2@db/ledger"}, "password inline"),
        ({"engine": "postgres", "dsn": "host=db user=u password=hunter2"}, "password inline"),
        ({"engine": "sqlite", "path": "/x.db", "token": "abc"}, "inline"),
    ],
)
def test_a_credential_written_inline_is_refused(source: dict[str, Any], complaint: str) -> None:
    with pytest.raises(ConfigError, match=complaint) as caught:
        parse_config(minimal(sources={"s": source}))
    # And the refusal does not repeat the secret into a log.
    assert "hunter2" not in str(caught.value)


def test_the_same_source_by_environment_reference_is_accepted() -> None:
    by_reference = {"engine": "postgres", "dsn": "host=db user=u", "password_env": "PG_PASSWORD"}
    config = parse_config(minimal(sources={"s": by_reference}))
    assert config.sources[0].password_env == "PG_PASSWORD"
    assert "hunter2" not in config.sources[0].describe()


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ConfigError) as caught:
        parse_config(
            {
                "server": {"url": "ftp://nowhere"},
                "sources": {"a": {"engine": "oracle"}, "b": {"engine": "sqlite"}},
                "residency": {"samples": "shout"},
                "spool": {"capacity": 0},
                "surprise": 1,
            }
        )
    message = caught.value.message
    for expected in ("not an http(s) URL", "state_dir is required", "oracle",
                     "path is required", "residency.samples", "spool.capacity",
                     "unknown top-level"):  # fmt: skip
        assert expected in message, expected


def test_plain_http_to_another_machine_needs_saying_so() -> None:
    with pytest.raises(ConfigError, match="plain HTTP"):
        parse_config(minimal(server={"url": "http://prama.example.com"}))
    assert parse_config(minimal(server={"url": "http://127.0.0.1:5900"})).server.url
    insecure = parse_config(minimal(server={"url": "http://prama.lan", "insecure": True}))
    assert insecure.server.insecure
    with pytest.raises(ConfigError, match="plain HTTP"):
        server_settings("http://prama.example.com")


def test_a_mask_policy_with_nothing_permitted_is_refused_by_the_kernel() -> None:
    with pytest.raises(ConfigError, match="permits no column"):
        parse_config(minimal(residency={"samples": "mask"}))


def test_residency_is_required() -> None:
    raw = minimal()
    del raw["residency"]
    with pytest.raises(ConfigError, match="residency is required"):
        parse_config(raw)


def test_environment_variables_expand_in_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRAMA_TEST_DATA", "/srv/data")
    config = parse_config(
        minimal(sources={"w": {"engine": "sqlite", "path": "$PRAMA_TEST_DATA/w.db"}})
    )
    assert config.sources[0].path == str(Path("/srv/data") / "w.db")


def test_an_unreadable_file_says_where(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="could not be read"):
        load_config(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("server: [unclosed\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(bad)
