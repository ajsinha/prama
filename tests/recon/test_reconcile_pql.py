"""RECONCILE in PQL: parsed, compiled to two fetches, run by the engine, judged, and proposed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import types
from datetime import date
from typing import Any

import pytest

from prama.backend import compile_for
from prama.backend.execute import judge
from prama.core.errors import PramaError
from prama.db import Database
from prama.derive.lineage_controls import propose
from prama.execute import ControlRun
from prama.ir.model import Verdict
from prama.ir.resolve import resolved
from prama.pql import parse_control
from prama.recon.pql import measure

SOURCE = (
    "RECONCILE positions AGAINST ledger ON (account, desk = book) "
    "COMPARING amount = balance WITHIN 1.00 EUR SEVERITY critical"
)
LEFT = [
    {"account": "A1", "desk": "EQ", "amount": 100.00},
    {"account": "A2", "desk": "EQ", "amount": 250.00},
    {"account": "A3", "desk": "FX", "amount": 75.00},
]
RIGHT = [
    {"account": "A1", "book": "EQ", "balance": 100.40},  # within 1.00: not a break
    {"account": "A2", "book": "EQ", "balance": 260.00},  # a value break
]  # A3 is missing from the ledger


def test_it_round_trips_and_says_what_it_checks() -> None:
    control = parse_control(SOURCE)
    assert parse_control(control.render()) == control
    assert control.render().startswith("RECONCILE positions AGAINST ledger")
    assert "within 1.00 EUR" in control.describe()


def test_it_compiles_to_one_fetch_per_side() -> None:
    compiled = compile_for(resolved(parse_control(SOURCE)), "duckdb")
    assert compiled.metric_query == 'SELECT "account", "desk", "amount"\nFROM "positions"'
    assert compiled.counterpart_query == 'SELECT "account", "book", "balance"\nFROM "ledger"'


def test_a_filter_on_one_side_is_refused() -> None:
    with pytest.raises(PramaError, match="no WHERE or FOR EACH"):
        resolved(parse_control(SOURCE + " WHERE desk = 'EQ'"))


def test_the_engine_counts_genuine_breaks_and_the_threshold_judges() -> None:
    plan = resolved(parse_control(SOURCE))
    metrics, run = measure(plan, LEFT, RIGHT, business_date=date(2026, 9, 27))
    assert metrics["violating_rows"] == 2  # A2's value, A3 missing; A1 within tolerance
    assert metrics["matched_pairs"] == 2 and metrics["missing_in_counterpart"] == 1
    assert judge(plan, metrics).verdict is Verdict.FAIL
    lenient = resolved(parse_control(SOURCE.replace(" SEVERITY", " AT MOST 2 ROWS SEVERITY")))
    assert judge(lenient, metrics).verdict is Verdict.PASS
    clean, _ = measure(plan, LEFT[:1], RIGHT[:1], business_date=date(2026, 9, 27))
    assert judge(plan, clean).verdict is Verdict.PASS


async def test_a_run_records_evidence_and_fills_the_break_workbench(
    started_database: Database, tenant_id: str
) -> None:
    async with started_database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="r", pql=SOURCE)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="bo")

    def execute(sql: str) -> list[dict[str, Any]]:
        return LEFT if '"positions"' in sql else RIGHT

    async with started_database.unit_of_work() as uow:
        report = await ControlRun(uow, tenant_id, execute=execute, engine="duckdb").execute_all()
        breaks = await uow.breaks.outstanding(tenant_id, "positions against ledger")
    (outcome,) = report.outcomes
    assert outcome.record.verdict == "fail" and outcome.record.metrics["violating_rows"] == 2
    assert "positions against ledger" in outcome.record.detail
    assert len(breaks) == 2


def test_an_agent_runs_it_beside_the_data() -> None:
    from prama.agent import Agent, AgentCapabilities, Assignment, ResidencyPolicy
    from prama.agent.residency import SampleDisposition

    plan = resolved(parse_control(SOURCE))
    agent = Agent(
        "a1",
        b"k" * 32,
        executor=lambda sql: LEFT if '"positions"' in sql else RIGHT,
        residency=ResidencyPolicy(zone="z", samples=SampleDisposition.WITHHOLD, investigate_at="z"),
        capabilities=AgentCapabilities(engines=("duckdb",)),
    )
    outcome = agent.run(Assignment.for_plan(plan, "duckdb", control_id="r"))
    assert outcome.record is not None and outcome.record.verdict == "fail"
    assert outcome.record.metrics["violating_rows"] == 2


def _edge(src: str, tgt: str, status: str = "parsed") -> Any:
    sd, _, sc = src.rpartition(".")
    td, _, tc = tgt.rpartition(".")
    return types.SimpleNamespace(
        source_dataset=sd,
        source_column=sc,
        target_dataset=td,
        target_column=tc,
        transform="identity",
        status=status,
    )


def test_lineage_proposes_a_reconciliation_for_a_copy_at_the_same_grain() -> None:
    edges = [
        _edge("stg.trades.account_id", "mart.positions.account_id"),
        _edge("stg.trades.notional", "mart.positions.notional"),
    ]
    (proposal,) = [p for p in propose(edges, []) if p.rule == "lineage_reconcile"]
    control = parse_control(proposal.pql)
    assert control.target == "mart.positions" and control.assertion.against == "stg.trades"
    assert proposal.deferred_because == ""
    # It must run, not merely parse: without a stated bound the engine refuses it.
    from prama.recon.pql import definition_of

    assert definition_of(resolved(control)).tolerance.absolute == 0
    # A filtered copy is held: every row the filter drops would be a break.
    status = types.SimpleNamespace(
        **{**vars(_edge("stg.trades.status", "mart.positions.*")), "transform": "filter"}
    )
    (held,) = [p for p in propose([*edges, status], []) if p.rule == "lineage_reconcile"]
    assert "filter on status" in held.deferred_because
    # The counterfactual: an aggregated amount is not a same-grain copy.
    aggregated = [edges[0], types.SimpleNamespace(**{**vars(edges[1]), "transform": "aggregated"})]
    assert not [p for p in propose(aggregated, []) if p.rule == "lineage_reconcile"]


NORMALISED = (
    "RECONCILE positions AGAINST ledger ON (book) COMPARING mv = balance_usd "
    "WITHIN 1 USD NORMALISING ccy TO 'USD' USING RATES fx"
)


def test_normalising_converts_before_comparing() -> None:
    plan = resolved(parse_control(NORMALISED))
    assert parse_control(parse_control(NORMALISED).render()) == parse_control(NORMALISED)
    compiled = compile_for(plan, "duckdb")
    assert '"ccy"' in compiled.metric_query and compiled.rates_query == 'SELECT *\nFROM "fx"'
    left = [{"book": "B1", "mv": 100.0, "ccy": "EUR"}, {"book": "B1", "mv": 50.0, "ccy": "USD"}]
    right = [{"book": "B1", "balance_usd": 160.0}]  # 100 EUR at 1.10 + 50 USD
    rates = [{"currency": "EUR", "rate": 1.10}, {"currency": "USD", "rate": 1.0}]
    metrics, _ = measure(plan, left, right, business_date=date(2026, 9, 27), rates=rates)
    assert metrics["violating_rows"] == 0
    # The counterfactual: without the rates, the same book is a break.
    wrong = resolved(parse_control(NORMALISED.split(" NORMALISING")[0]))
    unnormalised, _ = measure(wrong, left, right, business_date=date(2026, 9, 27))
    assert unnormalised["violating_rows"] == 1


def test_a_declared_reconciliation_is_proposed_as_runnable_pql() -> None:
    from decimal import Decimal

    from prama.derive.relationships import ComparisonKind, ComparisonSpec
    from prama.semantic.relationships import MatchKey, Tolerance

    spec = ComparisonSpec(
        identity="r",
        kind=ComparisonKind.RECONCILIATION,
        left="position_feed",
        right="general_ledger",
        match_keys=(MatchKey(left="book"),),
        compare=("market_value = balance_usd",),
        tolerance=Tolerance(absolute=Decimal("1"), currency="USD", relative=Decimal("0.0001")),
    )
    control = parse_control(spec.to_pql() or "")
    assert control.assertion.amount == ("market_value", "balance_usd")
    assert control.assertion.relative == "0.01" and control.assertion.currency == "USD"
    parity = ComparisonSpec(
        identity="p",
        kind=ComparisonKind.ROW_COUNT_PARITY,
        left="a",
        right="b",
        match_keys=(MatchKey(left="k"),),
    )
    assert parity.to_pql() is None  # no PQL form yet: stays a specification
