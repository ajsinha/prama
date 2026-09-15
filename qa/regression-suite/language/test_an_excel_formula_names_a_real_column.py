"""A formula that cannot name a column says so, instead of naming nothing.

QA round 4, `PQL-338` (P1) and `PQL-339`. Two gaps in the Excel surface's
tokenizer, both producing a `ColumnRef` that cannot resolve against any schema,
both silent at parse time.

`PQL-338`. The tokenizer's bare-name pattern is
`[A-Za-z_][A-Za-z0-9_.]*` — the dot is inside the character class — so
`positions.notional` became **one column literally called
`"positions.notional"`**, rather than `dataset="positions",
name="notional"`. Nothing resolves to that, and the formula parsed cleanly.

The PQL parser has always split a qualified name on the dot. Two surfaces onto
the same language disagreed about what `a.b` means, and only one of them was
right.

`PQL-339`. `[]` stripped to `""` and produced a `ColumnRef` with an empty name.

**The distinction the repair had to get right**, and the reason this is not a
one-line regex change: **brackets are the quoting mechanism.** `[total.gbp]`
must keep its dot, because quoting exists so a column genuinely called
`total.gbp` can be reached at all. A repair that split on the dot everywhere
would fix the bare case and make the quoted one unreachable — trading one
silently-wrong reference for another.

**What a careless version of this test would assert.**
`col.name.endswith("notional")` — true before and after, since
`"positions.notional"` ends with it too. The assertion has to be on both halves
of the split.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql import ast
from prama.pql.errors import PqlSyntaxError
from prama.pql.excel import ExcelParser


def column_of(formula: str) -> ast.ColumnRef:
    parsed = ExcelParser(formula).parse()
    left = parsed.left if hasattr(parsed, "left") else parsed
    assert isinstance(left, ast.ColumnRef), f"{formula!r} did not parse to a column"
    return left


# -- PQL-338: a qualified name is two things --------------------------------


def test_a_dotted_name_is_split_into_dataset_and_column() -> None:
    column = column_of("positions.notional > 0")
    assert (column.dataset, column.name) == ("positions", "notional"), (
        f"parsed as dataset={column.dataset!r} name={column.name!r}; a single "
        "column called 'positions.notional' resolves against nothing"
    )


def test_it_agrees_with_the_pql_parser() -> None:
    """Two surfaces onto one language cannot mean different things by `a.b`.

    Asserted against the other parser rather than against a remembered shape,
    so the two cannot drift apart later.
    """
    from prama.pql.parser import parse_control

    control = parse_control("CHECK positions.notional IS NOT NULL BECAUSE 'x'")
    from_pql = control.assertion.subject
    from_excel = column_of("positions.notional > 0")

    assert (from_excel.dataset, from_excel.name) == (from_pql.dataset, from_pql.name)


def test_an_unqualified_name_is_still_unqualified() -> None:
    """The counterfactual. Splitting unconditionally would invent a dataset."""
    column = column_of("notional > 0")
    assert (column.dataset, column.name) == ("", "notional")


def test_more_than_one_dot_is_refused() -> None:
    """`a.b.c` is not a reference this language has, and was not one before.

    The PQL parser takes one dot and then expects a column, so it refuses this
    too. Accepting it here would make the Excel surface strictly more
    permissive than the language it writes.
    """
    with pytest.raises(PqlSyntaxError) as caught:
        ExcelParser("a.b.c > 0").parse()
    assert "dot" in str(caught.value)


# -- PQL-339: an empty reference ---------------------------------------------


@pytest.mark.parametrize("formula", ["[] > 0", "[  ] > 0"], ids=["empty", "blank"])
def test_an_empty_bracket_is_refused(formula: str) -> None:
    with pytest.raises(PqlSyntaxError) as caught:
        ExcelParser(formula).parse()
    assert "column" in str(caught.value)


# -- the quoting the repair had to preserve ---------------------------------


def test_a_bracketed_name_keeps_its_dot() -> None:
    """Brackets quote, so what is inside them is a name verbatim.

    This is the case a dot-splitting repair breaks. A column genuinely called
    `total.gbp` is reachable only through the brackets, and if they split too it
    is reachable not at all — one silently wrong reference traded for another.
    """
    column = column_of("[total.gbp] > 0")
    assert (column.dataset, column.name) == ("", "total.gbp")


def test_a_bracketed_name_is_still_trimmed() -> None:
    """The behaviour that already worked, beside the one that did not."""
    assert column_of("[ notional ] > 0").name == "notional"
