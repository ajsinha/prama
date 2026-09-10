"""``prama contract`` — the commands a build system runs.

The value of a contract is that breaking it is noticed *before it ships*, so
these are built for CI and the exit code is the interface. Most of these tests
are about the exit codes being distinguishable: a build wants to tell "your
change broke the contract" apart from "the checker fell over", and one non-zero
code makes a broken checker look like a broken change.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from prama.cli.base import EXIT_DRIFT, EXIT_ERROR, EXIT_OK, Application
from prama.cli.commands import all_commands
from prama.core import pjson

CONTRACT = {
    "apiVersion": "3.0.0",
    "kind": "DataContract",
    "dataProduct": "positions",
    "criticality": "critical",
    "description": {"purpose": "EOD positions", "usage": "Risk"},
    "schema": [
        {
            "name": "positions_eod",
            "properties": [
                {"name": "account_id", "logicalType": "string", "required": True},
                {"name": "notional", "logicalType": "number", "required": True},
            ],
        }
    ],
}


def run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    return Application(all_commands()).run(argv, out=out), out.getvalue()


@pytest.fixture
def files(tmp_path: Path) -> Path:
    (tmp_path / "contract.json").write_text(json.dumps(CONTRACT))
    (tmp_path / "good.json").write_text(
        json.dumps([{"account_id": "A1", "notional": 10}, {"account_id": "A2", "notional": 20}])
    )
    (tmp_path / "missing.json").write_text(json.dumps([{"account_id": "A1"}, {"account_id": "A2"}]))
    (tmp_path / "nulls.json").write_text(
        json.dumps([{"account_id": "A1", "notional": 10}, {"account_id": None, "notional": 20}])
    )
    (tmp_path / "extra.json").write_text(
        json.dumps([{"account_id": "A1", "notional": 10, "new_column": "x"}])
    )
    (tmp_path / "empty.json").write_text("[]")
    return tmp_path


class TestTheExitCodesAreDistinguishable:
    def test_a_holding_contract_exits_zero(self, files: Path) -> None:
        code, text = run(
            ["contract", "check", str(files / "contract.json"), "--data", str(files / "good.json")]
        )
        assert code == EXIT_OK
        assert "The contract holds" in text

    def test_a_breach_exits_three_not_one(self, files: Path) -> None:
        """Three, so a build can tell "your change broke the contract" from
        "the checker fell over"."""
        code, text = run(
            [
                "contract",
                "check",
                str(files / "contract.json"),
                "--data",
                str(files / "missing.json"),
            ]
        )
        assert code == EXIT_DRIFT
        assert "BREACH" in text

    def test_a_broken_checker_exits_one(self, files: Path) -> None:
        code, _ = run(
            [
                "contract",
                "check",
                str(files / "contract.json"),
                "--data",
                str(files / "absent.json"),
            ]
        )
        assert code == EXIT_ERROR


class TestWhatCountsAsABreach:
    def test_a_missing_promised_column(self, files: Path) -> None:
        _, text = run(
            [
                "contract",
                "check",
                str(files / "contract.json"),
                "--data",
                str(files / "missing.json"),
            ]
        )
        assert "promised column(s) absent: notional" in text

    def test_a_required_column_holding_nulls(self, files: Path) -> None:
        """`required` is a promise about values, not only about the column
        existing. Checking the header alone passes a table of nulls."""
        code, text = run(
            ["contract", "check", str(files / "contract.json"), "--data", str(files / "nulls.json")]
        )
        assert code == EXIT_DRIFT
        assert "promised as required hold empty values: account_id" in text

    def test_an_added_column_can_be_allowed(self, files: Path) -> None:
        """A removed column breaks every consumer; an added one breaks none.
        Blocking both is how a gate gets switched off."""
        blocked, _ = run(
            ["contract", "check", str(files / "contract.json"), "--data", str(files / "extra.json")]
        )
        allowed, text = run(
            [
                "contract",
                "check",
                str(files / "contract.json"),
                "--data",
                str(files / "extra.json"),
                "--allow-additions",
            ]
        )
        assert blocked == EXIT_DRIFT
        assert allowed == EXIT_OK
        assert "note — column(s) not in the contract: new_column" in text

    def test_no_rows_is_a_breach_rather_than_a_pass(self, files: Path) -> None:
        """A contract check over no rows passes every test it can run and has
        established nothing."""
        code, text = run(
            ["contract", "check", str(files / "contract.json"), "--data", str(files / "empty.json")]
        )
        assert code == EXIT_DRIFT
        assert "no rows, so nothing was checked" in text

    def test_json_output_carries_the_verdict(self, files: Path) -> None:
        code, text = run(
            [
                "--json",
                "contract",
                "check",
                str(files / "contract.json"),
                "--data",
                str(files / "missing.json"),
            ]
        )
        payload = pjson.loads(text)
        assert code == EXIT_DRIFT
        assert payload["breached"] is True
        assert payload["missing_columns"] == ["notional"]


class TestDiff:
    def test_identical_data_exits_zero(self, files: Path) -> None:
        code, text = run(
            [
                "contract",
                "diff",
                str(files / "good.json"),
                str(files / "good.json"),
                "--key",
                "account_id",
            ]
        )
        assert code == EXIT_OK
        assert "identical" in text

    def test_a_difference_exits_three(self, files: Path) -> None:
        code, _ = run(
            [
                "contract",
                "diff",
                str(files / "good.json"),
                str(files / "nulls.json"),
                "--key",
                "account_id",
            ]
        )
        assert code == EXIT_DRIFT

    def test_without_a_key_it_says_rows_cannot_be_matched(self, files: Path) -> None:
        _, text = run(["contract", "diff", str(files / "good.json"), str(files / "missing.json")])
        assert "rows cannot be matched" in text

    def test_a_column_can_be_ignored(self, files: Path) -> None:
        code, _ = run(
            [
                "contract",
                "diff",
                str(files / "good.json"),
                str(files / "extra.json"),
                "--key",
                "account_id",
                "--ignore",
                "new_column",
            ]
        )
        # Still differs: extra.json has one row, good.json has two.
        assert code == EXIT_DRIFT

    def test_csv_is_read(self, files: Path) -> None:
        (files / "a.csv").write_text("account_id,notional\nA1,10\n")
        (files / "b.csv").write_text("account_id,notional\nA1,11\n")
        code, text = run(
            ["contract", "diff", str(files / "a.csv"), str(files / "b.csv"), "--key", "account_id"]
        )
        assert code == EXIT_DRIFT
        assert "notional" in text


class TestImport:
    def test_it_lists_what_did_not_come_across(self, files: Path) -> None:
        """A count tells a reader something was lost and not what, which is the
        half that decides whether it matters."""
        code, text = run(["contract", "import", str(files / "contract.json")])
        assert code == EXIT_OK
        assert "default: grain" in text
        assert "default: rhythm" in text

    def test_a_contract_with_no_schema_exits_non_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"apiVersion": "3.0.0", "kind": "DataContract"}))
        code, text = run(["contract", "import", str(path)])
        assert code == EXIT_DRIFT
        assert "no schema" in text

    def test_json_output_is_machine_readable(self, files: Path) -> None:
        code, text = run(["--json", "contract", "import", str(files / "contract.json")])
        payload = pjson.loads(text)
        assert code == EXIT_OK
        assert payload["attributes"] == 2
        assert payload["defaulted"]

    def test_a_missing_file_is_refused_with_a_path(self, tmp_path: Path) -> None:
        code, _ = run(["contract", "import", str(tmp_path / "nope.json")])
        assert code == EXIT_ERROR

    def test_unreadable_json_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json")
        code, _ = run(["contract", "import", str(path)])
        assert code == EXIT_ERROR
