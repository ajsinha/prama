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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from prama.codeintake.archive import IntakeRefused, Snapshot
from prama.codeintake.inventory import READ, inventory
from prama.codeintake.worker import limit_resources
from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.sql import Gap

#: Kinds worth asking a model about: code that expresses data movement.
MODEL_KINDS = frozenset(
    {"sql", "python", "pyspark", "pandas", "airflow", "scala", "java", "shell", "notebook"}
)

#: Confidence of an edge read by the pattern fallback or an unverified scanner.
FALLBACK_CONFIDENCE = 0.8

#: Methods whose edges are deterministic and verified: stored as `parsed`.
PARSED_METHODS = frozenset(
    {
        "code:sqlglot",
        "code:tsql_procedure",
        "code:plsql_procedure",
        "code:db2_procedure",
        "code:pyspark_ast",
        "code:pandas_ast",
        "code:airflow_sql",
        "code:powerbi_model",
    }
)


async def _reusable(
    uow: Any, tenant_id: str, source: Any, run: Any, snapshot: Snapshot, dialect: str
) -> dict[str, Any]:
    """Units of the base run whose file is byte-identical and read by the same
    reader version and dialect: their results cannot differ, so they are reused.

    A run whose coverage does not record its dialect is no base: reuse must be
    provably equivalent, never probably.
    """
    base = await uow.code.last_completed_run(tenant_id, source.id, before=run.id)
    if base is None or base.coverage_json.get("dialect") != dialect:
        return {}
    run.base_run_id = base.id
    from prama.codeintake.worker import VERSION

    out = {}
    for unit in await uow.code.units(tenant_id, base.id):
        digest = snapshot.files.get(unit.path, ("", 0))[0]
        if digest and digest == unit.blob_sha and unit.scanner_version in (VERSION, ""):
            out[unit.path] = unit
    return out


def run_worker(
    root: Path, dialect: str, *, timeout: float = 300.0, skip: Sequence[str] = ()
) -> dict[str, Any]:
    """Read *root* in a separate, resource-limited process, except the *skip* paths."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(sorted(skip), handle)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "prama.codeintake.worker", str(root), dialect, handle.name],
            capture_output=True,
            timeout=timeout,
            check=False,
            preexec_fn=limit_resources if os.name == "posix" else None,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        Path(handle.name).unlink(missing_ok=True)
        raise IntakeRefused(
            f"reading the code took longer than {timeout:.0f} s",
            remedy="Split the code into smaller sources, or raise codeintake.timeout.",
        ) from exc
    Path(handle.name).unlink(missing_ok=True)
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
    model: Any = None,
    model_units: int = 20,
) -> Any:
    """Read *snapshot* as a run of *source*. Deletes the snapshot's tree after.

    *model* is an LLM gateway with a `lineage` profile, or None. When given, the
    units the parsers left unread or read with gaps (at most *model_units*)
    are offered to it, and only edges that pass `model_lineage.check` are kept,
    as `inferred`.
    """
    run = await uow.code.start_run(tenant_id, source, snapshot.digest)
    found = inventory(snapshot.root, snapshot.files)
    reused = await _reusable(uow, tenant_id, source, run, snapshot, dialect)
    try:
        try:
            result = await asyncio.to_thread(
                run_worker, snapshot.root, dialect, timeout=timeout, skip=list(reused)
            )
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
        # Files unchanged since the base run: their unit is copied, not re-read.
        for path, previous in reused.items():
            rows[path] = uow.code.add_unit(
                tenant_id,
                run.id,
                path=path,
                blob_sha=previous.blob_sha,
                kind=previous.kind,
                scanner=previous.scanner,
                scanner_version=previous.scanner_version,
                statements=previous.statements,
                gaps_json=previous.gaps_json,
            )
            result["units"].append(
                {
                    "path": path,
                    "kind": previous.kind,
                    "statements": previous.statements,
                    "gaps": list(previous.gaps_json),
                    "read": previous.scanner != "none",
                    "reused": True,
                }
            )
            gaps.extend(
                Gap(kind=g["kind"], detail=f"{path}: {g['detail']}", statement="")
                for g in previous.gaps_json
            )
        await uow.flush()  # the units' ids are assigned here, not when added
        unit_ids = {path: row.id for path, row in rows.items()}
        grouped: dict[tuple[str, str], list[Edge]] = defaultdict(list)
        for edge in result["edges"]:
            grouped[(edge["unit"], edge["method"])].append(
                Edge(
                    source=Column(dataset=edge["source"][0], name=edge["source"][1]),
                    target=Column(dataset=edge["target"][0], name=edge["target"][1]),
                    transform=Transform(edge["transform"]),
                    produced_by=edge["unit"],
                    expression=edge["expression"],
                )
            )
        # Only the SQL parser's edges are `parsed`. The pattern fallback and
        # the unverified XML scanners produce `inferred` edges for review.
        batches = [
            (
                edges,
                method,
                "parsed" if method in PARSED_METHODS else "inferred",
                1.0 if method in PARSED_METHODS else FALLBACK_CONFIDENCE,
                unit_ids.get(path),
            )
            for (path, method), edges in grouped.items()
        ]
        # The base run's edges for unchanged files, carried forward as they
        # stand: same method, status and confidence, now on this run's unit.
        by_old_unit = {previous.id: path for path, previous in reused.items()}
        for row in await uow.lineage.unit_edges(tenant_id, list(by_old_unit)):
            batches.append(
                (
                    [
                        Edge(
                            source=Column(dataset=row.source_dataset, name=row.source_column),
                            target=Column(dataset=row.target_dataset, name=row.target_column),
                            transform=Transform(row.transform),
                            produced_by=row.produced_by,
                            expression=row.expression,
                        )
                    ],
                    row.method,
                    row.status,
                    row.confidence,
                    unit_ids.get(by_old_unit[str(row.unit_id)]),
                )
            )
        model_offered = model_kept = model_calls = 0
        if model is not None:
            from prama.codeintake.model_lineage import suggest

            candidates = [
                u
                for u in result["units"]
                if (not u["read"] or u["gaps"])
                and u["kind"] in MODEL_KINDS
                and not u.get("reused")  # its model edges were carried forward
            ][:model_units]
            for unit in candidates:
                text = (snapshot.root / unit["path"]).read_bytes().decode("utf-8", errors="replace")
                try:
                    suggested, offered = await asyncio.to_thread(suggest, model, unit["path"], text)
                except Exception as exc:
                    gaps.append(
                        Gap(kind="model_failed", detail=f"{unit['path']}: {exc}", statement="")
                    )
                    continue
                model_calls += 1
                model_offered += offered
                model_kept += len(suggested)
                for item in suggested:
                    batches.append(
                        (
                            [item.edge],
                            "llm:lineage",
                            "inferred",
                            item.confidence,
                            unit_ids.get(unit["path"]),
                        )
                    )
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
            # What the model offered and what survived the checks, so a model
            # that invents is visible as a low ratio.
            "model_offered": model_offered,
            "model_kept": model_kept,
            # Incremental: files unchanged since the base run, not re-read.
            "reused": len(reused),
            "dialect": dialect,
        }
        run.llm_calls = model_calls
        await uow.code.finish_run(
            run,
            status="succeeded" if not gaps else "partial",
            inventory={k: len(v) for k, v in found.items()},
            coverage=coverage,
        )
        return run
    finally:
        shutil.rmtree(snapshot.root, ignore_errors=True)
