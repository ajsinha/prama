"""Compiling a plan into an agent's assignment: the control plane's half.

An agent executes a query the control plane compiled and never compiles its
own, so this lives with the compiler, in the server, and the agent receives
only the result (`prama_kernel.agent.protocol.Assignment`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_kernel.agent.protocol import Assignment

from prama.backend import compile_for


def assignment_for(
    plan: Any,
    engine: str,
    *,
    table: str = "",
    columns: tuple[str, ...] = (),
    control_id: str = "",
) -> Assignment:
    """The assignment for *plan*, compiled here, by the control plane.

    For a delegate plan the query fetches rows, not metrics; *columns* are the
    delegate's declared columns when the control plane knows them, otherwise
    every column is fetched inside the agent's zone.
    """
    compiled = compile_for(plan, engine, table=table or plan.scope.dataset, columns=columns)
    return Assignment(
        plan_id=plan.plan_id,
        dataset=plan.scope.dataset,
        binding=plan.scope.binding or plan.scope.dataset,
        engine=engine,
        metric_query=compiled.metric_query,
        metric_names=compiled.metric_names,
        sample_query=compiled.sample_query,
        counterpart_query=compiled.counterpart_query,
        rates_query=compiled.rates_query,
        plan={**plan.to_dict(), "control_id": control_id},
    )
