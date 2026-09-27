"""Streaming rows to delegates in batches, and the conformance kit authors run in CI.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from prama.core.errors import ValidationError
from prama.delegates.host import host_from_config
from prama.delegates.testkit import Case, check_delegate, control_for
from prama.ir.resolve import resolved
from prama.pql import parse_control

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "delegates"
GOOD = FIXTURES / "good" / "threshold_count.py"
PLAN_SOURCE = "CHECK payments USING DELEGATE 'test.over_limit@2' (limit = 100)"


def _host(directory: Path, **options: Any) -> Any:
    host = host_from_config({"delegates": {"paths": [str(directory)], "entry_points": False}})
    for key, value in options.items():
        setattr(host, key, value)
    return host


class _Source:
    """Batches of rows, counting how many were pulled."""

    def __init__(self, batches: int, size: int) -> None:
        self.batches, self.size, self.pulled = batches, size, 0

    def __iter__(self) -> Iterator[list[dict[str, Any]]]:
        for b in range(self.batches):
            self.pulled += 1
            yield [
                {"id": b * self.size + i, "amount": (i % 200), "booked": "2026-09-01"}
                for i in range(self.size)
            ]


@pytest.mark.parametrize("sandbox", [False, True])
def test_a_large_input_streams_through_in_batches(sandbox: bool) -> None:
    host = _host(FIXTURES / "good", sandbox=sandbox)
    source = _Source(batches=40, size=5_000)  # 200,000 rows
    result = host.measure_stream(resolved(parse_control(PLAN_SOURCE)), source)
    assert result.metrics["scanned_rows"] == 200_000
    assert result.metrics["violating_rows"] == 200_000 * 99 // 200
    assert source.pulled == 40


@pytest.mark.parametrize("sandbox", [False, True])
def test_past_the_ceiling_the_stream_stops_and_the_run_is_refused(sandbox: bool) -> None:
    host = _host(FIXTURES / "good", sandbox=sandbox, max_rows=12_000)
    source = _Source(batches=1_000, size=5_000)
    with pytest.raises(ValidationError, match=r"exceed delegates\.max_rows"):
        host.measure_stream(resolved(parse_control(PLAN_SOURCE)), source)
    assert source.pulled <= 4  # stopped reading, rather than reading it all and refusing


def test_a_file_changed_after_admission_is_refused_in_the_sandbox(tmp_path: Path) -> None:
    shutil.copy(GOOD, tmp_path / GOOD.name)
    host = _host(tmp_path, sandbox=True)
    (tmp_path / GOOD.name).write_text(
        GOOD.read_text().replace('float(params["limit"])', "0.0"), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="changed since it was admitted"):
        host.measure_plan(resolved(parse_control(PLAN_SOURCE)), [{"id": 1, "amount": 5}])


def test_batches_come_from_the_cursor_not_one_fetch(tmp_path: Path) -> None:
    import duckdb

    from prama.connect.sources.query import executor_for
    from prama.delegates.host import batches_of

    database = tmp_path / "d.duckdb"
    connection = duckdb.connect(str(database))
    connection.execute("CREATE TABLE t AS SELECT range AS id FROM range(25)")
    connection.close()
    execute, close = executor_for(database, "duckdb")
    try:
        sizes = [len(b) for b in batches_of(execute, "SELECT id FROM t", 10)]
    finally:
        close()
    assert sizes == [10, 10, 5]


# -- the kit -------------------------------------------------------------------


def test_the_kit_passes_a_conforming_delegate_with_its_cases() -> None:
    report = check_delegate(
        GOOD,
        cases=[
            Case("one over", rows=[{"id": 1, "amount": 150}, {"id": 2, "amount": 5}], violating=1),
            Case(
                "raised limit", rows=[{"id": 1, "amount": 150}], params={"limit": 200}, violating=0
            ),
        ],
        large_rows=20_000,
    )
    assert report.ok, report.render()
    assert {c.name for c in report.checks} >= {
        "vetted before import",
        "admitted",
        "reads its rows in one pass",
        "streams 20,000 rows in batches",
        "case: one over",
    }


def test_the_kit_fails_a_wrong_expectation_and_names_it() -> None:
    report = check_delegate(
        GOOD, cases=[Case("wrong", rows=[{"id": 1, "amount": 150}], violating=0)], large_rows=100
    )
    assert not report.ok
    (miss,) = [c for c in report.checks if not c.passed]
    assert miss.name == "case: wrong" and "violating 1.0, expected 0" in miss.detail


def test_the_kit_fails_a_delegate_that_reads_its_rows_twice(tmp_path: Path) -> None:
    twice = tmp_path / "twice.py"
    twice.write_text(
        '"""Counts its rows twice."""\n'
        "from prama.delegates import DqDelegate, Measurement\n\n"
        "class Twice(DqDelegate):\n"
        "    name = 'test.twice'\n\n"
        "    def measure(self, rows, params):\n"
        "        first = sum(1 for _ in rows)\n"
        "        second = sum(1 for _ in rows)\n"
        "        return Measurement(scanned=first, violating=first - second)\n",
        encoding="utf-8",
    )
    report = check_delegate(twice, cases=[Case("two rows", rows=[{"value": 1}, {"value": 2}])])
    failed = {c.name for c in report.checks if not c.passed}
    assert "reads its rows in one pass" in failed


def test_the_kit_refuses_an_impure_file_without_importing_it() -> None:
    report = check_delegate(FIXTURES / "impure")  # it raises SystemExit if imported
    assert not report.ok
    assert report.checks[0].name == "vetted before import" and not report.checks[0].passed


def test_control_for_writes_pql_the_parser_reads_back() -> None:
    source = control_for("acme.x@1", {"market": "US", "days": 2, "strict": True, "rate": 0.5})
    plan = resolved(parse_control(source))
    assert plan.detail["parameters"] == {"market": "US", "days": 2, "strict": True, "rate": 0.5}


def test_the_cli_exits_non_zero_when_a_case_fails(tmp_path: Path) -> None:
    import io

    from prama.cli.base import EXIT_ERROR, Application
    from prama.cli.commands import all_commands

    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps([{"name": "c", "rows": [{"id": 1, "amount": 150}], "expect": {"violating": 0}}])
    )
    out = io.StringIO()
    argv = ["delegate", "check", str(GOOD), "--cases", str(cases), "--large", "100"]
    code = Application(all_commands()).run(argv, out=out)
    assert code == EXIT_ERROR and "FAIL" in out.getvalue()
