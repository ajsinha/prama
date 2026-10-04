"""A lineage reader for source-to-target mapping sheets: the worked example of
docs/developer/code-readers.md.

Before any ETL is written, a bank's analysts write the mapping down: a sheet
with one row per target column, naming its source and what happens on the way.
That sheet is often the only lineage anybody has for a legacy feed, so it is
worth reading, saved as CSV:

    source,target,transform,job
    raw.trades.acct,stg.trades.account_id,rename,load_trades
    stg.trades.notional,mart.positions.exposure,aggregated,build_positions

A row it cannot read becomes a **gap**, named, and the coverage figure says how
much of the sheet produced lineage. A transform it does not recognise is a gap
too, not a guess: an edge marked ``identity`` that was really an aggregation
makes every impact estimate built on it wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import csv
import io
from typing import ClassVar

from prama.lineage.graph import Column, Edge, Transform
from prama.lineage.scan import Scanner, ScanResult
from prama.lineage.sql import Extraction, Gap

REQUIRED = ("source", "target")


class MappingSheetScanner(Scanner):
    """Reads a ``source,target[,transform][,job]`` CSV into column edges."""

    name: ClassVar[str] = "mapping_sheet"
    verified_against: ClassVar[str] = (
        "sheets written by hand for tests/docs/test_developer_examples.py; not a "
        "customer's mapping workbook, which is where the surprises are"
    )

    def scan(self, text: str, *, source: str = "") -> ScanResult:
        reader = csv.DictReader(io.StringIO(text))
        header = [h.strip().lower() for h in reader.fieldnames or []]
        missing = [column for column in REQUIRED if column not in header]
        if missing:
            # Found the file and nothing in it that it could read: a wrong
            # configuration, reported as one rather than as an empty graph.
            return ScanResult(
                scanner=self.name,
                source=source,
                extraction=Extraction(),
                misconfigured=(
                    f"the sheet has no {' or '.join(missing)} column; its header is "
                    f"{', '.join(header) or 'empty'}"
                ),
            )

        edges: list[Edge] = []
        gaps: list[Gap] = []
        rows = 0
        for line, raw in enumerate(reader, start=2):
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            rows += 1
            unit = f"{source or 'sheet'}:{line}"
            try:
                edge_from = Column.parse(row["source"])
                edge_to = Column.parse(row["target"])
            except ValueError as exc:
                gaps.append(Gap(kind="unparsed", detail=str(exc), statement=unit))
                continue
            named = row.get("transform") or "identity"
            try:
                transform = Transform(named.lower())
            except ValueError:
                gaps.append(
                    Gap(
                        kind="unknown_transform",
                        detail=(
                            f"{named!r} is not one of "
                            f"{', '.join(t.value for t in Transform)}; the edge is left "
                            "out rather than guessed"
                        ),
                        statement=unit,
                    )
                )
                continue
            edges.append(
                Edge(
                    source=edge_from,
                    target=edge_to,
                    transform=transform,
                    produced_by=row.get("job") or source,
                    expression=f"mapping sheet row {line}",
                )
            )

        return ScanResult(
            scanner=self.name,
            source=source,
            extraction=Extraction(edges=tuple(edges), gaps=tuple(gaps), statements=rows),
            units_found=rows,
            units_unread=len(gaps),
        )
