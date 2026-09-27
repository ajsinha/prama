"""Reading a received snapshot into units and lineage.

The snapshot (from `archive.extract` or `git.fetch`) is read by the sandboxed
worker in its own process. Its units are stored with their hashes, its edges go
to the lineage store as the source `code:<name>` (each pointing at the unit it
came from), and the extracted tree is deleted however the run ends. Only
hashes and the short expressions edges cite are kept.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from prama.codeintake.archive import IntakeRefused, Snapshot
from prama.codeintake.inventory import READ, inventory
from prama.codeintake.worker import limit_resources
from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Gap

#: Confidence of an edge the worker read with the pattern fallback.
FALLBACK_CONFIDENCE = 0.8


def run_worker(root: Path, dialect: str, *, timeout: float = 300.0) -> dict[str, Any]:
    """Read *root* in a separate, resource-limited process."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "prama.codeintake.worker", str(root), dialect],
            capture_output=True,
            timeout=timeout,
            check=False,
            preexec_fn=limit_resources if os.name == "posix" else None,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise IntakeRefused(
            f"reading the code took longer than {timeout:.0f} s",
            remedy="Split the code into smaller sources, or raise codeintake.timeout.",
        ) from exc
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise IntakeRefused(
            "the code reader stopped before finishing",
            remedy="A file may be too large or pathological to parse; the run records which.",
            context={"detail": tail},
        )
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


async def analyse(
    uow: Any,
    tenant_id: str,
    source: Any,
    snapshot: Snapshot,
    *,
    dialect: str = "ansi",
    timeout: float = 300.0,
) -> Any:
    """Read *snapshot* as a run of *source*. Deletes the snapshot's tree after."""
    run = await uow.code.start_run(tenant_id, source, snapshot.digest)
    found = inventory(snapshot.root, snapshot.files)
    try:
        try:
            result = await asyncio.to_thread(run_worker, snapshot.root, dialect, timeout=timeout)
        except IntakeRefused as exc:
            await uow.code.finish_run(
                run,
                status="failed",
                inventory={k: len(v) for k, v in found.items()},
                coverage={},
                error=str(exc),
            )
            return run
        rows: dict[str, Any] = {}
        gaps: list[Gap] = []
        for unit in result["units"]:
            digest = snapshot.files.get(unit["path"], ("", 0))[0]
            row = uow.code.add_unit(
                tenant_id,
                run.id,
                path=unit["path"][:1024],
                blob_sha=digest,
                kind=unit["kind"],
                scanner=READ.get(unit["kind"], "none"),
                scanner_version=result["version"],
                statements=unit["statements"],
                gaps_json=unit["gaps"][:200],
            )
            rows[unit["path"]] = row
            gaps.extend(
                Gap(kind=g["kind"], detail=f"{unit['path']}: {g['detail']}", statement="")
                for g in unit["gaps"]
            )
        await uow.flush()  # the units' ids are assigned here, not when added
        unit_ids = {path: row.id for path, row in rows.items()}
        grouped: dict[tuple[str, bool], list[Edge]] = defaultdict(list)
        for edge in result["edges"]:
            grouped[(edge["unit"], edge["fallback"])].append(
                Edge(
                    source=Column(dataset=edge["source"][0], name=edge["source"][1]),
                    target=Column(dataset=edge["target"][0], name=edge["target"][1]),
                    transform=Transform(edge["transform"]),
                    produced_by=edge["unit"],
                    expression=edge["expression"],
                )
            )
        batches = [
            (
                edges,
                "code:regex" if fallback else f"code:{READ['sql']}",
                "inferred" if fallback else "parsed",
                FALLBACK_CONFIDENCE if fallback else 1.0,
                unit_ids.get(path),
            )
            for (path, fallback), edges in grouped.items()
        ]
        read = [u for u in result["units"] if u["read"]]
        lineage = await uow.lineage.ensure_source(
            tenant_id,
            f"code:{source.name}"[:128],
            kind="code",
            location=(source.url or source.name)[:512],
            dialect=dialect,
        )
        statements = sum(u["statements"] for u in read)
        understood = (
            1.0 - sum(1 for g in gaps if g.kind in ("unparsed", "regex_fallback")) / statements
            if statements
            else 0.0
        )
        await uow.lineage.record_run(
            tenant_id,
            lineage,
            batches,
            gaps,
            statements=statements,
            understood=max(0.0, understood),
        )
        coverage = {
            "units": len(result["units"]),
            "read": len(read),
            "unread_kinds": sorted({u["kind"] for u in result["units"] if not u["read"]}),
            "edges": len(result["edges"]),
            "gaps": len(gaps),
            "symlinks_ignored": len(snapshot.symlinks),
        }
        await uow.code.finish_run(
            run,
            status="succeeded" if not gaps else "partial",
            inventory={k: len(v) for k, v in found.items()},
            coverage=coverage,
        )
        return run
    finally:
        shutil.rmtree(snapshot.root, ignore_errors=True)
