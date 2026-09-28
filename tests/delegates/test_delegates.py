"""DQ delegates: the language, the gate, the host, the control-plane run and the agent.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from prama.backend import compile_for
from prama.backend.execute import judge
from prama.core.errors import PramaError, ValidationError
from prama.db import Database
from prama.delegates.host import DelegateHost, host_from_config
from prama.delegates.registry import DelegateRegistry
from prama.execute import ControlRun
from prama.ir.model import Verdict
from prama.ir.resolve import resolved
from prama.pql import parse_control

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "delegates"
CONTROL = "CHECK payments USING DELEGATE 'test.over_limit@2' (limit = 100)"
ROWS = [
    {"id": 1, "amount": 50, "booked": dt.date(2026, 9, 1)},
    {"id": 2, "amount": 150, "booked": dt.date(2026, 9, 2)},
    {"id": 3, "amount": None, "booked": dt.date(2026, 9, 3)},
]


def _host(*, sandbox: bool = False, **options: Any) -> DelegateHost:
    host = host_from_config(
        {
            "delegates": {
                "paths": [str(FIXTURES / "good")],
                "entry_points": False,
                "sandbox": sandbox,
            }
        }
    )
    for key, value in options.items():
        setattr(host, key, value)
    return host


# -- the language ------------------------------------------------------------


def test_a_delegate_control_round_trips_and_lowers_to_its_own_kind() -> None:
    control = parse_control(CONTROL + " WHERE status = 'released' SEVERITY critical")
    assert parse_control(control.render()) == control
    plan = resolved(control)
    assert plan.assertion_kind == "delegate"
    assert plan.detail == {
        "delegate": "test.over_limit",
        "version": "2",
        "parameters": {"limit": 100},
    }
    other = resolved(parse_control(CONTROL.replace("100", "200")))
    assert other.plan_id != plan.plan_id  # a parameter is part of what the control means


def test_the_engine_is_asked_for_the_declared_columns_filtered_not_a_metric() -> None:
    plan = resolved(parse_control(CONTROL + " WHERE status = 'released'"))
    query = compile_for(plan, "duckdb", columns=("id", "amount")).metric_query
    assert query.startswith('SELECT "id", "amount"') and "status" in query
    assert "COUNT" not in query


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("CHECK payments.amount USING DELEGATE 'x'", "a dataset, not one column"),
        ("CHECK payments USING DELEGATE 'x' (limit = amount)", "must be a number"),
        ("CHECK payments USING DELEGATE 'x' (a = 1, a = 2)", "given twice"),
    ],
)
def test_malformed_delegate_controls_are_refused(source: str, message: str) -> None:
    with pytest.raises(PramaError, match=message):
        parse_control(source)


def test_a_delegate_cannot_be_segmented() -> None:
    with pytest.raises(ValidationError, match="cannot be segmented"):
        resolved(parse_control(CONTROL + " FOR EACH region"))


# -- the gate ----------------------------------------------------------------


def test_an_impure_file_is_refused_before_it_is_imported() -> None:
    registry = DelegateRegistry()
    # phones_home.py raises SystemExit at import. Reaching the assertion at all
    # is the proof that it was never imported.
    registry.load_paths([str(FIXTURES / "impure"), str(FIXTURES / "good")])
    assert "phones_home.py" in registry.refused
    assert "socket" in registry.refused["phones_home.py"]
    assert registry.pinned() == ("test.over_limit@2",)


def _misbehaving() -> Any:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "prama_test_misbehaving", FIXTURES / "misbehaving.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BAD = _misbehaving()


@pytest.mark.parametrize(
    ("delegate", "message"),
    [
        (BAD.Flaky(), "two answers"),
        (BAD.Fragile(), "raised on probe rows"),
        (BAD.Liar(), "cannot be judged"),
    ],
)
def test_admission_refuses_what_cannot_replay_or_be_judged(delegate: Any, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        DelegateRegistry().admit(delegate)


# -- the host ----------------------------------------------------------------


def test_sandboxed_and_in_process_runs_agree_and_both_see_json_values() -> None:
    plan = resolved(parse_control(CONTROL))
    inside = _host(sandbox=False).measure_plan(plan, ROWS)
    sandboxed = _host(sandbox=True).measure_plan(plan, ROWS)
    # They agree on everything but what stood between the delegate and the
    # host, which the evidence records.
    assert inside.parameters.pop("delegate_isolation") == "none: in process"
    assert "audit hook" in sandboxed.parameters.pop("delegate_isolation")
    assert inside == sandboxed
    assert inside.metrics == {"scanned_rows": 3.0, "violating_rows": 2.0}
    assert inside.note == "booked types: str"  # a date arrives as ISO text, everywhere
    assert inside.parameters["delegate"] == "test.over_limit@2"
    assert len(inside.parameters["delegate_hash"]) == 32


def test_the_measurement_is_judged_by_the_shared_threshold() -> None:
    host = _host()
    strict = resolved(parse_control(CONTROL))
    lenient = resolved(parse_control(CONTROL + " AT MOST 2 ROWS"))
    assert judge(strict, host.measure_plan(strict, ROWS).metrics).verdict is Verdict.FAIL
    assert judge(lenient, host.measure_plan(lenient, ROWS).metrics).verdict is Verdict.PASS


def test_a_pinned_version_other_than_the_installed_one_is_refused() -> None:
    plan = resolved(parse_control(CONTROL.replace("@2", "@1")))
    with pytest.raises(ValidationError, match=r"pins test\.over_limit@1"):
        _host().measure_plan(plan, ROWS)


def test_too_many_rows_are_refused_not_truncated() -> None:
    with pytest.raises(ValidationError, match="never sees a silently truncated"):
        _host(max_rows=2).measure_plan(resolved(parse_control(CONTROL)), ROWS)


def test_a_result_that_establishes_nothing_is_indeterminate_not_a_pass() -> None:
    host = DelegateHost(sandbox=False)
    host.registry.admit(BAD.Thin())
    plan = resolved(parse_control("CHECK t USING DELEGATE 'test.thin'"))
    result = host.measure_plan(plan, ROWS)
    assert judge(plan, result.metrics).verdict is Verdict.INDETERMINATE
    rate = resolved(parse_control("CHECK t USING DELEGATE 'test.thin' BELOW 1%"))
    with pytest.raises(ValidationError, match="counts findings"):
        host.measure_plan(rate, ROWS)


# -- the control plane's run -------------------------------------------------


async def _active(database: Database, tenant_id: str, pql: str) -> None:
    async with database.unit_of_work() as uow:
        control, _ = await uow.controls.declare(tenant_id=tenant_id, identity="d", pql=pql)
        await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")


async def test_a_run_records_the_verdict_samples_and_which_delegate_ran(
    started_database: Database, tenant_id: str
) -> None:
    await _active(started_database, tenant_id, CONTROL)
    asked: list[str] = []

    def execute(sql: str) -> list[dict[str, Any]]:
        asked.append(sql)
        return ROWS

    async with started_database.unit_of_work() as uow:
        report = await ControlRun(
            uow, tenant_id, execute=execute, engine="duckdb", delegates=_host()
        ).execute_all()
    (outcome,) = report.outcomes
    record = outcome.record
    assert record.verdict == "fail" and record.metrics["violating_rows"] == 2
    assert record.parameters["delegate"] == "test.over_limit@2"
    assert record.sample_count == 2
    assert asked == ['SELECT "id", "amount", "booked"\nFROM "payments"']


async def test_without_a_delegate_host_the_control_is_an_error_not_a_skip(
    started_database: Database, tenant_id: str
) -> None:
    await _active(started_database, tenant_id, CONTROL)
    async with started_database.unit_of_work() as uow:
        report = await ControlRun(uow, tenant_id, execute=lambda _sql: ROWS).execute_all()
    (outcome,) = report.outcomes
    assert outcome.record.verdict == "error"
    assert "no delegates are configured" in outcome.record.detail


# -- the remote agent ----------------------------------------------------------


def test_an_agent_is_assigned_only_the_delegates_its_own_config_admitted() -> None:
    from prama.agent import Agent, AgentCapabilities, Assignment, ResidencyPolicy, fits
    from prama.agent.residency import SampleDisposition

    plan = resolved(parse_control(CONTROL))
    bare = AgentCapabilities(engines=("duckdb",))
    assert not fits(plan, bare).assignable  # the control: no delegate, no assignment

    agent = Agent(
        "agent-1",
        b"k" * 32,
        executor=lambda _sql: ROWS,
        residency=ResidencyPolicy(
            zone="pci", samples=SampleDisposition.WITHHOLD, investigate_at="the zone"
        ),
        capabilities=bare,
        delegates=_host(),
    )
    hello, _ = agent.hello()
    assert hello.capabilities.delegates == ("test.over_limit@2",)
    assert fits(plan, hello.capabilities).assignable
    pinned_elsewhere = resolved(parse_control(CONTROL.replace("@2", "@3")))
    assert "pins test.over_limit@3" in fits(pinned_elsewhere, hello.capabilities).render()

    outcome = agent.run(Assignment.for_plan(plan, "duckdb", control_id="c1"))
    record = outcome.record
    assert record is not None and record.verdict == "fail"
    assert (
        record.parameters["delegate_hash"]
        == _host().registry.get("test.over_limit").implementation_hash
    )
    assert record.samples_digest == ""  # withheld: the rows stayed in the zone
    assert agent.local_samples  # ...but they are kept there
