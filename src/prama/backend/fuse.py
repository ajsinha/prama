"""Running many controls in one pass over the data.

A tier-one dataset in a bank carries dozens of controls: a null check on each
critical attribute, a range check, a codelist, a key, a row count. Run
separately that is dozens of scans of the same table, at the same moment every
morning, against a database somebody else is trying to use. It is also the
reason data quality tools acquire a reputation for being expensive and get
scheduled into a window too small for them.

They do not need separate scans. Every one of those controls is a count over
the same rows with a different condition, and SQL computes as many of those in
one pass as you like. Twenty controls become one query with twenty-one columns.

What decides whether two controls can share a pass is narrow and checkable:
the same dataset, the same binding, the same filter, the same segmentation.
Thresholds, severities and justifications differ freely — those are applied
afterwards, to numbers the single query already produced.

The cost estimate falls out of the same grouping. What a run costs is the
number of *scans* it performs, not the number of controls it evaluates, and a
platform that reported the second would be describing something nobody pays
for.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from prama.backend.execute import ControlResult, judge, judge_segments
from prama.backend.sql import SqlCompiler
from prama.ir.model import ControlPlan
from prama.pql.errors import PqlUnsupportedError

#: Metric names are prefixed per control, since two controls in one query will
#: both want to be called violating_rows.
ALIAS = "c{index}__{metric}"


@dataclasses.dataclass(frozen=True, slots=True)
class ScanGroup:
    """Controls that can be answered by one pass over the data."""

    dataset: str
    binding: str
    filter_sql: str
    segment_by: tuple[str, ...]
    plans: tuple[ControlPlan, ...] = ()

    @property
    def key(self) -> tuple[str, str, str, tuple[str, ...]]:
        return (self.dataset, self.binding, self.filter_sql, self.segment_by)

    @property
    def size(self) -> int:
        return len(self.plans)

    def describe(self) -> str:
        scope = f" where {self.filter_sql}" if self.filter_sql else ""
        segment = f", by {', '.join(self.segment_by)}" if self.segment_by else ""
        return f"{self.size} control(s) over {self.dataset}{scope}{segment}"


@dataclasses.dataclass(frozen=True, slots=True)
class FusedQuery:
    """One query answering several controls."""

    group: ScanGroup
    sql: str
    #: Column alias to every (plan index, metric name) it answers. One alias
    #: can serve several controls: twenty controls over one scope all want a
    #: row count, and computing it twenty times is twenty identical columns
    #: for the engine to carry.
    columns: dict[str, tuple[tuple[int, str], ...]] = dataclasses.field(default_factory=dict)

    def unpack(self, rows: list[dict[str, Any]]) -> list[ControlResult]:
        """Split one query's answer back into one result per control."""
        if self.group.segment_by:
            return self._unpack_segmented(rows)
        row = rows[0] if rows else {}
        return [
            judge(plan, self._metrics_for(index, row))
            for index, plan in enumerate(self.group.plans)
        ]

    def _unpack_segmented(self, rows: list[dict[str, Any]]) -> list[ControlResult]:
        results = []
        for index, plan in enumerate(self.group.plans):
            segments = [
                (
                    "|".join(str(row[c]) for c in self.group.segment_by),
                    self._metrics_for(index, row),
                )
                for row in rows
            ]
            results.append(judge_segments(plan, segments))
        return results

    def _metrics_for(self, index: int, row: dict[str, Any]) -> dict[str, float]:
        return {
            metric: float(row[alias])
            for alias, owners in self.columns.items()
            for owner, metric in owners
            if owner == index and row.get(alias) is not None
        }


@dataclasses.dataclass(frozen=True, slots=True)
class RunCost:
    """What a run will cost, in the terms somebody pays for."""

    controls: int
    scans: int
    rows_per_scan: dict[str, int | None] = dataclasses.field(default_factory=dict)

    @property
    def controls_per_scan(self) -> float:
        return self.controls / self.scans if self.scans else 0.0

    @property
    def rows_read(self) -> int | None:
        """Total rows read, or None when any dataset's size is unknown.

        None rather than a partial sum: a total that quietly omits the datasets
        nobody has measured looks precise and is short by however much they
        hold.
        """
        counts = list(self.rows_per_scan.values())
        if not counts or any(c is None for c in counts):
            return None
        return sum(c for c in counts if c is not None)

    def render(self) -> str:
        saved = self.controls - self.scans
        sentence = f"{self.controls} control(s) in {self.scans} scan(s)"
        if saved > 0:
            sentence += f" — {saved} fewer passes over the data than running them separately"
        rows = self.rows_read
        if rows is not None:
            sentence += f", reading about {rows:,} rows"
        return sentence + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "controls": self.controls,
            "scans": self.scans,
            "controls_per_scan": round(self.controls_per_scan, 2),
            "rows_read": self.rows_read,
            "rows_per_scan": self.rows_per_scan,
            "summary": self.render(),
        }


class Fuser:
    """Groups plans into shared passes and compiles one query per group."""

    def __init__(self, target: str) -> None:
        self._compiler = SqlCompiler(target)

    @property
    def dialect(self) -> Any:
        return self._compiler.dialect

    def group(self, plans: list[ControlPlan]) -> list[ScanGroup]:
        """Partition plans by the scope they read.

        Order within a group follows the input, so a fused query's columns are
        laid out predictably and a diff of generated SQL stays readable.
        """
        grouped: dict[tuple[str, str, str, tuple[str, ...]], list[ControlPlan]] = {}
        for plan in plans:
            group = self._empty_group(plan)
            grouped.setdefault(group.key, []).append(plan)
        return [
            ScanGroup(
                dataset=key[0],
                binding=key[1],
                filter_sql=key[2],
                segment_by=key[3],
                plans=tuple(members),
            )
            for key, members in grouped.items()
        ]

    def _empty_group(self, plan: ControlPlan) -> ScanGroup:
        return ScanGroup(
            dataset=plan.scope.dataset,
            binding=plan.scope.binding,
            # The compiled filter, not the IR node: two filters that compile to
            # the same SQL read the same rows however they were written, and
            # grouping on the tree would miss that.
            filter_sql=self._compiler.expression_over(
                plan.scope.filter,
                source=self._compiler.dialect.qualify(plan.scope.binding or plan.scope.dataset),
            )
            if plan.scope.filter is not None
            else "",
            segment_by=plan.scope.segment_by,
            plans=(plan,),
        )

    def fuse(self, group: ScanGroup, *, table: str = "") -> FusedQuery:
        """One query computing every metric of every control in the group."""
        source = self.dialect.qualify(table or group.binding or group.dataset)
        selects: list[str] = []
        columns: dict[str, tuple[tuple[int, str], ...]] = {}
        #: One column per distinct expression. Controls sharing a scope almost
        #: always share metrics — every one of them counts the rows — and an
        #: engine asked for the same aggregate fifty times will compute it
        #: fifty times.
        emitted: dict[str, str] = {}
        for index, plan in enumerate(group.plans):
            missing = self.dialect.missing(plan.requires)
            if missing:
                raise PqlUnsupportedError(
                    f"{self.dialect.name} cannot run one of these controls: it needs "
                    f"{', '.join(sorted(missing))}",
                    remedy=(
                        "Remove it from the run, or run the group on an engine that "
                        "has it. One control that cannot be expressed must not stop "
                        "the rest — but it must not be silently dropped either."
                    ),
                    context={"plan": plan.plan_id, "missing": sorted(missing)},
                )
            for metric in plan.metrics:
                expression = self._compiler.metric_sql(plan, metric, source=source)
                alias = emitted.get(expression)
                if alias is None:
                    alias = ALIAS.format(index=index, metric=metric.name)
                    emitted[expression] = alias
                    selects.append(f"{expression} AS {self.dialect.quote(alias)}")
                columns[alias] = (*columns.get(alias, ()), (index, metric.name))
        projection = ", ".join(selects)
        grouping = ", ".join(self.dialect.quote(c) for c in group.segment_by)
        head = f"{grouping}, {projection}" if grouping else projection
        sql = f"SELECT {head}\nFROM {source}"
        if group.filter_sql:
            sql += f"\nWHERE {group.filter_sql}"
        if grouping:
            sql += f"\nGROUP BY {grouping}"
        return FusedQuery(group=group, sql=sql, columns=columns)

    def cost(
        self, plans: list[ControlPlan], *, rows: dict[str, int | None] | None = None
    ) -> RunCost:
        """What a run costs, before it runs.

        Counted in scans rather than controls, because a scan is what the
        source pays for and the control count is what a dashboard likes.
        """
        known = rows or {}
        groups = self.group(plans)
        return RunCost(
            controls=len(plans),
            scans=len(groups),
            rows_per_scan={g.describe(): known.get(g.dataset) for g in groups},
        )
