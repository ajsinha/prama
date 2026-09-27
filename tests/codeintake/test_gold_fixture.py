"""The gold fixture: Prama's code lineage measured against lineage written by hand.

The gate from docs/design/code-lineage-and-steward-agents.md (P2):

* **Precision.** Of the value edges Prama produces, at least 98% are true.
  A lineage tool that invents edges sends an impact analysis to the wrong
  place.
* **Nothing missed silently.** Every true edge is either found, or lies in a
  file the run reports as not read or as read with gaps. Recall below 100% is
  acceptable; an unexplained miss is not.

Recall is printed on every run, so a change in it is visible.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from prama.codeintake.archive import Limits
from prama.codeintake.git import snapshot_of
from prama.codeintake.service import analyse
from prama.db import Database

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "code" / "bankco-etl"


async def test_bankco_etl_meets_the_gate(
    started_database: Database, tenant_id: str, tmp_path: Path
) -> None:
    gold = {
        (e["from"], e["to"]): e["file"]
        for e in json.loads((FIXTURE / "gold.json").read_text())["edges"]
    }
    tree = tmp_path / "bankco"
    shutil.copytree(FIXTURE, tree, ignore=shutil.ignore_patterns("gold.json"))
    snapshot = snapshot_of(tree, Limits())
    async with started_database.unit_of_work() as uow:
        source = await uow.code.ensure_source(tenant_id, "bankco", kind="zip")
        run = await analyse(uow, tenant_id, source, snapshot, dialect="tsql")
        units = {u.path: u for u in await uow.code.units(tenant_id, run.id)}
        rows = [
            e
            for e in await uow.lineage.edges(tenant_id)
            if e.transform not in ("filter", "join_key")
        ]
    found = {
        (f"{e.source_dataset}.{e.source_column}", f"{e.target_dataset}.{e.target_column}")
        for e in rows
    }
    true_positives = found & gold.keys()
    precision = len(true_positives) / len(found) if found else 0.0
    recall = len(true_positives) / len(gold)
    print(
        f"\nbankco-etl: precision {precision:.2f}, recall {recall:.2f}, {len(found)} edges produced"
    )

    assert precision >= 0.98, f"invented edges: {sorted(found - gold.keys())}"
    missed = {edge: path for edge, path in gold.items() if edge not in found}
    unexplained = {
        edge: path
        for edge, path in missed.items()
        if path in units and units[path].scanner != "none" and not units[path].gaps_json
    }
    assert not unexplained, f"true edges missed with no gap reported: {unexplained}"
    # The control: this fixture is not trivially satisfied by reading nothing.
    # 0.83 before the PySpark reader, 0.67 of today's gold before the pandas and
    # Airflow readers; a drop is a regression.
    assert recall >= 0.95
