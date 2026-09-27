"""Control proposals derived from lineage.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import types
from typing import Any

from prama.derive.lineage_controls import propose


def _edge(src: str, tgt: str, transform: str = "identity", status: str = "parsed") -> Any:
    sd, _, sc = src.rpartition(".")
    td, _, tc = tgt.rpartition(".")
    return types.SimpleNamespace(
        source_dataset=sd,
        source_column=sc,
        target_dataset=td,
        target_column=tc,
        transform=transform,
        status=status,
    )


NOT_NULL = types.SimpleNamespace(
    control_id="c1",
    identity="c1",
    name="notional present",
    dataset="raw.trades",
    pql="CHECK \"raw.trades\".notional IS NOT NULL BECAUSE 'risk needs it'",
)


def test_a_control_is_carried_to_a_copied_column() -> None:
    (proposal,) = [
        p
        for p in propose([_edge("raw.trades.notional", "stg.trades.notional")], [NOT_NULL])
        if p.rule == "lineage_propagated"
    ]
    assert proposal.pql.startswith('CHECK "stg.trades".notional IS NOT NULL')
    assert proposal.dataset == "stg.trades" and not proposal.deferred_because


def test_an_aggregated_column_does_not_inherit_a_row_level_control() -> None:
    # The control: a SUM of non-null values need not be "not null" per row.
    assert not propose([_edge("raw.trades.notional", "mart.p.total", "aggregated")], [NOT_NULL])


def test_a_copied_key_must_exist_in_its_source() -> None:
    (proposal,) = propose([_edge("raw.trades.account_id", "stg.trades.account_id")], [])
    assert proposal.rule == "lineage_referential"
    assert 'REFERENCES "raw.trades".account_id' in proposal.pql


def test_a_proposal_on_an_inferred_edge_is_held() -> None:
    (proposal,) = propose(
        [_edge("raw.trades.account_id", "stg.trades.account_id", status="inferred")], []
    )
    assert proposal.deferred_because


def test_every_proposal_is_valid_pql() -> None:
    from prama.pql.parser import parse_control

    edges = [_edge("raw.trades.notional", "stg.trades.notional"), _edge("a.b_id", "c.b_id")]
    for proposal in propose(edges, [NOT_NULL]):
        parse_control(proposal.pql)
