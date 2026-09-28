"""Most used, least controlled: where a steward's next hour does the most good.

Joins usage (how often a dataset is read) with coverage (how many active
controls it has, and how many are failing), and lists the busiest datasets
with the least protection first. Used datasets that nobody has declared are
listed separately, because the first thing they need is a declaration.

Usage orders this list and does nothing else. It is not an input to any score
(`prama.score` never reads it, and a test holds that), because popularity says
nothing about whether data is right.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

_UNRESOLVED = ("fail", "error", "skipped", "indeterminate")


def _matches(used: str, slug: str) -> bool:
    return used == slug or used.endswith("." + slug) or used.replace(".", "_").endswith(slug)


async def priorities(uow: Any, tenant_id: str, *, days: int = 30) -> dict[str, Any]:
    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    usage = await uow.usage.totals(tenant_id, since=since)
    live = await uow.controls.live(tenant_id)
    latest = await uow.evidence.latest_per_control(tenant_id)
    failing: dict[str, int] = {}
    for record in latest.values():
        if record.verdict in _UNRESOLVED:
            failing[record.dataset] = failing.get(record.dataset, 0) + 1
    rows, claimed = [], set()
    for version in await uow.datasets.list_current(tenant_id, limit=5000):
        used = [name for name in usage if _matches(name, version.slug)]
        claimed.update(used)
        queries = sum(usage[n][0] for n in used)
        readers = max((usage[n][1] for n in used), default=0)
        controls = sum(1 for c in live if c.dataset == version.slug)
        rows.append(
            {
                "dataset": version.name,
                "slug": version.slug,
                "queries": queries,
                "readers": readers,
                "controls": controls,
                "failing": failing.get(version.slug, 0),
                "criticality": version.criticality,
            }
        )
    rows.sort(key=lambda r: (-r["queries"], r["controls"], r["criticality"]))
    undeclared = sorted(
        (
            {"dataset": name, "queries": q, "readers": u}
            for name, (q, u) in usage.items()
            if name not in claimed
        ),
        key=lambda r: -r["queries"],
    )
    return {
        "since": since,
        "datasets": rows,
        "undeclared": undeclared[:50],
        "has_usage": bool(usage),
    }
