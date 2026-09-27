"""A change to SQL, assessed against the estate's lineage, as a CI gate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import types
from typing import Any

from prama.lineage.change import assess, changed_columns
from prama.lineage.graph import Column, Edge, LineageGraph, Transform

BEFORE = "INSERT INTO stg.a (amt, ccy) SELECT t.notional, t.ccy FROM raw.trades t"
AFTER_DROP = "INSERT INTO stg.a (ccy) SELECT t.ccy FROM raw.trades t"


def _estate() -> LineageGraph:
    graph = LineageGraph()
    graph.add(Edge(Column("stg.a", "amt"), Column("rpt.line_23", "amount"), Transform.AGGREGATED))
    return graph


class _Uow:
    """Just enough of a unit of work: controls and attestations per dataset."""

    def __init__(self, controlled: str = "", attested: str = "") -> None:
        control = types.SimpleNamespace(
            control_id="c1", name="line 23 complete", severity="critical"
        )
        attestation = types.SimpleNamespace(
            scope=attested, attester_name="Ada", period_end="2026-09-30"
        )
        self.controls = types.SimpleNamespace(
            for_dataset=_async(lambda _t, d: [control] if d == controlled else [])
        )
        self.attestations = types.SimpleNamespace(
            current=_async(lambda _t: [attestation] if attested else [])
        )


def _async(fn: Any) -> Any:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return wrapper


def test_dropping_a_column_is_a_change_to_it() -> None:
    changed = {c.qualified for c in changed_columns(BEFORE, AFTER_DROP)}
    assert changed == {"stg.a.amt"}
    assert not changed_columns(BEFORE, BEFORE)  # the control: no change, nothing changed


async def test_it_names_the_attestation_and_control_at_risk() -> None:
    changed = changed_columns(BEFORE, AFTER_DROP)
    impact = await assess(
        _Uow(controlled="rpt.line_23", attested="rpt.line_23"), "t", changed, graph=_estate()
    )
    assert impact.at_risk
    assert "rpt.line_23.amount" in dict(impact.reached)
    assert impact.attestations[0]["scope"] == "rpt.line_23"
    assert impact.controls[0]["severity"] == "critical"


async def test_a_change_reaching_nothing_controlled_is_not_at_risk() -> None:
    changed = changed_columns(BEFORE, AFTER_DROP)
    impact = await assess(_Uow(), "t", changed, graph=_estate())
    assert impact.reached and not impact.at_risk
