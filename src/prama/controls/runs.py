"""Running the estate against a registered connection, on the server.

The same `ControlRun` the CLI, the scheduler and the case studies use — so one
definition of "run a control", one evidence format, one hash chain — driven by
a connection somebody registered rather than by a path somebody typed. The
server reads the source itself; the caller sends no rows.

Where the path may point is the one decision this module adds, and it is made
in `prama.connect.sources.confined`: under ``runs.roots``, never at Prama's own
database, with the engine fenced in as well as the path.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from prama.connect.sources.confined import OpenedSource, open_confined
from prama.core.errors import NotFoundError, ValidationError
from prama.execute import ControlRun


def roots_of(config: Any) -> list[str]:
    """The directories a server-side run may read, from ``runs.roots``."""
    return [str(root) for root in config.get_list("runs.roots", [])]


def protected_of(config: Any) -> list[str]:
    """Files no run may read: Prama's own database, when it is a file.

    Read without asking which dialect is configured, so nothing here branches
    on it: a PostgreSQL deployment simply has no such file to protect, and a
    path that names nothing protects nothing.
    """
    path = config.get_str("database.sqlite.path", "")
    return [path] if path and path != ":memory:" else []


async def open_connection(uow: Any, tenant_id: str, connection_id: str, config: Any) -> Any:
    """This estate's connection, opened confined — or a refusal naming why not."""
    connection = await uow.connections.current(connection_id, tenant_id=tenant_id)
    if connection is None:
        raise NotFoundError(
            f"connection {connection_id!r} does not exist in this estate",
            remedy="Register it with POST /connections, or list the connections.",
            context={"connection_id": connection_id},
        )
    opened = open_confined(
        connection.source_type,
        dict(connection.config_json or {}),
        roots=roots_of(config),
        forbidden=protected_of(config),
    )
    return connection, opened


async def dataset_scope(uow: Any, tenant_id: str, names: Iterable[str]) -> set[str]:
    """The dataset names a pass covers, from names or dataset identifiers.

    A control names its dataset by the name it has in the engine, which is the
    declared dataset's slug; a caller may know either. Something that is
    neither is refused rather than silently matching nothing — a scope that
    names a typo would otherwise report every control as "on another source".
    """
    wanted = [str(name).strip() for name in names if str(name).strip()]
    scope: set[str] = set()
    for name in wanted:
        by_id = await uow.datasets.current(name, tenant_id=tenant_id)
        if by_id is not None:
            scope.add(by_id.slug)
            continue
        if await uow.datasets.by_slug(tenant_id, name) is not None:
            scope.add(name)
            continue
        if await uow.controls.for_dataset(tenant_id, name):
            scope.add(name)  # controls on a dataset nobody declared still run
            continue
        raise ValidationError(
            f"no declared dataset or control target is called {name!r}",
            remedy="Name datasets by their slug or identifier, as GET /datasets lists them.",
            context={"dataset": name},
        )
    return scope


async def run_connection(
    uow: Any,
    tenant_id: str,
    *,
    connection_id: str,
    config: Any,
    datasets: Iterable[str] = (),
    samples: bool = False,
    due_only: bool = False,
    actor_id: str | None = None,
    delegates: Any = None,
) -> dict[str, Any]:
    """Run the live controls against one connection and return the run report.

    Scoped to *datasets* when any are named, as the harness scopes one pass per
    source; everything live otherwise. The report names what did not run as
    well as what did: controls that could not be executed, and controls left
    alone because their data is on another source.
    """
    connection, opened = await open_connection(uow, tenant_id, connection_id, config)
    scope = await dataset_scope(uow, tenant_id, datasets)
    try:
        report = await ControlRun(
            uow,
            tenant_id,
            execute=opened.execute,
            # Failing rows are personal data on a retention clock; kept only
            # when the caller asks, as `prama control run --samples` does.
            sample=opened.execute if samples else None,
            engine=opened.engine,
            triggered_by="schedule" if due_only else "manual",
            actor_id=actor_id,
            respect_schedule=due_only,
            datasets=scope or None,
            delegates=delegates,
        ).execute_all()
    finally:
        opened.close()
    return report_out(report, connection=connection, opened=opened, scope=scope)


def report_out(
    report: Any, *, connection: Any, opened: OpenedSource, scope: set[str]
) -> dict[str, Any]:
    """A run report as JSON: every outcome with its evidence record."""
    return {
        "run_id": report.run_id,
        "summary": report.describe(),
        "connection_id": str(connection.connection_id),
        "engine": opened.engine,
        "datasets": sorted(scope) or None,
        "tables": list(opened.tables),
        "skipped_files": list(opened.skipped),
        "controls": len(report.outcomes),
        "executed": report.executed,
        "failed_to_run": report.failed_to_run,
        "verdicts": report.verdicts,
        "outcomes": [
            {
                "control_id": outcome.control_id,
                "dataset": outcome.record.dataset,
                "ran": outcome.ran,
                "error": outcome.error,
                "verdict": outcome.record.verdict,
                "metrics": dict(outcome.record.metrics),
                "detail": outcome.record.detail,
                "record": outcome.record.to_dict(),
            }
            for outcome in report.outcomes
        ],
        "not_run": [
            {
                "control_id": item.control_id,
                "dataset": item.dataset,
                "reason": item.reason,
                "detail": item.detail,
                "is_a_defect": bool(item.is_a_defect),
            }
            for item in report.skipped
        ],
    }


def run_row_out(run: Any) -> dict[str, Any]:
    """One stored run, as listed."""
    return {
        "run_id": str(run.id),
        "triggered_by": run.triggered_by,
        "actor_id": run.actor_id,
        "engine": run.engine,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "record_count": run.record_count,
        "summary": run.detail,
    }


__all__ = [
    "dataset_scope",
    "open_connection",
    "protected_of",
    "report_out",
    "roots_of",
    "run_connection",
    "run_row_out",
]
