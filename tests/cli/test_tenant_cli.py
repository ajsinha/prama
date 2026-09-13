"""``prama tenant`` — the command that made a fresh installation reachable.

Every other command took ``--tenant`` and none of them could create one, so the
console's ``tenancy.default_tenant`` wanted an identifier that nothing produced.
These tests are mostly about the two things that made the gap expensive: that a
mistake is refused rather than absorbed, and that the output says what to do
next rather than printing an identifier and stopping.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from prama.cli.base import EXIT_ERROR, EXIT_OK, Application
from prama.cli.commands import all_commands
from prama.cli.principal import _resolve_tenant
from prama.core import pjson
from prama.core.errors import ValidationError
from prama.db import Database


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = Application(all_commands()).run(argv, out=out)
    return code, out.getvalue()


@pytest.fixture
def config(tmp_path: Path, repo_root: Path) -> Path:
    path = tmp_path / "application.yaml"
    path.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {tmp_path / 'tenant.db'}\n"
        f"  schema_dir: {repo_root / 'schema'}\n"
    )
    run(["--config", str(path), "db", "init"])
    return path


class TestCreate:
    def test_it_prints_an_identifier(self, config: Path) -> None:
        code, text = run(["--config", str(config), "tenant", "create", "acme-bank"])
        assert code == EXIT_OK
        assert "created acme-bank (acme-bank)" in text

    def test_it_says_what_to_do_with_the_identifier(self, config: Path) -> None:
        """An id printed without saying what it is for is a step somebody has to
        guess, and the guess is usually "paste it into the tracked config
        file"."""
        code, text = run(
            ["--config", str(config), "tenant", "create", "acme-bank", "--name", "Acme"]
        )
        assert "tenancy:" in text
        assert "default_tenant:" in text
        assert "application.local.yaml" in text
        assert "git-ignored" in text

    def test_the_display_name_defaults_to_the_slug(self, config: Path) -> None:
        _, text = run(["--config", str(config), "tenant", "create", "acme-bank"])
        assert "created acme-bank (acme-bank)" in text

    def test_json_output_carries_the_id(self, config: Path) -> None:
        code, text = run(["--config", str(config), "--json", "tenant", "create", "acme-bank"])
        assert code == EXIT_OK
        payload = pjson.loads(text)
        assert payload["slug"] == "acme-bank"
        assert len(payload["id"]) == 26

    def test_a_second_create_is_refused_and_names_the_existing_id(
        self, config: Path, capsys
    ) -> None:
        """Refused rather than reused. "Make one" and "you already have one"
        meaning the same thing would make a typo in the slug indistinguishable
        from a second estate."""
        _, first = run(["--config", str(config), "tenant", "create", "acme-bank"])
        identifier = first.split("id:")[1].split()[0]
        capsys.readouterr()

        code, _ = run(["--config", str(config), "tenant", "create", "acme-bank"])
        assert code == EXIT_ERROR
        errors = capsys.readouterr().err
        assert "already a tenant" in errors
        assert identifier in errors

    def test_case_is_normalised_rather_than_refused(self, config: Path) -> None:
        """Forgiving where forgiveness is unambiguous. ``ACME`` can only have
        meant ``acme``; a space could have meant several things, so that is
        refused below."""
        code, text = run(["--config", str(config), "tenant", "create", "ACME"])
        assert code == EXIT_OK
        assert "(acme)" in text

    # A leading hyphen is absent from this list on purpose: argparse claims it
    # as a flag before the validator is reached, so it is refused a layer
    # earlier and with a different message. Asserting the validator's wording
    # against the parser's refusal would be testing argparse.
    @pytest.mark.parametrize("slug", ["Acme Bank", "acme_bank", "", "a" * 64])
    def test_an_unusable_slug_is_refused(self, config: Path, slug: str, capsys) -> None:
        """It appears in URLs and in configuration, so it has to survive both."""
        code, _ = run(["--config", str(config), "tenant", "create", slug])
        assert code != EXIT_OK
        assert "slug" in capsys.readouterr().err.lower()


class TestList:
    def test_an_empty_estate_says_what_to_do(self, config: Path) -> None:
        """Not a blank list. A fresh installation with no tenant is the state
        somebody most needs a next step from."""
        code, text = run(["--config", str(config), "tenant", "list"])
        assert code == EXIT_OK
        assert "No tenants" in text
        assert "prama tenant create" in text
        assert "sign-in that does not exist" in text

    def test_it_marks_the_configured_tenant(self, config: Path) -> None:
        """A list of identifiers with no indication of which one is configured
        is a list somebody reads and then still has to check the
        configuration."""
        _, created = run(["--config", str(config), "tenant", "create", "acme-bank"])
        identifier = created.split("id:")[1].split()[0]

        code, text = run(
            [
                "--config",
                str(config),
                "--set",
                f"tenancy.default_tenant={identifier}",
                "tenant",
                "list",
            ]
        )
        assert code == EXIT_OK
        assert f"* {identifier}" in text
        assert "the estate the console reads" in text

    def test_it_says_when_nothing_is_configured(self, config: Path) -> None:
        run(["--config", str(config), "tenant", "create", "acme-bank"])
        _, text = run(["--config", str(config), "tenant", "list"])
        assert "tenancy.default_tenant is not set" in text

    def test_json_output_reports_the_configured_tenant(self, config: Path) -> None:
        run(["--config", str(config), "tenant", "create", "acme-bank"])
        code, text = run(["--config", str(config), "--json", "tenant", "list"])
        assert code == EXIT_OK
        payload = pjson.loads(text)
        assert payload["tenants"][0]["slug"] == "acme-bank"
        assert payload["default_tenant"] == ""


class TestItIsNotFoldedIntoDbInit:
    def test_db_init_creates_no_tenant(self, config: Path) -> None:
        """Applying a schema is idempotent and says nothing about who the
        system is for. Folding the estate into it would mean every db init on a
        shared database silently added a tenant nobody asked for."""
        run(["--config", str(config), "db", "init"])
        run(["--config", str(config), "db", "init"])
        _, text = run(["--config", str(config), "tenant", "list"])
        assert "No tenants" in text


class TestTheNextStepIsSpelledOut:
    """An identifier printed without saying what to do with it is a step
    somebody has to guess, and the guess is usually "paste it into the tracked
    config file".
    """

    def test_it_points_at_the_git_ignored_file(self, config: Path) -> None:
        _, text = run(["--config", str(config), "tenant", "create", "acme-bank"])
        assert "config/application.local.yaml" in text
        assert "git-ignored" in text

    def test_it_names_creating_somebody_who_can_sign_in(self, config: Path) -> None:
        """The console *has* sign-in. This said it did not, which sent a reader
        looking for a feature that is there."""
        _, text = run(["--config", str(config), "tenant", "create", "acme-bank"])
        assert "prama principal create" in text
        assert "has no sign-in yet" not in text


class TestTheFirstTwoCommandsAgree:
    """`prama tenant create` prints, as its next step:

        prama principal create <username> --admin --tenant acme-bank

    and until this was pinned, that command failed with a raw
    `FOREIGN KEY constraint failed`. `--tenant` took an id; the message told
    the operator to pass a slug. The first two commands anybody runs, and the
    first one told them to type something the second refused.

    Found by standing the product up, not by the suite — the same way the
    sign-in redirect loop was. Both are the shape a suite is worst at: two
    components that are each correct and disagree at the seam.
    """

    async def _tenant(self, database: Database, slug: str = "acme-bank") -> str:
        async with database.unit_of_work() as uow:
            tenant = uow.tenants.create(slug=slug, display_name="Acme")
            await uow.flush()
            return str(tenant.id)

    async def test_a_slug_is_accepted(self, started_database: Database) -> None:
        expected = await self._tenant(started_database)
        async with started_database.unit_of_work() as uow:
            assert await _resolve_tenant(uow, "acme-bank") == expected

    async def test_an_id_is_still_accepted(self, started_database: Database) -> None:
        """Scripts pass ids and people pass slugs; both have to work."""
        identifier = await self._tenant(started_database)
        async with started_database.unit_of_work() as uow:
            assert await _resolve_tenant(uow, identifier) == identifier

    async def test_an_unknown_estate_is_named_not_a_constraint(
        self, started_database: Database
    ) -> None:
        """An integrity error names a constraint. A person needs the mistake."""
        await self._tenant(started_database)
        async with started_database.unit_of_work() as uow:
            with pytest.raises(ValidationError, match="no estate called"):
                await _resolve_tenant(uow, "nosuchbank")

    async def test_the_refusal_lists_the_estates_that_do_exist(
        self, started_database: Database
    ) -> None:
        await self._tenant(started_database)
        async with started_database.unit_of_work() as uow:
            with pytest.raises(ValidationError) as caught:
                await _resolve_tenant(uow, "nope")
        assert "acme-bank" in str(caught.value)


class TestAPipedPasswordIsTheOneThatWasPiped:
    """QA found `principal create` storing a password nobody typed.

    `_read_password` did `sys.stdin.read().strip()` — the *whole* stream as one
    value. Piping the password twice, which is the natural thing to do because
    the interactive path asks twice, stored a password containing a newline.
    The account was created, the command printed `created alice`, and nobody
    could ever sign in to it.

    Silent in both directions, which is what made it expensive: the CLI said
    "created" and the console said "invalid credentials", and neither of them
    was lying about what it saw.
    """

    def read(self, piped: str) -> str:
        import io
        import sys
        from unittest.mock import patch

        from prama.cli.principal import _read_password

        with patch.object(sys, "stdin", io.StringIO(piped)):
            return _read_password()

    def test_one_line(self) -> None:
        assert self.read("hunter2-and-long-enough\n") == "hunter2-and-long-enough"

    def test_one_line_without_a_newline(self) -> None:
        """`printf '%s'`, which is the form the error message recommends."""
        assert self.read("hunter2-and-long-enough") == "hunter2-and-long-enough"

    def test_the_same_password_twice_is_a_confirmation(self) -> None:
        """The natural thing to pipe, and what used to produce a password with
        a newline in the middle of it."""
        assert self.read("hunter2-and-long-enough\nhunter2-and-long-enough\n") == (
            "hunter2-and-long-enough"
        )

    def test_two_different_lines_are_refused(self) -> None:
        """If it looks like a confirmation, it has to behave like one."""
        with pytest.raises(ValidationError, match="did not match"):
            self.read("one-password-here\nanother-one-here\n")

    def test_a_file_piped_by_mistake_is_refused(self) -> None:
        """Rather than setting a password nobody can type."""
        with pytest.raises(ValidationError, match="a password is one"):
            self.read("line one\nline two\nline three\n")

    def test_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no password on stdin"):
            self.read("   \n\n")
