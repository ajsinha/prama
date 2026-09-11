"""Declaration to verdict, against real data.

Everything else in the suite tests one link. This tests the chain: a business
owner declares a dataset, Γ derives controls from the declaration, somebody
accepts one, it runs against an actual table, and the evidence appears on the
console — with the verdict the data deserves rather than the one the pipeline
found convenient.

It uses DuckDB over a real table rather than a stub executor, because the
failure this is written against is the one a stub cannot have: SQL that
compiles cleanly, looks right, and does not run.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from prama.db import Database
from prama.derive import ControlGenerator
from prama.derive.persisted import dataset_declaration_of
from prama.execute import ControlRun
from prama.semantic.services import DatasetService
from prama.semantic.values import Grain

pytestmark = pytest.mark.anyio


@pytest.fixture
def warehouse(tmp_path: Path) -> Any:
    """A DuckDB file with one table and one genuine defect.

    Two rows share an account and instrument on the same day, which the
    declared grain forbids. The whole test is whether Prama finds that without
    being told where to look.
    """
    import duckdb

    path = tmp_path / "warehouse.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE positions_eod (
            account_id     VARCHAR,
            instrument_id  VARCHAR,
            as_of_date     VARCHAR,
            notional       DOUBLE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO positions_eod VALUES
            ('A1', 'ISIN1', '2026-09-08', 100.0),
            ('A1', 'ISIN2', '2026-09-08', 250.0),
            ('A2', 'ISIN1', '2026-09-08', 400.0),
            ('A1', 'ISIN1', '2026-09-08', 100.0)
        """
    )
    connection.close()
    return path


def executor_for(path: Path) -> Any:
    """The shipped executor, not a stand-in.

    Building a private one here would test a query runner nobody uses and
    leave the real one — the one the CLI calls — unexercised end to end.
    """
    from prama.connect.sources.query import executor_for as build

    execute, _close = build(path, "duckdb")
    return execute


class TestDeclarationToVerdict:
    async def test_a_declared_grain_catches_a_real_duplicate(
        self,
        ui: httpx.AsyncClient,
        started_database: Database,
        tenant_id: str,
        warehouse: Path,
    ) -> None:
        """The product's whole claim, executed once end to end.

        A business owner says what one row represents. Nobody writes SQL. The
        duplicate is found.
        """
        # 1. The declaration. One sentence, from somebody who owns the data.
        async with started_database.unit_of_work() as uow:
            _, version = await DatasetService(uow).declare(
                tenant_id=tenant_id,
                name="positions_eod",
                description="End-of-day positions.",
                shape="table",
                criticality=2,
                grain=Grain(
                    attributes=("account_id", "instrument_id", "as_of_date"),
                    statement="one position per account per instrument per business day",
                ),
                authored_by="alice",
                approved_by="bob",
            )
            dataset_id = str(version.dataset_id)

        # 2. Γ derives the controls the declaration implies.
        async with started_database.unit_of_work() as uow:
            stored = await uow.datasets.require_current(dataset_id, tenant_id=tenant_id)
            attributes = await uow.attributes.for_dataset(dataset_id)
            generation = ControlGenerator().generate(dataset_declaration_of(stored, attributes))
            derived = [c for c in generation.controls if c.rule.startswith("grain")]
            assert derived, "the grain should generate at least one control"

            # 3. Somebody accepts one. Until then it does not run.
            for control in derived:
                entity, _ = await uow.controls.declare(
                    tenant_id=tenant_id,
                    identity=control.identity,
                    pql=control.content,
                    rule=control.rule,
                    criticality=2,
                )
                await uow.controls.activate(str(entity.id), tenant_id=tenant_id, approved_by="bob")

        # 4. It runs against the actual table.
        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=executor_for(warehouse), engine="duckdb"
            ).execute_all()

        assert report.failed_to_run == 0, report.describe()
        assert "fail" in report.verdicts, report.describe()

        # 5. And it is on the console, as an incident, saying what was found.
        body = " ".join((await ui.get("/incidents")).text.split())
        assert "positions_eod" in body
        assert "Nothing has been examined" not in body

    async def test_the_evidence_chain_verifies_after_a_real_run(
        self, started_database: Database, tenant_id: str, warehouse: Path
    ) -> None:
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="grain",
                pql=(
                    "CHECK positions_eod HAS UNIQUE KEY "
                    "(account_id, instrument_id, as_of_date) "
                    "SEVERITY critical DIMENSION uniqueness BECAUSE 'declared grain'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bob")

        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=executor_for(warehouse), engine="duckdb"
            ).execute_all()
            verification = await uow.evidence.verify(tenant_id)
            [record] = await uow.evidence.chain(tenant_id)

        assert verification.is_intact, verification.render()
        assert record.verdict == "fail"
        # Four rows scanned, three distinct keys: the duplicate is the finding.
        assert record.metrics["scanned_rows"] == 4
        assert record.metrics["distinct_keys"] == 3

    async def test_a_clean_control_passes_against_the_same_data(
        self, started_database: Database, tenant_id: str, warehouse: Path
    ) -> None:
        """The counterfactual. A runner that failed everything would pass the
        test above and be worthless."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="notnull",
                pql=(
                    "CHECK positions_eod.notional IS NOT NULL "
                    "SEVERITY major DIMENSION completeness BECAUSE 'CDE'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bob")

        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=executor_for(warehouse), engine="duckdb"
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)

        assert record.verdict == "pass"
        assert record.metrics["scanned_rows"] == 4

    async def test_a_control_against_a_missing_table_is_a_finding(
        self, started_database: Database, tenant_id: str, warehouse: Path
    ) -> None:
        """The commonest real failure, and the one that must not take the rest
        of the run with it."""
        async with started_database.unit_of_work() as uow:
            control, _ = await uow.controls.declare(
                tenant_id=tenant_id,
                identity="ghost",
                pql=(
                    "CHECK no_such_table.x IS NOT NULL "
                    "SEVERITY major DIMENSION completeness BECAUSE 'why'"
                ),
            )
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bob")

        async with started_database.unit_of_work() as uow:
            report = await ControlRun(
                uow, tenant_id, execute=executor_for(warehouse), engine="duckdb"
            ).execute_all()
            [record] = await uow.evidence.chain(tenant_id)

        assert record.verdict == "error"
        assert report.failed_to_run == 1
        assert "no_such_table" in record.detail

    async def test_the_scorecard_reflects_the_run(
        self,
        ui: httpx.AsyncClient,
        started_database: Database,
        tenant_id: str,
        warehouse: Path,
    ) -> None:
        """The last link: the number a business owner reads is derived from
        evidence produced by a control they accepted, against their data."""
        async with started_database.unit_of_work() as uow:
            for identity, pql in (
                (
                    "grain",
                    "CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date) "
                    "SEVERITY critical DIMENSION uniqueness BECAUSE 'declared grain'",
                ),
                (
                    "notnull",
                    "CHECK positions_eod.notional IS NOT NULL "
                    "SEVERITY major DIMENSION completeness BECAUSE 'CDE'",
                ),
            ):
                control, _ = await uow.controls.declare(
                    tenant_id=tenant_id, identity=identity, pql=pql
                )
                await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bob")

        async with started_database.unit_of_work() as uow:
            await ControlRun(
                uow, tenant_id, execute=executor_for(warehouse), engine="duckdb"
            ).execute_all()

        body = (await ui.get("/scorecards")).text
        assert "dim-uniqueness" in body
        assert "dim-completeness" in body
        assert "positions_eod" in body


class TestTheShippedExecutor:
    def test_it_opens_read_only(self, warehouse: Path) -> None:
        """A control is a check. It has no business being able to write, and
        opening read-only means a defect in a generated query cannot damage the
        data it was meant to examine."""
        import duckdb

        from prama.connect.sources.query import executor_for as build

        execute, close = build(warehouse, "duckdb")
        try:
            with pytest.raises(duckdb.Error):
                execute("DELETE FROM positions_eod")
        finally:
            close()

    def test_a_missing_file_says_so_before_anything_runs(self, tmp_path: Path) -> None:
        from prama.connect.sources.query import executor_for as build
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="no file at"):
            build(tmp_path / "absent.duckdb", "duckdb")

    def test_an_unknown_engine_lists_the_real_ones(self, warehouse: Path) -> None:
        from prama.connect.sources.query import executor_for as build
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="duckdb"):
            build(warehouse, "oracle")
