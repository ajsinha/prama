"""Controls, PQL, proposals, derivation (Γ), runs and the schedule.

The heart of Prama from Python: declare a dataset (``client.datasets``), derive
its controls, accept them, run them against a registered connection, and read
the verdicts — the same stages a case study walks, with the server doing the
reading.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg


@namespace("controls")
class Controls(Resource):
    """The estate of controls: author, approve, silence, retire, try, import."""

    @endpoint("GET", "/controls")
    def list(
        self,
        *,
        status: str | None = None,
        dataset: str | None = None,
        overdue: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        """Controls, by ``status`` (proposed, active, suppressed, retired) or ``dataset``;
        ``overdue=True`` lists the ones silenced past their expiry."""
        return self._get(
            "/controls",
            status=status,
            dataset=dataset,
            overdue=overdue,
            limit=limit,
            offset=offset,
        )

    @endpoint("GET", "/controls/{control_id}")
    def get(self, control_id: str) -> Any:
        return self._get(f"/controls/{seg(control_id)}")

    @endpoint("GET", "/controls/{control_id}/history")
    def history(self, control_id: str) -> Any:
        """Every version of a control, oldest first."""
        return self._get(f"/controls/{seg(control_id)}/history")

    @endpoint("POST", "/controls")
    def declare(self, pql: str, **fields: Any) -> Any:
        """Author a control; it is a proposal until activated. Fields: identity, rule,
        source_ref, criticality, schedule, owner_id, origin, reason."""
        return self._post("/controls", body(pql=pql, **fields))

    @endpoint("POST", "/controls/{control_id}/activate")
    def activate(self, control_id: str, *, reason: str | None = None) -> Any:
        """Approve a control, so it runs. Needs ``control:approve``."""
        return self._post(f"/controls/{seg(control_id)}/activate", body(reason=reason))

    @endpoint("POST", "/controls/{control_id}/suppress")
    def suppress(self, control_id: str, *, until: str, because: str) -> Any:
        """Silence a control until an ISO-8601 instant, for a stated reason."""
        return self._post(
            f"/controls/{seg(control_id)}/suppress", body(until=until, because=because)
        )

    @endpoint("POST", "/controls/{control_id}/retire")
    def retire(self, control_id: str, *, reason: str | None = None) -> Any:
        """Stop running a control. It is kept, with its evidence."""
        return self._post(f"/controls/{seg(control_id)}/retire", body(reason=reason))

    @endpoint("POST", "/controls/preview")
    def preview(self, pql: str, connection_id: str, *, max_rows: int | None = None) -> Any:
        """Run a control once against a connection. Records no evidence."""
        return self._post(
            "/controls/preview", body(pql=pql, connection_id=connection_id, max_rows=max_rows)
        )

    @endpoint("POST", "/controls/backtest")
    def backtest(
        self,
        pql: str,
        connection_id: str,
        period_column: str,
        *,
        days: int | None = None,
        max_rows: int | None = None,
    ) -> Any:
        """Run a control once per business day over the last ``days``. Records no evidence."""
        return self._post(
            "/controls/backtest",
            body(
                pql=pql,
                connection_id=connection_id,
                period_column=period_column,
                days=days,
                max_rows=max_rows,
            ),
        )

    @endpoint("GET", "/rule-builder")
    def builder_questions(self) -> Any:
        """The rule builder's questions, and the estate's datasets and columns."""
        return self._get("/rule-builder")

    @endpoint("POST", "/rule-builder")
    def build(self, dataset: str, rule: str, **answers: Any) -> Any:
        """A control from the rule builder's answers: ``{"pql", "sentence"}``. Stores nothing.
        Answers: severity, because, column, columns, values, pattern, lower, upper, minimum,
        maximum, reference_dataset, reference_column, tolerance_minutes, due_time, calendar,
        tolerated_percent, unknown_is_violation."""
        return self._post("/rule-builder", body(dataset=dataset, rule=rule, **answers))

    @endpoint("POST", "/controls/import")
    def import_(self, text: str, source_format: str, *, declare: bool | None = None) -> Any:
        """Translate dbt, Great Expectations or Soda tests to PQL, with what did not come
        across. ``declare=True`` also stores them as proposals."""
        return self._post(
            "/controls/import", body(text=text, source_format=source_format, declare=declare)
        )


@namespace("pql")
class Pql(Resource):
    """The language: check, explain, compile, format, complete. Nothing is stored."""

    @endpoint("POST", "/pql/check")
    def check(self, source: str, *, catalogue: dict[str, Any] | None = None) -> Any:
        """Parse, type-check and lint, against the estate's datasets or ``catalogue``."""
        return self._post("/pql/check", body(source=source, catalogue=catalogue))

    @endpoint("POST", "/pql/explain")
    def explain(self, source: str) -> Any:
        """Each control as a sentence, with how its functions differ from a spreadsheet."""
        return self._post("/pql/explain", body(source=source))

    @endpoint("POST", "/pql/compile")
    def compile(self, source: str, *, dialect: str | None = None, fuse: bool | None = None) -> Any:
        """The SQL each control becomes on ``dialect``, and what it does not test."""
        return self._post("/pql/compile", body(source=source, dialect=dialect, fuse=fuse))

    @endpoint("POST", "/pql/format")
    def format(self, source: str) -> Any:
        """The controls in canonical form."""
        return self._post("/pql/format", body(source=source))

    @endpoint("POST", "/pql/completions")
    def completions(self, source: str, line: int, column: int) -> Any:
        return self._post("/pql/completions", body(source=source, line=line, column=column))

    @endpoint("POST", "/pql/hover")
    def hover(self, source: str, line: int, column: int) -> Any:
        return self._post("/pql/hover", body(source=source, line=line, column=column))

    @endpoint("GET", "/pql/functions")
    def functions(self, *, engine: str | None = None) -> Any:
        """The function catalogue, and each engine's pushdown coverage."""
        return self._get("/pql/functions", engine=engine)


@namespace("proposals")
class Proposals(Resource):
    """What the declarations imply, awaiting a decision."""

    @endpoint("GET", "/proposals")
    def list(self, *, dataset_id: str | None = None) -> Any:
        """The queue: proposals, what could not be proposed, and counts already decided."""
        return self._get("/proposals", dataset_id=dataset_id)

    @endpoint("POST", "/proposals/accept")
    def accept(
        self,
        identity: str,
        pql: str,
        *,
        rule: str | None = None,
        dataset_id: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Accept a proposal: it becomes an active control. Needs ``control:approve``."""
        return self._post(
            "/proposals/accept",
            body(identity=identity, pql=pql, rule=rule, dataset_id=dataset_id, reason=reason),
        )

    @endpoint("POST", "/proposals/reject")
    def reject(
        self,
        identity: str,
        content_hash: str,
        *,
        reason: str | None = None,
        note: str | None = None,
    ) -> Any:
        """Turn a proposal down, recorded so it is not proposed again."""
        return self._post(
            "/proposals/reject",
            body(identity=identity, content_hash=content_hash, reason=reason, note=note),
        )

    @endpoint("GET", "/proposals/rejections")
    def rejections(self, *, limit: int | None = None) -> Any:
        return self._get("/proposals/rejections", limit=limit)


@namespace("derive")
class Derive(Resource):
    """Γ: controls from declarations, and what could not be derived."""

    @endpoint("GET", "/datasets/{dataset_id}/derivation")
    def preview_dataset(self, dataset_id: str) -> Any:
        """What Γ derives from a declared dataset, without storing anything."""
        return self._get(f"/datasets/{seg(dataset_id)}/derivation")

    @endpoint("POST", "/datasets/{dataset_id}/derive")
    def dataset(
        self,
        dataset_id: str,
        *,
        declare: bool | None = None,
        accept: bool | None = None,
        schedule: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Γ over a declared dataset. ``declare=True`` stores the controls as proposals;
        ``accept=True`` also activates them (needs ``control:approve``)."""
        return self._post(
            f"/datasets/{seg(dataset_id)}/derive",
            body(declare=declare, accept=accept, schedule=schedule, reason=reason),
        )

    @endpoint("GET", "/relationships/{relationship_id}/derivation")
    def preview_relationship(self, relationship_id: str) -> Any:
        """What Γ derives from a declared relationship, without storing anything."""
        return self._get(f"/relationships/{seg(relationship_id)}/derivation")

    @endpoint("POST", "/relationships/{relationship_id}/derive")
    def relationship(
        self,
        relationship_id: str,
        *,
        declare: bool | None = None,
        accept: bool | None = None,
        schedule: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Γ over a declared relationship; comparison specs come back, never declared.
        Accepting needs the relationship to be confirmed."""
        return self._post(
            f"/relationships/{seg(relationship_id)}/derive",
            body(declare=declare, accept=accept, schedule=schedule, reason=reason),
        )


@namespace("runs")
class Runs(Resource):
    """Runs the server performs against a registered connection, and their evidence."""

    @endpoint("POST", "/runs")
    def start(
        self,
        connection_id: str,
        *,
        datasets: Sequence[str] | None = None,
        samples: bool | None = None,
        due_only: bool | None = None,
    ) -> Any:
        """Run the active controls against a connection and return the run report:
        every outcome with its verdict, metrics and evidence record. Needs
        ``control:approve``; the connection's path must be under ``runs.roots``."""
        return self._post(
            "/runs",
            body(
                connection_id=connection_id,
                datasets=list(datasets) if datasets is not None else None,
                samples=samples,
                due_only=due_only,
            ),
        )

    @endpoint("GET", "/runs")
    def list(self, *, limit: int | None = None, unfinished: bool | None = None) -> Any:
        return self._get("/runs", limit=limit, unfinished=unfinished)

    @endpoint("GET", "/runs/{run_id}")
    def get(self, run_id: str) -> Any:
        """One run and every evidence record it wrote."""
        return self._get(f"/runs/{seg(run_id)}")


@namespace("schedule")
class ScheduleResource(Resource):
    """When controls run on their own."""

    @endpoint("GET", "/schedule")
    def get(self) -> Any:
        """Each active control's schedule, what is due now, and the scheduler's ticks."""
        return self._get("/schedule")

    @endpoint("POST", "/schedule/run")
    def run_now(self) -> Any:
        """Run one scheduler tick now. Needs the scheduler on, serving this estate."""
        return self._post("/schedule/run")
