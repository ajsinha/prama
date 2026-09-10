"""Data diff: what changed between two versions of a dataset.

The question behind a migration, a parallel run, a refactor of a transformation,
and every "did my change do what I meant" — and the reason it belongs in a data
quality product rather than in a script is that the interesting answer is almost
never the row count.

Four rules, each of which the obvious implementation breaks:

* **A schema change dominates a row change.** Comparing rows across two
  different column sets produces a diff where everything changed, and the one
  fact that explains it — a column was renamed — is buried under ten thousand
  rows. Schema differences are reported first and separately, and a row diff
  taken across a changed schema says so.
* **A changed row names the columns that changed.** "4,120 rows differ" is a
  number nobody can act on; "4,120 rows differ, all of them only in
  ``settlement_date``" is a finding with an owner.
* **Without a key there is no diff.** Two bags of rows can be compared for
  membership and nothing more — no row "changed", because nothing says which row
  is which. That is a real answer and it is reported as one, rather than as a
  positional comparison that reports every row as changed the moment an ordering
  differs.
* **A capped diff says it was capped.** Detail is bounded because a million
  differing rows is not a report, and a bound presented as a total is the most
  dangerous number here.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

#: How many differing rows are described in detail. Beyond this the counts stay
#: exact and the examples stop, which the report states.
DETAIL_LIMIT = 100


def _key_of(row: Mapping[str, Any], key: Sequence[str]) -> tuple[Any, ...]:
    return tuple(row.get(name) for name in key)


@dataclasses.dataclass(frozen=True, slots=True)
class ColumnChange:
    """One column's before and after, for one row."""

    column: str
    before: Any
    after: Any

    def render(self) -> str:
        return f"{self.column}: {self.before!r} -> {self.after!r}"


@dataclasses.dataclass(frozen=True, slots=True)
class RowChange:
    """A row present on both sides whose values differ."""

    key: tuple[Any, ...]
    changes: tuple[ColumnChange, ...]

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(change.column for change in self.changes)

    def render(self) -> str:
        return f"{self.key}: " + "; ".join(change.render() for change in self.changes)


@dataclasses.dataclass(frozen=True, slots=True)
class SchemaDiff:
    """Columns that appeared, disappeared, or changed type."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    #: ``column -> (before, after)`` where a type was declared on both sides.
    retyped: tuple[tuple[str, str, str], ...] = ()

    @property
    def is_identical(self) -> bool:
        return not (self.added or self.removed or self.retyped)

    def describe(self) -> str:
        if self.is_identical:
            return "the two sides have the same columns"
        parts = []
        if self.removed:
            # First, because a removed column is the difference most likely to
            # be a mistake and the one that makes every row look changed.
            parts.append(f"{len(self.removed)} column(s) gone: {', '.join(self.removed)}")
        if self.added:
            parts.append(f"{len(self.added)} added: {', '.join(self.added)}")
        if self.retyped:
            parts.append(
                f"{len(self.retyped)} retyped: "
                + ", ".join(f"{c} {a}->{b}" for c, a, b in self.retyped)
            )
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "retyped": [list(item) for item in self.retyped],
            "identical": self.is_identical,
            "message": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Diff:
    """What changed between two versions of a dataset."""

    schema: SchemaDiff
    #: Empty when no key was given, in which case ``comparable`` is False.
    key: tuple[str, ...] = ()
    added: int = 0
    removed: int = 0
    changed: int = 0
    unchanged: int = 0
    #: Bounded examples. ``truncated`` says whether there were more.
    added_examples: tuple[tuple[Any, ...], ...] = ()
    removed_examples: tuple[tuple[Any, ...], ...] = ()
    changed_examples: tuple[RowChange, ...] = ()
    truncated: bool = False
    #: Rows that share a key with another row on their own side. A key that is
    #: not unique is not a key, and a diff computed on one is arithmetic on the
    #: wrong pairs.
    duplicate_keys_left: int = 0
    duplicate_keys_right: int = 0

    @property
    def comparable(self) -> bool:
        """Whether rows could be matched at all.

        False without a key. Two bags of rows can be compared for membership
        and nothing more — no row "changed", because nothing says which row is
        which.
        """
        return bool(self.key)

    @property
    def is_identical(self) -> bool:
        return self.schema.is_identical and not self.added and not self.removed and not self.changed

    @property
    def columns_that_changed(self) -> tuple[str, ...]:
        """Every column appearing in a change, most common first.

        The number that turns a diff into an action: four thousand rows
        differing in one column is one bug, and in forty columns is a different
        conversation.
        """
        counts: dict[str, int] = {}
        for change in self.changed_examples:
            for column in change.columns:
                counts[column] = counts.get(column, 0) + 1
        return tuple(sorted(counts, key=lambda c: (-counts[c], c)))

    def describe(self) -> str:
        if not self.schema.is_identical:
            # First and on its own line. A row diff taken across a changed
            # schema is a diff where everything changed, and the one fact that
            # explains it would otherwise be buried.
            head = f"the schema differs — {self.schema.describe()}. "
        else:
            head = ""

        if not self.comparable:
            return (
                head + f"No key was given, so rows cannot be matched: {self.added} row(s) "
                f"appear only on the right and {self.removed} only on the left. "
                "Nothing here says a row *changed*, because nothing says which "
                "row is which."
            )

        if self.is_identical:
            return head + f"identical: {self.unchanged} row(s), none added, removed or changed"

        parts = [
            f"{self.added} added",
            f"{self.removed} removed",
            f"{self.changed} changed",
            f"{self.unchanged} unchanged",
        ]
        detail = head + ", ".join(parts)
        if self.changed and self.columns_that_changed:
            detail += f"; changes are in {', '.join(self.columns_that_changed[:5])}"
        if self.duplicate_keys_left or self.duplicate_keys_right:
            detail += (
                f"; {self.duplicate_keys_left + self.duplicate_keys_right} row(s) share "
                "a key with another on their own side, so this comparison is between "
                "the wrong pairs"
            )
        if self.truncated:
            detail += f"; examples are capped at {DETAIL_LIMIT} and the counts are not"
        return detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema.to_dict(),
            "key": list(self.key),
            "comparable": self.comparable,
            "identical": self.is_identical,
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "unchanged": self.unchanged,
            "columns_that_changed": list(self.columns_that_changed),
            "duplicate_keys_left": self.duplicate_keys_left,
            "duplicate_keys_right": self.duplicate_keys_right,
            "truncated": self.truncated,
            "added_examples": [list(k) for k in self.added_examples],
            "removed_examples": [list(k) for k in self.removed_examples],
            "changed_examples": [c.render() for c in self.changed_examples],
            "message": self.describe(),
        }


def compare_schema(
    left: Mapping[str, str] | Iterable[str],
    right: Mapping[str, str] | Iterable[str],
) -> SchemaDiff:
    """Two column sets, with types where both sides declare them."""
    left_types = dict(left) if isinstance(left, Mapping) else dict.fromkeys(left, "")
    right_types = dict(right) if isinstance(right, Mapping) else dict.fromkeys(right, "")

    retyped = tuple(
        (name, left_types[name], right_types[name])
        for name in sorted(set(left_types) & set(right_types))
        # Only where both sides said something. A type declared on one side and
        # not the other is not a change of type, it is a change of how much is
        # known — and reporting it as a retype sends somebody looking for a
        # migration that never happened.
        if left_types[name] and right_types[name] and left_types[name] != right_types[name]
    )
    return SchemaDiff(
        added=tuple(sorted(set(right_types) - set(left_types))),
        removed=tuple(sorted(set(left_types) - set(right_types))),
        retyped=retyped,
    )


def compare(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    *,
    key: Sequence[str] = (),
    ignore: Sequence[str] = (),
    limit: int = DETAIL_LIMIT,
) -> Diff:
    """What changed between two row sets.

    ``key`` identifies a row on both sides. Without it this degrades honestly to
    a membership comparison rather than pretending position is identity.

    ``ignore`` drops columns from the value comparison — a load timestamp
    differs on every row of every reload, and a diff dominated by it hides
    everything else.
    """
    schema = compare_schema(
        {column for row in left for column in row},
        {column for row in right for column in row},
    )
    ignored = set(ignore)

    if not key:
        left_rows = {_freeze(row, ignored) for row in left}
        right_rows = {_freeze(row, ignored) for row in right}
        return Diff(
            schema=schema,
            added=len(right_rows - left_rows),
            removed=len(left_rows - right_rows),
            unchanged=len(left_rows & right_rows),
        )

    key = tuple(key)
    left_by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    right_by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    duplicates_left = duplicates_right = 0

    for row in left:
        identity = _key_of(row, key)
        if identity in left_by_key:
            duplicates_left += 1
        left_by_key[identity] = row
    for row in right:
        identity = _key_of(row, key)
        if identity in right_by_key:
            duplicates_right += 1
        right_by_key[identity] = row

    added_keys = sorted(set(right_by_key) - set(left_by_key), key=_sortable)
    removed_keys = sorted(set(left_by_key) - set(right_by_key), key=_sortable)
    shared = sorted(set(left_by_key) & set(right_by_key), key=_sortable)

    # Only columns both sides have. Comparing a column that exists on one side
    # reports every shared row as changed, which is the schema difference said
    # a second time and much less clearly.
    comparable_columns = sorted(
        ({c for row in left for c in row} & {c for row in right for c in row}) - ignored - set(key)
    )

    changes: list[RowChange] = []
    changed = unchanged = 0
    for identity in shared:
        before, after = left_by_key[identity], right_by_key[identity]
        differing = tuple(
            ColumnChange(column=column, before=before.get(column), after=after.get(column))
            for column in comparable_columns
            if before.get(column) != after.get(column)
        )
        if differing:
            changed += 1
            if len(changes) < limit:
                changes.append(RowChange(key=identity, changes=differing))
        else:
            unchanged += 1

    truncated = changed > len(changes) or len(added_keys) > limit or len(removed_keys) > limit

    return Diff(
        schema=schema,
        key=key,
        added=len(added_keys),
        removed=len(removed_keys),
        changed=changed,
        unchanged=unchanged,
        added_examples=tuple(added_keys[:limit]),
        removed_examples=tuple(removed_keys[:limit]),
        changed_examples=tuple(changes),
        truncated=truncated,
        duplicate_keys_left=duplicates_left,
        duplicate_keys_right=duplicates_right,
    )


def _freeze(row: Mapping[str, Any], ignored: set[str]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted((k, v) for k, v in row.items() if k not in ignored))


def _sortable(identity: tuple[Any, ...]) -> tuple[str, ...]:
    """A sort key that survives mixed types and ``None``.

    Sorting raw tuples raises the moment a key column holds both an integer and
    a string, which is exactly what a mid-migration dataset looks like.
    """
    return tuple("" if part is None else str(part) for part in identity)


__all__ = [
    "DETAIL_LIMIT",
    "ColumnChange",
    "Diff",
    "RowChange",
    "SchemaDiff",
    "compare",
    "compare_schema",
]
