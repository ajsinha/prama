"""``prama-agent enrol / run / status``, and the identity kept in the state directory.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
import yaml
from prama_agent.cli import main
from prama_agent.link import LinkUnavailable
from prama_agent.state import IDENTITY, load_identity, save_identity
from prama_kernel.agent.protocol import Refusal
from prama_kernel.errors import ConfigError, ValidationError
from tests.agent_daemon.conftest import IDENTITY as AN_IDENTITY
from tests.agent_daemon.conftest import FakeServer, amount_present


@pytest.fixture
def agent_yaml(tmp_path: Path, source: Path) -> Path:
    path = tmp_path / "agent.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "server": {"url": "https://prama.example.com"},
                "state_dir": "state",
                "sources": {"trades": {"engine": "sqlite", "path": "w.db"}},
                "residency": {"samples": "withhold"},
                "logging": {"format": "text"},
            }
        )
    )
    return path


def test_enrol_keeps_the_identity_readable_by_the_owner_only(
    tmp_path: Path, agent_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server = FakeServer()
    state = tmp_path / "state"
    argv = ["enrol", "--server", "https://prama.example.com", "--token", "tok-1",
            "--name", "eu-01", "--state", str(state), "--config", str(agent_yaml)]  # fmt: skip
    assert main(argv, link_factory=lambda _s: server) == 0
    assert "agt-01" in capsys.readouterr().out

    identity = load_identity(state)
    assert identity.zone == "eu-frankfurt" and identity.key.hex() == "11" * 32
    assert stat.S_IMODE((state / IDENTITY).stat().st_mode) == 0o600
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert server.enrolled["capabilities"]["engines"] == ["sqlite"]
    assert server.closed

    # Enrolling again would orphan the first identity silently; it must be asked for.
    assert main(argv, link_factory=lambda _s: server) == 1
    assert "already holds" in capsys.readouterr().err
    assert main([*argv, "--force"], link_factory=lambda _s: server) == 0


def test_enrol_refuses_plain_http_to_another_machine(tmp_path: Path) -> None:
    argv = ["enrol", "--server", "http://prama.example.com", "--token", "t",
            "--name", "n", "--state", str(tmp_path)]  # fmt: skip
    assert main(argv, link_factory=lambda _s: FakeServer()) == 1
    assert not (tmp_path / IDENTITY).exists()


def test_run_once_then_status(
    tmp_path: Path, agent_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_identity(tmp_path / "state", AN_IDENTITY)
    server = FakeServer([amount_present()])
    assert main(["run", "--config", str(agent_yaml), "--once"], link_factory=lambda _s: server) == 0
    assert len(server.records) == 1 and server.closed

    capsys.readouterr()
    assert main(["status", "--config", str(agent_yaml), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["identity"]["agent_id"] == "agt-01" and "key" not in status["identity"]
    assert status["spool"]["pending"] == 0 and status["gaps"] == []
    assert status["contact"]["last_contact_at"]
    assert "11" * 32 not in json.dumps(status)  # the key never appears in status

    assert main(["status", "--config", str(agent_yaml)]) == 0
    assert "eu-frankfurt" in capsys.readouterr().out


def test_status_shows_what_is_waiting_when_the_server_is_away(
    tmp_path: Path, agent_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_identity(tmp_path / "state", AN_IDENTITY)
    server = FakeServer([amount_present()])

    def unreachable(report: dict, *, key: bytes) -> dict:
        raise LinkUnavailable("connection refused", remedy="wait")

    server.report = unreachable  # type: ignore[method-assign]
    main(["run", "--config", str(agent_yaml), "--once"], link_factory=lambda _s: server)
    capsys.readouterr()
    main(["status", "--config", str(agent_yaml), "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status["spool"]["pending"] == 1
    assert status["contact"]["consecutive_failures"] == 1
    assert "connection refused" in status["contact"]["last_error"]


def test_a_refused_agent_exits_3_and_status_says_so(
    tmp_path: Path, agent_yaml: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    save_identity(tmp_path / "state", AN_IDENTITY)
    server = FakeServer()
    server.refusal = Refusal("revoked by a.roy", permanent=True)
    assert main(["run", "--config", str(agent_yaml)], link_factory=lambda _s: server) == 3
    assert main(["status", "--config", str(agent_yaml)]) == 3
    assert "REFUSED" in capsys.readouterr().out


def test_run_without_an_identity_says_how_to_enrol(agent_yaml: Path) -> None:
    assert main(["run", "--config", str(agent_yaml)], link_factory=lambda _s: FakeServer()) == 1


def test_state_files_refuse_to_be_silently_replaced_or_misread(tmp_path: Path) -> None:
    save_identity(tmp_path, AN_IDENTITY)
    with pytest.raises(ValidationError, match="already holds"):
        save_identity(tmp_path, AN_IDENTITY)
    (tmp_path / IDENTITY).write_text("{not json")
    with pytest.raises(ConfigError, match="could not be read"):
        load_identity(tmp_path)
    with pytest.raises(ConfigError, match="not enrolled"):
        load_identity(tmp_path / "elsewhere")
