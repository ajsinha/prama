"""Incremental re-analysis: a new commit re-reads only the files that changed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from prama.codeintake.archive import Limits
from prama.codeintake.git import snapshot_of
from prama.codeintake.service import analyse
from prama.db import Database

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "code" / "bankco-etl"


async def _analyse(
    database: Database, tenant_id: str, tree: Path, *, dialect: str = "tsql", edit: Any = None
) -> tuple[Any, set[tuple[str, str]]]:
    copy = tree.parent / f"{tree.name}-{len(list(tree.parent.iterdir()))}"
    shutil.copytree(FIXTURE, copy, ignore=shutil.ignore_patterns("gold.json"))
    if edit:
        edit(copy)
    async with database.unit_of_work() as uow:
        source = await uow.code.ensure_source(tenant_id, "bankco", kind="zip")
        run = await analyse(uow, tenant_id, source, snapshot_of(copy, Limits()), dialect=dialect)
        edges = {
            (f"{e.source_dataset}.{e.source_column}", f"{e.target_dataset}.{e.target_column}")
            for e in await uow.lineage.edges(tenant_id)
        }
    return run, edges


async def test_an_unchanged_commit_is_all_reused_and_the_lineage_is_identical(
    started_database: Database, tenant_id: str, tmp_path: Path
) -> None:
    first, before = await _analyse(started_database, tenant_id, tmp_path / "t")
    second, after = await _analyse(started_database, tenant_id, tmp_path / "t")
    assert first.coverage_json["reused"] == 0
    assert second.coverage_json["reused"] == first.coverage_json["units"]
    assert second.base_run_id == first.id
    assert after == before and len(after) >= 18


async def test_a_changed_file_alone_is_re_read_and_its_old_edge_closes(
    started_database: Database, tenant_id: str, tmp_path: Path
) -> None:
    def rename(tree: Path) -> None:
        job = tree / "jobs" / "risk_job.py"
        job.write_text(
            job.read_text().replace('F.col("notional")', 'F.col("notional").alias("gross")')
        )

    first, before = await _analyse(started_database, tenant_id, tmp_path / "t")
    second, after = await _analyse(started_database, tenant_id, tmp_path / "t", edit=rename)
    assert second.coverage_json["reused"] == first.coverage_json["units"] - 1
    assert ("stg.trades.notional", "risk.var_input.gross") in after
    assert ("stg.trades.notional", "risk.var_input.notional") not in after
    assert after - {("stg.trades.notional", "risk.var_input.gross")} == before - {
        ("stg.trades.notional", "risk.var_input.notional")
    }


async def test_a_different_dialect_reuses_nothing(
    started_database: Database, tenant_id: str, tmp_path: Path
) -> None:
    await _analyse(started_database, tenant_id, tmp_path / "t")
    second, _ = await _analyse(started_database, tenant_id, tmp_path / "t", dialect="ansi")
    assert second.coverage_json["reused"] == 0
