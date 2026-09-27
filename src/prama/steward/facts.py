"""What is failing, as plain sentences, gathered without any model.

Kept apart from the tools that call models, on purpose: `test_layering.py`
refuses any module that both talks to a model and handles pass/fail results
(CON-007). The steward's model sees only these sentences, never the records.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any


async def failing_facts(uow: Any, tenant_id: str, *, limit: int = 50) -> list[str]:
    """One sentence per control that is not passing."""
    facts = []
    for record in await uow.evidence.failing(tenant_id, limit=limit):
        bad = int(record.metrics.get("violating_rows", 0))
        scanned = int(record.metrics.get("scanned_rows", 0))
        outcome = str(getattr(record, "verdict", ""))
        facts.append(
            f"{record.dataset}: control {record.control_id} {outcome} ({bad} of {scanned} rows)"
        )
    return facts
