"""What the miners are looking at, and how much it is worth.

Every mined constraint is a statement about a sample, and almost every way
mining goes wrong is a statement about a sample being read as a statement about
the data. This module exists so that the sample can answer questions about
itself, and so that a miner cannot forget to ask.

**The failure this is mostly here to prevent.** A key mined from one day's
extract is unique in that extract and repeats on the second day, every time,
for every daily snapshot table there has ever been. ``(account_id)`` is
perfectly unique within Monday and is not the key; ``(account_id,
business_date)`` is. A miner that sees one partition cannot tell these apart —
not because it is a bad miner, but because the evidence is genuinely not there
— and the only honest thing it can do is say so, loudly, on every constraint it
proposes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from typing import Any

#: Below this many rows, nothing mined is worth proposing. A constraint that
#: holds across two hundred rows holds across two hundred rows.
MINIMUM_ROWS = 200

#: A sample covering less than this fraction of the table is reported as a
#: sample rather than as the data. Not a threshold for refusing to mine —
#: mining a sample is the normal case — but for how the finding is described.
REPRESENTATIVE_FRACTION = 0.9


@dataclasses.dataclass(frozen=True, slots=True)
class Sample:
    """Rows a miner may look at, and everything known about where they came from."""

    dataset: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    #: The table's real row count, when the connector could report it cheaply.
    #: Without it a miner cannot tell a full read from a 1% sample, and the two
    #: support very different claims.
    total_rows: int | None = None
    #: The column the data is partitioned or dated by, if the dataset declares
    #: one. The single most important thing to know about a sample: a key mined
    #: within one partition is not a key.
    partition_column: str = ""
    #: Where the rows came from: "full scan", "reservoir over 30 days", …
    method: str = ""

    @property
    def size(self) -> int:
        return len(self.rows)

    @property
    def is_usable(self) -> bool:
        return self.size >= MINIMUM_ROWS

    @property
    def coverage(self) -> float | None:
        """Fraction of the table examined, when that is knowable."""
        if not self.total_rows:
            return None
        return min(1.0, self.size / self.total_rows)

    @property
    def is_representative(self) -> bool:
        coverage = self.coverage
        return coverage is not None and coverage >= REPRESENTATIVE_FRACTION

    @property
    def partitions_seen(self) -> int:
        """Distinct values of the partition column in this sample.

        One means every constraint mined here is a within-partition constraint,
        whatever it looks like.
        """
        if not self.partition_column:
            return 0
        return len({row.get(self.partition_column) for row in self.rows})

    @property
    def spans_one_partition(self) -> bool:
        return self.partition_column != "" and self.partitions_seen <= 1

    def values(self, column: str) -> list[Any]:
        return [row.get(column) for row in self.rows]

    def tuples(self, columns: Sequence[str]) -> list[tuple[Any, ...]]:
        return [tuple(row.get(c) for c in columns) for row in self.rows]

    def caveats(self) -> tuple[str, ...]:
        """Everything a reviewer needs to discount this sample by.

        Assembled here rather than at each miner, so a new miner cannot ship
        without them. Every one of these has been the reason a mined constraint
        was wrong in production.
        """
        notes: list[str] = []
        if self.spans_one_partition:
            notes.append(
                f"every row in this sample has the same {self.partition_column}, so "
                f"anything found here holds *within* one {self.partition_column} and "
                f"may not hold across them — the classic false key"
            )
        coverage = self.coverage
        if coverage is not None and coverage < REPRESENTATIVE_FRACTION:
            notes.append(
                f"{self.size:,} of {self.total_rows:,} rows were examined ({coverage:.1%}); "
                f"a constraint can hold on a sample and fail on the rest"
            )
        elif coverage is None:
            notes.append(
                "the table's size is unknown, so what fraction of it this sample "
                "represents cannot be stated"
            )
        if self.size < 1000:
            notes.append(
                f"{self.size:,} rows is a small sample; patterns in it are easy to find "
                f"and easy to be wrong about"
            )
        return tuple(notes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "columns": list(self.columns),
            "size": self.size,
            "total_rows": self.total_rows,
            "coverage": self.coverage,
            "partition_column": self.partition_column,
            "partitions_seen": self.partitions_seen,
            "method": self.method,
            "caveats": list(self.caveats()),
        }

    @classmethod
    def of(
        cls,
        dataset: str,
        rows: Iterable[dict[str, Any]],
        *,
        total_rows: int | None = None,
        partition_column: str = "",
        method: str = "",
    ) -> Sample:
        materialised = tuple(dict(r) for r in rows)
        columns: list[str] = []
        for row in materialised:
            for key in row:
                if key not in columns:
                    columns.append(key)
        return cls(
            dataset=dataset,
            columns=tuple(columns),
            rows=materialised,
            total_rows=total_rows,
            partition_column=partition_column,
            method=method,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Evidence:
    """The observation behind one mined constraint.

    Kept rather than folded into a score, because "unique across 4.2 million
    rows spanning ninety days" and "unique across 400 rows from one day" are
    both a confidence of 1.0 by any naive measure, and a reviewer needs to be
    able to tell them apart in one glance.
    """

    rows_examined: int
    #: Rows the constraint held for.
    supporting: int
    #: Rows it did not hold for. Zero for an exact constraint.
    violating: int = 0
    #: Rows excluded because a value involved was null. Counted separately
    #: because SQL's aggregate functions silently skip them, and a "unique"
    #: column that is ninety percent null is not a key — it is an empty column
    #: with a few values in it.
    null_excluded: int = 0
    distinct: int = 0
    caveats: tuple[str, ...] = ()

    @property
    def is_exact(self) -> bool:
        return self.violating == 0

    @property
    def support(self) -> float:
        """Fraction of the applicable rows that satisfy it."""
        applicable = self.rows_examined - self.null_excluded
        return self.supporting / applicable if applicable else 0.0

    @property
    def null_fraction(self) -> float:
        return self.null_excluded / self.rows_examined if self.rows_examined else 0.0

    def describe(self) -> str:
        head = (
            f"holds for all {self.supporting:,} of {self.rows_examined:,} rows examined"
            if self.is_exact
            else (
                f"holds for {self.supporting:,} of "
                f"{self.rows_examined - self.null_excluded:,} applicable rows "
                f"({self.support:.2%}); {self.violating:,} exceptions"
            )
        )
        if self.null_excluded:
            head += (
                f". {self.null_excluded:,} rows ({self.null_fraction:.1%}) were excluded "
                f"because a value was missing"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_examined": self.rows_examined,
            "supporting": self.supporting,
            "violating": self.violating,
            "null_excluded": self.null_excluded,
            "distinct": self.distinct,
            "support": round(self.support, 6),
            "null_fraction": round(self.null_fraction, 6),
            "is_exact": self.is_exact,
            "caveats": list(self.caveats),
            "summary": self.describe(),
        }
