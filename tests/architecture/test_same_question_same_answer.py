"""The Excel surface and the PQL parser read the same text the same way.

The "same question answered twice, differently" cluster was five findings deep
in QA round 4 with no guard (`Q-89`, `Q-104`, `Q-112`, …). `Q-112` pinned one
case, `a.b`. This guard pins the class. It generates expressions from the
syntax both surfaces share, renders each in both spellings (the string quotes
differ), and requires the two parsers to build the same tree.

Seeded, so a failure reproduces; wide, so it finds what a hand-picked list
would not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

import pytest

from prama.pql.excel import parse_formula
from prama.pql.parser import parse_control

COLUMNS = ("notional", "qty", "price", "positions.notional", "p.qty")
COMPARE = ("=", "<>", "<", ">", "<=", ">=")
ARITH = ("+", "-", "*", "/")


def _value(rng: random.Random, depth: int) -> tuple[str, str]:
    """A numeric or text operand, as (PQL text, Excel text)."""
    pick = rng.random()
    if depth <= 0 or pick < 0.35:
        column = rng.choice(COLUMNS)
        return column, column
    if pick < 0.5:
        number = rng.choice(("0", "1", "42", "2.5", "1000000", "0.001"))
        return number, number
    if pick < 0.6:
        word = rng.choice(("USD", "GBP", "it's"))
        return "'" + word.replace("'", "''") + "'", '"' + word + '"'
    if pick < 0.7:
        inner = _value(rng, depth - 1)
        return f"ROUND({inner[0]}, 2)", f"ROUND({inner[1]}, 2)"
    if pick < 0.8:
        inner = _value(rng, depth - 1)
        return f"({inner[0]})", f"({inner[1]})"
    left, right, op = _value(rng, depth - 1), _value(rng, depth - 1), rng.choice(ARITH)
    return f"{left[0]} {op} {right[0]}", f"{left[1]} {op} {right[1]}"


def _condition(rng: random.Random, depth: int) -> tuple[str, str]:
    """A boolean condition, as (PQL text, Excel text)."""
    if depth > 0 and rng.random() < 0.35:
        left, right = _condition(rng, depth - 1), _condition(rng, depth - 1)
        joiner = rng.choice(("AND", "OR"))
        if rng.random() < 0.3:
            return f"({left[0]}) {joiner} {right[0]}", f"({left[1]}) {joiner} {right[1]}"
        return f"{left[0]} {joiner} {right[0]}", f"{left[1]} {joiner} {right[1]}"
    left, right, op = _value(rng, depth), _value(rng, depth), rng.choice(COMPARE)
    return f"{left[0]} {op} {right[0]}", f"{left[1]} {op} {right[1]}"


CASES = [_condition(random.Random(seed), 3) for seed in range(400)]


@pytest.mark.parametrize(("pql", "excel"), CASES, ids=[str(i) for i in range(len(CASES))])
def test_both_surfaces_build_the_same_tree(pql: str, excel: str) -> None:
    from_pql = parse_control(f"CHECK positions SATISFIES {pql}").assertion.condition
    from_excel = parse_formula("=" + excel)
    assert from_excel == from_pql, f"\n  PQL:   {pql}\n  Excel: {excel}"


def test_the_guard_can_fail() -> None:
    """The counterfactual: two different expressions are told apart, so a
    green run is not the comparison being vacuous."""
    one = parse_control("CHECK positions SATISFIES qty > 1").assertion.condition
    assert parse_formula("=qty < 1") != one
