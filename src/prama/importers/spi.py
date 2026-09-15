"""Bringing an existing control estate across, without pretending.

Nobody adopts a data quality platform on an empty estate. They have four
hundred dbt tests, a Soda scan, a Great Expectations suite somebody wrote in
2023, and a spreadsheet. The question they ask first is not "what can this do"
but "what happens to what I already have".

The honest answer has three parts, and an importer that gives fewer than three
is selling something:

* **What came across exactly.** Same meaning, same coverage, nothing assumed.
* **What came across with a caveat.** The construct exists here but means
  something slightly different, and the difference is stated.
* **What did not come across, and why.** Named individually, never summarised
  as a count. "382 of 400 imported" reads as success; the eighteen are the
  ones somebody has to decide about, and burying them is how an estate
  silently loses coverage during a migration.

The rule this package holds to: **never guess**. A construct whose meaning is
not certain is reported unmapped rather than approximated, because an
approximated control passes review — it looks like the others — and then
quietly checks something else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from typing import Any

from prama.pql import ast


@dataclasses.dataclass(frozen=True, slots=True)
class Unmapped:
    """Something the source estate has and Prama did not import."""

    #: What it was called in the source, verbatim, so it can be found again.
    source: str
    reason: str
    #: What to do instead, when there is something.
    remedy: str = ""
    dataset: str = ""

    def render(self) -> str:
        line = f"{self.source}: {self.reason}"
        return f"{line}\n    → {self.remedy}" if self.remedy else line


@dataclasses.dataclass(frozen=True, slots=True)
class Caveat:
    """Something that came across, with a difference worth stating."""

    control: str
    note: str

    def render(self) -> str:
        return f"{self.control}\n    ! {self.note}"


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    """What an import produced, in full."""

    controls: tuple[ast.Control, ...] = ()
    unmapped: tuple[Unmapped, ...] = ()
    caveats: tuple[Caveat, ...] = ()
    source_format: str = ""

    @property
    def imported(self) -> int:
        return len(self.controls)

    @property
    def is_complete(self) -> bool:
        return not self.unmapped

    def render(self) -> str:
        """A report somebody has to read before approving the migration."""
        lines = [f"Imported {self.imported} control(s) from {self.source_format}."]
        if self.caveats:
            lines.append("")
            lines.append(f"{len(self.caveats)} came across with a difference worth knowing:")
            lines.extend(f"  {c.render()}" for c in self.caveats)
        if self.unmapped:
            lines.append("")
            # Listed individually and never as a count. These are the ones
            # somebody has to decide about, and a number hides them.
            lines.append(f"{len(self.unmapped)} did not come across:")
            lines.extend(f"  {u.render()}" for u in self.unmapped)
        else:
            lines.append("")
            lines.append("Nothing was left behind.")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_format": self.source_format,
            "imported": self.imported,
            "complete": self.is_complete,
            "controls": [c.render() for c in self.controls],
            "caveats": [{"control": c.control, "note": c.note} for c in self.caveats],
            "unmapped": [
                {
                    "source": u.source,
                    "dataset": u.dataset,
                    "reason": u.reason,
                    "remedy": u.remedy,
                }
                for u in self.unmapped
            ],
        }

    def merged_with(self, other: ImportResult) -> ImportResult:
        return ImportResult(
            controls=self.controls + other.controls,
            unmapped=self.unmapped + other.unmapped,
            caveats=self.caveats + other.caveats,
            source_format=self.source_format or other.source_format,
        )


class Importer(ABC):
    """Reads one tool's control definitions."""

    #: What this reads, as it would be named to a user.
    format_name: str = ""

    @abstractmethod
    def read(self, document: Any) -> ImportResult:
        """Import an already-parsed document."""

    def read_text(self, text: str) -> ImportResult:
        """Import from the file's own text."""
        return self.read(self._parse(text))

    def _parse(self, text: str) -> Any:
        import yaml

        return yaml.safe_load(text)


class Collector:
    """Accumulates controls, caveats and gaps while an importer works.

    A small thing that matters: an importer built around a collector cannot
    forget to report a construct it skipped, because skipping means calling
    ``unmapped`` and there is nowhere else to put it.
    """

    def __init__(self, source_format: str) -> None:
        self._format = source_format
        self._controls: list[ast.Control] = []
        self._unmapped: list[Unmapped] = []
        self._caveats: list[Caveat] = []

    def control(self, pql: str, *, caveat: str = "") -> None:
        from prama.pql.errors import PqlSyntaxError
        from prama.pql.parser import parse_control

        first_line = pql.splitlines()[0] if pql.splitlines() else pql
        try:
            parsed = parse_control(pql)
        except PqlSyntaxError as exc:
            # The whole point of this class, stated in its own docstring: a
            # construct that does not come across is *reported*, not fatal. A
            # `PqlSyntaxError` escaping here aborted an entire multi-hundred
            # control migration because one carried-over expression did not
            # parse — which is the outcome `unmapped` exists to prevent, thrown
            # away at the one place it was easiest to throw away.
            #
            # Recorded rather than swallowed: it lands in the report `prama
            # control import` prints, under the same heading as everything else
            # that did not come across. QA round 4, `IMP-007`.
            self._unmapped.append(
                Unmapped(
                    source=first_line,
                    reason=f"the imported expression does not parse as PQL: {exc.message}",
                    remedy=(
                        "Write this control by hand, or adjust the source so the "
                        "expression is one PQL can express. The rest of the import "
                        "is unaffected."
                    ),
                )
            )
            return
        self._controls.append(parsed)
        if caveat:
            self._caveats.append(Caveat(control=first_line, note=caveat))

    def unmapped(self, source: str, reason: str, *, remedy: str = "", dataset: str = "") -> None:
        self._unmapped.append(
            Unmapped(source=source, reason=reason, remedy=remedy, dataset=dataset)
        )

    def result(self) -> ImportResult:
        return ImportResult(
            controls=tuple(self._controls),
            unmapped=tuple(self._unmapped),
            caveats=tuple(self._caveats),
            source_format=self._format,
        )


def quote(value: Any) -> str:
    """A value as a PQL literal."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def because(origin: str) -> str:
    """The BECAUSE clause an imported control carries, quoting included.

    Every imported control says where it came from. Six months after a
    migration, "why does this exist" is answered by the control itself rather
    than by whoever remembers the old tool.

    Returns the whole clause rather than the text, because the text is a
    fragment of somebody else's file and will contain apostrophes — a SodaCL
    check is quoted in its own origin line. Handing back an unescaped string
    for a caller to interpolate is an invitation to emit PQL that does not
    parse, which is what happened the first time this existed.
    """
    return f"BECAUSE {quote(f'Imported from {origin}')}"
