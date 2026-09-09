"""What was planted, so the reader can check what was found.

A demonstration that shows only the defects the tool caught is a demonstration
nobody can audit. Each generator here records every defect it introduces —
where, how many, and which control ought to catch it — and the run prints the
planted list against the found list, including the rows that fall in neither
column.

That last part is the point. A tool with no false negatives on a dataset it was
tuned against tells you nothing; a tool that says plainly "these three I did
not catch, and here is why" tells you what it is.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class Defect:
    """One thing deliberately wrong with the fabricated data."""

    #: Short handle used in the README and in the run's output.
    key: str
    dataset: str
    #: What is wrong, in a sentence a business owner would use.
    what: str
    #: How many rows carry it.
    rows: int
    #: The dimension the control that should catch it belongs to.
    dimension: str
    #: Whether Prama can be expected to find it *on this source*. Some cannot
    #: be — a regular-expression control cannot run on SQLite, and saying so up
    #: front is more useful than a study that quietly omits it.
    detectable: bool = True
    #: When it is not, why.
    caveat: str = ""


class DefectLog:
    """Everything a generator planted, in the order it planted it."""

    def __init__(self) -> None:
        self._defects: list[Defect] = []

    def plant(self, defect: Defect) -> Defect:
        self._defects.append(defect)
        return defect

    def add(self, **fields: object) -> Defect:
        return self.plant(Defect(**fields))  # type: ignore[arg-type]

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._defects)

    def __len__(self) -> int:
        return len(self._defects)

    @property
    def detectable(self) -> list[Defect]:
        return [d for d in self._defects if d.detectable]

    @property
    def undetectable(self) -> list[Defect]:
        return [d for d in self._defects if not d.detectable]

    @property
    def rows(self) -> int:
        return sum(d.rows for d in self._defects)

    def by_dataset(self) -> dict[str, list[Defect]]:
        grouped: dict[str, list[Defect]] = {}
        for defect in self._defects:
            grouped.setdefault(defect.dataset, []).append(defect)
        return grouped

    def render(self) -> str:
        lines = [f"{len(self._defects)} defect(s) planted, {self.rows:,} affected row(s):"]
        for defect in self._defects:
            mark = " " if defect.detectable else "!"
            lines.append(
                f"  {mark} {defect.dataset:<22} {defect.rows:>7,}  {defect.what}"
            )
            if defect.caveat:
                lines.append(f"      └─ {defect.caveat}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "count": len(self._defects),
            "rows": self.rows,
            "defects": [dataclasses.asdict(d) for d in self._defects],
        }
