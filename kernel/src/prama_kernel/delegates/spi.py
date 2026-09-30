"""The interface a DQ delegate implements: Python that measures, never decides.

A delegate is for the check PQL cannot say: a settlement cycle that depends on
a market calendar, a first-digit (Benford) test over a ledger, a proprietary
scoring rule. It is written by the bank, registered under a name, and named
from PQL::

    CHECK trades USING DELEGATE 'acme.settlement_cycle' (market = 'US')
      BELOW 0.1%
      SEVERITY critical

The contract, and why each part exists:

* **It measures; Prama judges.** `measure` returns counts: rows (or findings)
  scanned and how many violate, plus named observations. The control's
  threshold turns those into a verdict in the same shared code that judges
  every other control, so a delegate cannot decide pass or fail (CON-007 is the
  same rule for models).
* **It is a function of its rows and parameters.** No clock, no network, no
  filesystem, no model: checked by scanning its source *before* it is imported,
  and by running it twice on the same probes. A delegate that could read the
  clock could not be replayed, and evidence nobody can reproduce is an opinion.
* **Its rows are JSON values.** Dates arrive as ISO-8601 text, decimals as
  floats. Every engine returns different Python types for the same column, and
  a delegate that saw a `date` on DuckDB and a `str` on PostgreSQL would give
  two answers about one dataset.
* **It declares what it reads.** `requires` names the columns, and Prama fetches
  exactly those: the rest of the table never reaches the delegate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import math
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

#: What a delegate counts. `rows` supports a rate threshold (violations over
#: rows scanned); `findings` does not, because a rate of findings per row is not
#: a quantity anybody means.
UNITS = ("rows", "findings")


@dataclasses.dataclass(frozen=True, slots=True)
class Parameter:
    """One parameter a delegate accepts, with the type PQL must supply."""

    name: str
    kind: str = "text"  # text | number | boolean
    default: Any = None
    required: bool = False
    doc: str = ""

    def accepts(self, value: Any) -> bool:
        if self.kind == "boolean":
            return isinstance(value, bool)
        if self.kind == "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        return isinstance(value, str)


@dataclasses.dataclass(frozen=True, slots=True)
class Measurement:
    """What a delegate found. Numbers and a few example rows, nothing more."""

    scanned: int
    violating: int
    #: Named observations recorded with the evidence (`mad`, `chi_square`).
    #: Recorded, never judged: the threshold reads `violating`.
    observations: Mapping[str, float] = dataclasses.field(default_factory=dict)
    #: A few violating rows, as evidence. Bounded by the host.
    samples: tuple[Mapping[str, Any], ...] = ()
    #: One sentence a data owner reads beside the verdict.
    note: str = ""
    #: False when the rows could not establish anything (too few for a
    #: statistical test). The verdict is then INDETERMINATE, never a pass:
    #: a test that did not have enough data demonstrated nothing.
    established: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "violating": self.violating,
            "observations": dict(self.observations),
            "samples": [dict(s) for s in self.samples],
            "note": self.note,
            "established": self.established,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Measurement:
        return cls(
            scanned=payload.get("scanned", -1),
            violating=payload.get("violating", -1),
            observations=dict(payload.get("observations") or {}),
            samples=tuple(payload.get("samples") or ()),
            note=str(payload.get("note", "")),
            established=bool(payload.get("established", True)),
        )

    def problems(self, *, unit: str) -> list[str]:
        """Why this measurement cannot be judged, or an empty list."""
        found = []
        for label, value in (("scanned", self.scanned), ("violating", self.violating)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                found.append(f"{label} must be a non-negative whole number, not {value!r}")
        if not found and unit == "rows" and self.violating > self.scanned:
            found.append(f"{self.violating} violating rows out of {self.scanned} scanned")
        for name, observed in self.observations.items():
            if not name.isidentifier():
                found.append(f"the observation name {name!r} is not an identifier")
            elif not isinstance(observed, int | float) or not math.isfinite(float(observed)):
                found.append(f"the observation {name} is not a finite number")
        return found


class DqDelegate(abc.ABC):
    """A data quality check written in Python, registered under a name."""

    #: The name PQL uses: ``USING DELEGATE 'acme.settlement_cycle'``.
    name: ClassVar[str] = ""
    #: Pinned from PQL as ``'acme.settlement_cycle@2'``.
    version: ClassVar[str] = "1"
    #: The columns it reads. Empty means every column, which is allowed and
    #: discouraged: whatever is fetched is data that left its table.
    requires: ClassVar[tuple[str, ...]] = ()
    parameters: ClassVar[tuple[Parameter, ...]] = ()
    #: `rows` or `findings`; see UNITS.
    unit: ClassVar[str] = "rows"
    #: One sentence: what this checks, for `prama delegate list` and the console.
    summary: ClassVar[str] = ""

    @abc.abstractmethod
    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        """Count what is scanned and what violates. Must not raise on odd input:
        a blank, a null or an empty dataset is data, and a delegate that raises
        on one takes the control down instead of failing the row."""

    def resolve(self, given: Mapping[str, Any]) -> dict[str, Any]:
        """Parameters with defaults applied; unknown, missing or mistyped ones refused."""
        from prama_kernel.errors import ValidationError

        declared = {p.name: p for p in self.parameters}
        unknown = sorted(set(given) - set(declared))
        if unknown:
            raise ValidationError(
                f"{self.name} has no parameter {', '.join(unknown)}",
                remedy=f"It accepts: {', '.join(sorted(declared)) or 'no parameters'}.",
            )
        out: dict[str, Any] = {}
        for parameter in self.parameters:
            if parameter.name in given:
                value = given[parameter.name]
                if not parameter.accepts(value):
                    raise ValidationError(
                        f"{self.name}: {parameter.name} must be {parameter.kind}, not {value!r}",
                        remedy=parameter.doc or f"Give {parameter.name} as a {parameter.kind}.",
                    )
                out[parameter.name] = value
            elif parameter.required:
                raise ValidationError(
                    f"{self.name} needs the parameter {parameter.name}",
                    remedy=parameter.doc or f"Add {parameter.name} = … to the control.",
                )
            else:
                out[parameter.name] = parameter.default
        return out
