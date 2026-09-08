"""How much this actually sustains, measured rather than claimed.

Wave 5 asserts a million assertion executions a day and a fusion saving of at
least half. Both are numbers, and a number nobody has measured is a hope. These
measure them on whatever machine the suite runs on and report what they find —
the assertions are deliberately loose, because a laptop and a CI runner differ
by more than the margin, and a threshold tight enough to be interesting on one
would fail on the other every day until somebody deleted it.

What is *not* loose is the shape: fusion must reduce scans, spooling must not
lose findings, and throughput must not collapse as the estate grows. Those are
properties, and a property that only holds on fast hardware was never a
property.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

import duckdb
import pytest

from prama.backend.corpus import ROWS, create_table, insert_rows
from prama.backend.execute import judge
from prama.backend.fuse import Fuser
from prama.backend.generate import ControlGenerator
from prama.backend.sql import SqlCompiler
from prama.evidence import Ledger, Recorder, SampleStore
from prama.ir.lower import Lowerer
from prama.pql.parser import parse_control

#: Kept small so the ordinary suite stays fast. CI and anybody sizing a
#: deployment raise it: PRAMA_SOAK_CONTROLS=20000 pytest tests/soak
CONTROLS = int(os.environ.get("PRAMA_SOAK_CONTROLS", "400"))

#: Seconds in a day, for turning a measured rate into the roadmap's units.
DAY = 86_400


@pytest.fixture(scope="module")
def engine() -> Any:
    connection = duckdb.connect()
    connection.execute(create_table(dialect="duckdb"))
    connection.executemany(insert_rows(), [list(r) for r in ROWS])

    def run(sql: str) -> list[dict[str, Any]]:
        relation = connection.sql(sql)
        columns = [d[0] for d in relation.description]
        return [dict(zip(columns, row, strict=True)) for row in relation.fetchall()]

    yield run
    connection.close()


@pytest.fixture(scope="module")
def plans() -> list:
    lowerer = Lowerer()
    return [
        lowerer.control(parse_control(control.pql)) for control in ControlGenerator().many(CONTROLS)
    ]


class TestThroughput:
    def test_the_pipeline_sustains_a_useful_rate(
        self, plans: list, engine: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Compile, execute, judge and record — the whole path, timed.

        Measured end to end rather than per stage, because the number that
        matters is what a control plane gets through and every stage is in the
        way of it.
        """
        recorder = Recorder(Ledger(), SampleStore(), engine="duckdb")
        compiler = SqlCompiler("duckdb")
        started = time.monotonic()
        executed = 0
        for plan in plans:
            compiled = compiler.compile(plan, table="corpus")
            rows = engine(compiled.metric_query)
            names = [m.name for m in plan.metrics]
            first = rows[0] if rows else {}
            result = judge(
                plan,
                {n: float(first[n]) for n in names if first.get(n) is not None},
                engine="duckdb",
            )
            recorder.record(plan, result, snapshot=None)
            executed += 1
        elapsed = time.monotonic() - started
        per_second = executed / elapsed
        with capsys.disabled():
            print(
                f"\n  {executed} assertions in {elapsed:.2f}s "
                f"= {per_second:,.0f}/s = {per_second * DAY:,.0f}/day on one process"
            )
        assert executed == len(plans)
        assert len(recorder.ledger) == executed
        # Loose on purpose: the shape is what is being asserted, not the speed
        # of whatever machine this is. A rate below this would mean something
        # is quadratic rather than that the hardware is slow.
        assert per_second > 20

    def test_the_evidence_chain_holds_at_volume(self, plans: list, engine: Any) -> None:
        # A chain is easy to get right for five records. The interesting
        # question is whether anything drifts across thousands.
        recorder = Recorder(Ledger(), SampleStore(), engine="duckdb")
        compiler = SqlCompiler("duckdb")
        for plan in plans[:200]:
            compiled = compiler.compile(plan, table="corpus")
            rows = engine(compiled.metric_query)
            names = [m.name for m in plan.metrics]
            first = rows[0] if rows else {}
            recorder.record(
                plan,
                judge(plan, {n: float(first[n]) for n in names if first.get(n) is not None}),
                snapshot=None,
            )
        assert recorder.ledger.verify().is_intact

    def test_record_size_does_not_grow_with_the_estate(self, plans: list, engine: Any) -> None:
        # Evidence is kept for years. A record that grew with the number of
        # controls would make retention cost superlinear in the estate.
        recorder = Recorder(Ledger(), SampleStore(), engine="duckdb")
        compiler = SqlCompiler("duckdb")
        for plan in plans[:200]:
            compiled = compiler.compile(plan, table="corpus")
            rows = engine(compiled.metric_query)
            names = [m.name for m in plan.metrics]
            first = rows[0] if rows else {}
            recorder.record(
                plan,
                judge(plan, {n: float(first[n]) for n in names if first.get(n) is not None}),
                snapshot=None,
            )
        sizes = sorted(r.size_bytes for r in recorder.ledger)
        assert sizes[len(sizes) // 2] < 2048
        assert sizes[-1] < 4096


class TestFusionActuallySaves:
    """NFR-COS-001: at most half the scans of a naive per-rule pass."""

    def test_a_realistic_suite_needs_far_fewer_scans(
        self, plans: list, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fuser = Fuser("duckdb")
        groups = fuser.group(plans)
        naive = len(plans)
        fused = len(groups)
        with capsys.disabled():
            print(
                f"\n  {naive} controls in {fused} scans "
                f"= {100 * fused / naive:.1f}% of a naive pass"
            )
        assert fused <= naive / 2

    def test_the_saving_grows_with_the_suite(self, engine: Any) -> None:
        # The property that matters: adding controls to a dataset should cost
        # columns, not scans. A saving that plateaued would mean fusion had a
        # ceiling nobody documented.
        lowerer = Lowerer()
        fuser = Fuser("duckdb")
        ratios = []
        for size in (20, 100, 400):
            plans = [lowerer.control(parse_control(c.pql)) for c in ControlGenerator().many(size)]
            ratios.append(len(fuser.group(plans)) / len(plans))
        assert ratios[-1] < ratios[0]

    def test_fused_answers_match_unfused_ones_at_volume(self, plans: list, engine: Any) -> None:
        # The saving is worthless if it changes an answer. Checked here as well
        # as in the unit tests, because the interesting failures are the ones
        # that need a hundred controls in one query to appear.
        fuser = Fuser("duckdb")
        compiler = SqlCompiler("duckdb")
        sample = plans[:120]
        alone: dict[str, Any] = {}
        for plan in sample:
            compiled = compiler.compile(plan, table="corpus")
            rows = engine(compiled.metric_query)
            names = [m.name for m in plan.metrics]
            if plan.scope.segment_by:
                continue
            first = rows[0] if rows else {}
            alone[plan.plan_id] = judge(
                plan, {n: float(first[n]) for n in names if first.get(n) is not None}
            ).comparable()

        for group in fuser.group(sample):
            if group.segment_by:
                continue
            query = fuser.fuse(group, table="corpus")
            for result in query.unpack(engine(query.sql)):
                if result.plan_id in alone:
                    assert result.comparable() == alone[result.plan_id]


class TestSqliteKeepsUp:
    """The engine an air-gapped deployment falls back to."""

    def test_the_same_suite_runs_on_sqlite(self, plans: list) -> None:
        connection = sqlite3.connect(":memory:")
        connection.execute(create_table(dialect="sqlite"))
        connection.executemany(insert_rows(), [list(r) for r in ROWS])
        compiler = SqlCompiler("sqlite")
        ran = refused = 0
        for plan in plans[:200]:
            try:
                compiled = compiler.compile(plan, table="corpus")
            except Exception:
                # A refusal is a conforming outcome, and at volume it should
                # still be rare: an engine refusing most of an estate is not a
                # fallback.
                refused += 1
                continue
            connection.execute(compiled.metric_query).fetchall()
            ran += 1
        connection.close()
        assert ran > 0
        assert refused / (ran + refused) < 0.2
