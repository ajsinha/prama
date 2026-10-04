"""The competitive landscape's content, loaded and checked.

Laid out after Maya's ``/about/competitive``. The comparison is by **category,
not vendor**: a row naming one product's features would be wrong by its next
release, and is not Prama's to state. ``docs/corpus/20-competitive-analysis.md`` is the
long form, vendor by vendor.

The rows themselves live in ``content/competitive.yaml``. They are copy about
products, and copy that names models and verdicts belongs in a data file, not
in a Python module the layering guard has to reason about. This module only
reads them and refuses anything malformed at import, so a bad rating fails the
build rather than rendering.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

YES, PARTIAL, NO = "Yes", "Partial", "No"
RATINGS = (YES, PARTIAL, NO)

CONTENT = Path(__file__).parent / "content" / "competitive.yaml"


@dataclasses.dataclass(frozen=True, slots=True)
class Category:
    """A family of products Prama is compared with."""

    key: str
    label: str
    short: str
    examples: str


@dataclasses.dataclass(frozen=True, slots=True)
class Row:
    """One capability: how each category stands, the problem, and how Prama does it."""

    id: str
    cap: str
    #: Keyed by `Category.key`, plus ``prama``.
    ratings: dict[str, str]
    problem: str
    #: Paragraphs. Trusted markup (``<code>``, ``<em>``) from the content file.
    how: tuple[str, ...]

    @property
    def prama(self) -> str:
        return self.ratings["prama"]


def load(path: Path = CONTENT) -> tuple[tuple[Category, ...], tuple[Row, ...]]:
    """The categories and rows, refused if any row does not rate every column."""
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    categories = tuple(Category(**c) for c in document["categories"])
    keys = {c.key for c in categories} | {"prama"}
    rows = []
    for raw in document["rows"]:
        row = Row(
            id=raw["id"],
            cap=raw["cap"],
            ratings=dict(raw["ratings"]),
            problem=raw["problem"],
            how=tuple(raw["how"]),
        )
        if set(row.ratings) != keys:
            raise ValueError(
                f"{path.name}: {row.id} rates {sorted(row.ratings)}, not {sorted(keys)}"
            )
        unknown = set(row.ratings.values()) - set(RATINGS)
        if unknown:
            raise ValueError(f"{path.name}: {row.id} has ratings {sorted(unknown)}")
        rows.append(row)
    return categories, tuple(rows)


CATEGORIES, ROWS = load()
SHINES = tuple(row for row in ROWS if row.prama == YES)
BEHIND = tuple(row for row in ROWS if row.prama != YES)
