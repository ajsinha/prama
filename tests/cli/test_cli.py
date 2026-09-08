"""The command line.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from prama.cli.base import EXIT_DRIFT, EXIT_ERROR, EXIT_OK, EXIT_USAGE, Application
from prama.cli.commands import all_commands
from prama.core import pjson


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = Application(all_commands()).run(argv, out=out)
    return code, out.getvalue()


@pytest.fixture
def cli_config(tmp_path: Path, repo_root: Path) -> Path:
    path = tmp_path / "application.yaml"
    path.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {tmp_path / 'cli.db'}\n"
        f"  schema_dir: {repo_root / 'schema'}\n"
    )
    return path


class TestVersion:
    def test_human_output_carries_the_tagline(self) -> None:
        code, text = run(["version"])
        assert code == EXIT_OK
        assert "Declare it. Prove it. Trust it." in text

    def test_json_output_is_machine_readable(self) -> None:
        code, text = run(["--json", "version"])
        assert code == EXIT_OK
        assert set(pjson.loads(text)) == {"product", "version", "ir_version", "schema_version"}


class TestConfigShow:
    def test_secrets_are_redacted_by_default(self, tmp_path: Path) -> None:
        path = tmp_path / "application.yaml"
        path.write_text("security:\n  session_secret: hunter2\n")
        code, text = run(["--config", str(path), "config", "show"])
        assert code == EXIT_OK
        assert "hunter2" not in text
        assert "***" in text

    def test_raw_is_refused_without_the_explicit_environment_opt_in(self, tmp_path: Path) -> None:
        path = tmp_path / "application.yaml"
        path.write_text("security:\n  session_secret: hunter2\n")
        code, text = run(["--config", str(path), "config", "show", "--raw"])
        assert "hunter2" not in text

    def test_provenance_names_the_source(self, cli_config: Path) -> None:
        code, text = run(["--config", str(cli_config), "config", "show", "--provenance"])
        assert code == EXIT_OK
        assert str(cli_config) in text

    def test_set_override_reaches_the_configuration(self, cli_config: Path) -> None:
        code, text = run(
            ["--config", str(cli_config), "--set", "logging.level=DEBUG", "config", "show"]
        )
        assert "'DEBUG'" in text


class TestDb:
    def test_init_then_verify_is_clean(self, cli_config: Path) -> None:
        assert run(["--config", str(cli_config), "db", "init"])[0] == EXIT_OK
        code, text = run(["--config", str(cli_config), "db", "verify"])
        assert code == EXIT_OK
        assert "no drift" in text

    def test_init_is_idempotent(self, cli_config: Path) -> None:
        run(["--config", str(cli_config), "db", "init"])
        code, text = run(["--config", str(cli_config), "db", "init"])
        assert code == EXIT_OK
        assert "already current" in text

    def test_verify_exits_non_zero_on_blocking_drift(self, cli_config: Path) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sql

        run(["--config", str(cli_config), "db", "init"])
        db_path = next(
            line.split(":", 1)[1].strip()
            for line in cli_config.read_text().splitlines()
            if line.strip().startswith("path:")
        )
        engine = create_engine(f"sqlite+pysqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(sql("DROP TABLE tenant"))
        engine.dispose()
        code, text = run(["--config", str(cli_config), "db", "verify"])
        assert code == EXIT_DRIFT
        assert "missing_table" in text

    def test_info_reports_the_configured_engine_and_tables(self, cli_config: Path) -> None:
        run(["--config", str(cli_config), "db", "init"])
        code, text = run(["--config", str(cli_config), "db", "info"])
        assert code == EXIT_OK
        assert "sqlite" in text
        assert "audit_event" in text

    def test_a_password_is_never_printed_in_the_url(self, tmp_path: Path, repo_root: Path) -> None:
        path = tmp_path / "application.yaml"
        path.write_text(
            "database:\n  dialect: postgres\n"
            "  postgres:\n    host: db\n    password: hunter2\n"
            f"  schema_dir: {repo_root / 'schema'}\n"
        )
        code, text = run(["--config", str(path), "db", "info"])
        assert "hunter2" not in text


class TestErrorHandling:
    def test_no_command_prints_help_and_exits_with_usage(self) -> None:
        assert run([])[0] == EXIT_USAGE

    def test_a_group_without_a_subcommand_shows_its_options(self) -> None:
        code, text = run(["db"])
        assert code == EXIT_USAGE
        assert "init" in text and "verify" in text

    def test_a_prama_error_becomes_a_clean_exit_code(self, tmp_path: Path) -> None:
        code, _ = run(["--config", str(tmp_path / "absent.yaml"), "config", "show"])
        assert code == EXIT_ERROR
