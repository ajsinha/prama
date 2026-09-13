"""`prama apikey` — the credential the HTTP API requires.

Written because the API's own refusal named this command and it did not exist.
A caller with no credential was told *"Create one with `prama apikey create`"*
and there was no `apikey` group at all, so on a clean install the HTTP API
could not be authenticated to by any supported means. Found from both ends by a
QA pass: the API agent following the remedy, and the operator agent looking for
a way in.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from prama.cli.base import EXIT_OK, Application
from prama.cli.commands import all_commands


def invoke(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = Application(all_commands()).run(argv, out=out)
    return code, out.getvalue()


def failing(argv: list[str], capsys: Any) -> tuple[int, str]:
    """Run something expected to fail, and return what the operator sees.

    Refusals go to stderr, which is right — a script piping stdout to `jq`
    must not be handed prose — so a test reading only stdout sees an empty
    string and proves nothing.
    """
    capsys.readouterr()
    code, _ = invoke(argv)
    captured = capsys.readouterr()
    return code, captured.err + captured.out


@pytest.fixture
def estate(tmp_path: Path, repo_root: Path) -> Path:
    """A config with a database, an estate and somebody to attribute a key to."""
    path = tmp_path / "application.yaml"
    path.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {tmp_path / 'apikey.db'}\n"
        f"  schema_dir: {repo_root / 'schema'}\n"
    )
    invoke(["--config", str(path), "db", "init"])
    invoke(["--config", str(path), "tenant", "create", "acme-bank"])
    import sys
    from unittest.mock import patch

    with patch.object(sys, "stdin", io.StringIO("a-long-enough-password\n")):
        invoke(
            [
                "--config",
                str(path),
                "principal",
                "create",
                "alice",
                "--admin",
                "--tenant",
                "acme-bank",
            ]
        )
    return path


def run(config_path: str, *argv: str, json_output: bool = False) -> tuple[int, str]:
    arguments = ["--config", config_path]
    if json_output:
        arguments.append("--json")
    return invoke([*arguments, *argv])


class TestTheCommandTheApiTellsYouToRun:
    def test_it_exists(self) -> None:
        """The whole finding: it did not."""
        names = {c.name for c in all_commands()}
        assert "apikey" in names, sorted(names)

    def test_every_remedy_naming_a_command_names_one_that_exists(self) -> None:
        """The API's 401 says `prama apikey create`. Following a remedy has to
        reach a command that exists — this codebase has shipped three that did
        not: `prama apikey`, `prama validators scan`, and the `--tenant acme-bank`
        that `tenant create` prints.

        Reads `remedy=` literals by AST rather than grepping prose, because a
        docstring *explaining* that a command never existed names it too, and a
        scan that cannot tell those apart flags its own correction.
        """
        import re

        from tests.architecture.test_remedies import remedies

        groups = {c.name for c in all_commands()}
        missing = set()
        for module, line, text in remedies():
            for named in re.findall(r"`?\bprama (\w+)", text):
                if named not in groups:
                    missing.add(f"{named} ({module}:{line})")
        assert not missing, f"remedies name commands that do not exist: {sorted(missing)}"


class TestTheKeyLifecycle:
    def test_issue_then_list_then_revoke(self, estate: Path) -> None:
        code, out = run(
            str(estate),
            "apikey",
            "create",
            "ci",
            "--tenant",
            "acme-bank",
            "--principal",
            "alice",
            "--scope",
            "*",
            json_output=True,
        )
        assert code == EXIT_OK, out
        issued: dict[str, Any] = json.loads(out)
        assert issued["key"].startswith("pk_"), issued["key"][:8]
        assert issued["scopes"] == ["*"]

        code, out = run(str(estate), "apikey", "list", "--tenant", "acme-bank")
        assert code == EXIT_OK
        assert issued["prefix"] in out
        assert issued["key"] not in out, "the plaintext must never be readable again"

        code, out = run(str(estate), "apikey", "revoke", issued["prefix"], "--tenant", "acme-bank")
        assert code == EXIT_OK
        assert "revoked" in out

    def test_a_key_with_no_scopes_is_refused(self, estate: Path, capsys: Any) -> None:
        """An empty scope list permits nothing, so issuing one is issuing a
        credential that cannot work. Refused at the point of creation rather
        than discovered on the first 403."""
        code, out = failing(
            [
                "--config",
                str(estate),
                "apikey",
                "create",
                "ci",
                "--tenant",
                "acme-bank",
                "--principal",
                "alice",
            ],
            capsys,
        )
        assert code != EXIT_OK
        assert "no scopes" in out

    def test_an_invented_scope_is_refused(self, estate: Path, capsys: Any) -> None:
        """A scope nobody enforces can never be satisfied — the H5 failure, at
        the point where it is cheapest to catch."""
        code, out = failing(
            [
                "--config",
                str(estate),
                "apikey",
                "create",
                "ci",
                "--tenant",
                "acme-bank",
                "--principal",
                "alice",
                "--scope",
                "not:a:scope",
            ],
            capsys,
        )
        assert code != EXIT_OK
        assert "unknown scope" in out

    def test_an_unknown_principal_is_named(self, estate: Path, capsys: Any) -> None:
        """And not reported as a foreign-key violation, which is what the
        schema would have said."""
        code, out = failing(
            [
                "--config",
                str(estate),
                "apikey",
                "create",
                "ci",
                "--tenant",
                "acme-bank",
                "--principal",
                "nobody",
                "--scope",
                "*",
            ],
            capsys,
        )
        assert code != EXIT_OK
        assert "no principal called" in out
        assert "FOREIGN KEY" not in out
