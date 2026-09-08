"""The control commands.

What a person does with the language from a terminal: check it, read it,
see the SQL it becomes, and bring an existing estate across.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from prama.cli.base import EXIT_ERROR, EXIT_OK, EXIT_USAGE, Application
from prama.cli.commands import all_commands

SUITE = """
SUITE positions_eod_core {
  CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id)
    SEVERITY critical DIMENSION uniqueness BECAUSE 'Declared grain'

  CHECK positions_eod.notional_amount IS NOT NULL
    SEVERITY critical DIMENSION completeness BECAUSE 'CDE for FRTB'

  CHECK positions_eod.isin MATCHES /^[A-Z]{2}[0-9A-Z]{9}[0-9]$/
    SEVERITY major DIMENSION validity BECAUSE 'ISO 6166'
}
"""

ROTTED = """
CHECK t.a IS NOT NULL BELOW 100% BECAUSE 'nice to have'
"""

DBT = """
version: 2
models:
  - name: positions_eod
    columns:
      - name: account_id
        tests: [unique, not_null]
      - name: qty
        tests: [my_company.check_frtb]
"""


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = Application(all_commands()).run(argv, out=out)
    return code, out.getvalue()


@pytest.fixture
def suite(tmp_path: Path) -> Path:
    path = tmp_path / "suite.pql"
    path.write_text(SUITE, encoding="utf-8")
    return path


class TestCheck:
    def test_a_sound_suite_passes(self, suite: Path) -> None:
        code, output = run(["control", "check", str(suite)])
        assert code == EXIT_OK
        assert "3 control(s) read" in output

    def test_a_control_that_can_never_fire_fails_the_check(self, tmp_path: Path) -> None:
        # So it can go straight into CI without anything else being written.
        path = tmp_path / "rotted.pql"
        path.write_text(ROTTED, encoding="utf-8")
        code, output = run(["control", "check", str(path)])
        assert code == EXIT_ERROR
        assert "can never fail" in output

    def test_strict_promotes_warnings(self, tmp_path: Path) -> None:
        path = tmp_path / "redundant.pql"
        path.write_text(
            "CHECK t.a BETWEEN 0 AND 1 BECAUSE 'range'\nCHECK t.a IS NOT NULL BECAUSE 'null'\n",
            encoding="utf-8",
        )
        assert run(["control", "check", str(path)])[0] == EXIT_OK
        assert run(["control", "check", str(path), "--strict"])[0] == EXIT_ERROR

    def test_an_undeclared_dataset_is_reported_once(self, suite: Path) -> None:
        # Not once per control. A fifty-control suite would otherwise bury its
        # real findings under fifty identical paragraphs.
        _, output = run(["control", "check", str(suite)])
        assert output.count("nothing is known about positions_eod") == 1

    def test_a_syntax_error_is_shown_with_its_caret(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.pql"
        path.write_text("CHECK t.a IS NOT NULL SEVERITY urgent\n", encoding="utf-8")
        code, output = run(["control", "check", str(path)])
        assert code == EXIT_ERROR
        assert "^" in output
        assert "critical" in output  # the remedy lists the real severities

    def test_a_missing_file_is_a_usage_error(self, tmp_path: Path) -> None:
        code, output = run(["control", "check", str(tmp_path / "absent.pql")])
        assert code == EXIT_USAGE
        assert "no such file" in output

    def test_json_output_carries_the_findings(self, suite: Path) -> None:
        _, output = run(["--json", "control", "check", str(suite)])
        payload = json.loads(output)
        assert payload["controls"] == 3
        assert isinstance(payload["findings"], list)


class TestExplain:
    def test_it_renders_a_sentence_per_control(self, suite: Path) -> None:
        code, output = run(["control", "explain", str(suite)])
        assert code == EXIT_OK
        assert output.count("· In positions_eod") == 3
        assert "This exists because: Declared grain." in output

    def test_the_sentences_read_as_english(self, suite: Path) -> None:
        _, output = run(["control", "explain", str(suite)])
        assert "looks like" in output
        assert "does look like" not in output


class TestFormat:
    def test_it_prints_canonical_form(self, suite: Path) -> None:
        code, output = run(["control", "format", str(suite)])
        assert code == EXIT_OK
        assert output.startswith("CHECK positions_eod HAS UNIQUE KEY")

    def test_writing_is_idempotent(self, suite: Path) -> None:
        # A formatter whose second run differs from its first makes every diff
        # a fight.
        run(["control", "format", str(suite), "--write"])
        first = suite.read_text(encoding="utf-8")
        run(["control", "format", str(suite), "--write"])
        assert suite.read_text(encoding="utf-8") == first

    def test_the_formatted_file_still_reads(self, suite: Path) -> None:
        run(["control", "format", str(suite), "--write"])
        assert run(["control", "check", str(suite)])[0] == EXIT_OK


class TestCompile:
    def test_it_shows_the_sql(self, suite: Path) -> None:
        code, output = run(["control", "compile", str(suite), "--dialect", "postgresql"])
        assert code == EXIT_OK
        assert "SELECT COUNT(*)" in output
        assert 'FROM "positions_eod"' in output

    def test_a_refusal_is_reported_rather_than_raised(self, suite: Path) -> None:
        # The engine saying which control it cannot run, before anything is
        # scheduled against it.
        code, output = run(["control", "compile", str(suite), "--dialect", "sqlite"])
        assert code == EXIT_OK
        assert "refused" in output
        assert "pushdown.regex" in output
        assert "1 control(s) cannot run on sqlite" in output

    def test_fusing_shows_one_query_and_the_saving(self, suite: Path) -> None:
        code, output = run(["control", "compile", str(suite), "--dialect", "duckdb", "--fuse"])
        assert code == EXIT_OK
        assert "3 control(s) in 1 scan(s)" in output
        assert output.count("SELECT") == 1

    def test_each_query_is_labelled_with_what_it_checks(self, suite: Path) -> None:
        _, output = run(["control", "compile", str(suite), "--dialect", "duckdb"])
        assert "-- In positions_eod" in output


class TestImport:
    def test_it_reports_what_did_not_come_across(self, tmp_path: Path) -> None:
        path = tmp_path / "schema.yml"
        path.write_text(DBT, encoding="utf-8")
        code, output = run(["control", "import", str(path), "--from", "dbt"])
        # Non-zero, so a migration script cannot report success while quietly
        # losing coverage.
        assert code == EXIT_ERROR
        assert "1 did not come across" in output
        assert "check_frtb" in output

    def test_a_complete_import_succeeds(self, tmp_path: Path) -> None:
        path = tmp_path / "schema.yml"
        path.write_text(
            "version: 2\nmodels:\n  - name: t\n    columns:\n"
            "      - name: k\n        tests: [not_null]\n",
            encoding="utf-8",
        )
        code, output = run(["control", "import", str(path), "--from", "dbt"])
        assert code == EXIT_OK
        assert "Nothing was left behind" in output

    def test_it_can_write_the_controls_out(self, tmp_path: Path) -> None:
        source = tmp_path / "schema.yml"
        source.write_text(DBT, encoding="utf-8")
        target = tmp_path / "imported.pql"
        run(["control", "import", str(source), "--from", "dbt", "--out", str(target)])
        assert target.is_file()
        # And what it wrote is a control file the rest of the tools accept.
        assert run(["control", "check", str(target)])[0] == EXIT_OK

    def test_an_unknown_source_is_rejected_by_the_parser(self, tmp_path: Path) -> None:
        path = tmp_path / "x.yml"
        path.write_text("a: 1", encoding="utf-8")
        with pytest.raises(SystemExit):
            run(["control", "import", str(path), "--from", "monte_carlo"])

    def test_json_output_is_a_migration_record(self, tmp_path: Path) -> None:
        path = tmp_path / "schema.yml"
        path.write_text(DBT, encoding="utf-8")
        _, output = run(["--json", "control", "import", str(path), "--from", "dbt"])
        payload = json.loads(output)
        assert payload["source_format"] == "dbt"
        assert payload["unmapped"]
