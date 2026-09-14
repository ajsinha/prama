"""The parser's precedence and the renderer's binding cannot disagree.

QA rounds 3 and 4, `PQL-198` and `PQL-199`. `pql/parser.py::PRECEDENCE` decides
how a control's text is grouped when it is read; `pql/ast.py::BINDING` decides
where brackets go when it is written back. `BINDING`'s own comment states the
invariant:

    Must agree with the parser's PRECEDENCE, or the formatter emits text that
    means something else — the failure this table exists to prevent.

Nothing derived one from the other, so "must agree" was a hope. They disagreed
about `!=`: `PRECEDENCE` lists it, `BINDING` does not, and
`BINDING.get(op, ATOM_BINDING)` therefore scored it **100** — tighter than
multiplication — so a `!=` comparison would never be bracketed.

**Why those two cases were not simply weakened.** It is tempting to call them
over-strict: the parser normalises `!=` to `<>` before any AST node exists, so
no node can carry `!=` and the missing entry is unreachable today. But that
argument rests on a normalisation living in a third place, and the comment above
claims the invariant outright. A round-3 batch deliberately left these cases
alone rather than lower the bar to two hand-maintained lists that happen not to
have drifted far enough to hurt yet.

This is `CLAUDE.md`'s **derive, never restate** applied where the project's own
language lives: *"anything restated in a second place will drift, silently, in
the flattering direction"*. Two tables of operators, maintained by hand, is the
restatement.

**What a careless version of this test would assert.** That both tables are
non-empty, or that they have the same length. The first is vacuous; the second
is false by design, because `BINDING` carries the keyword predicates (`IN`,
`BETWEEN`, `IS NULL`) that never appear in `PRECEDENCE`, and `PRECEDENCE`
carries surface aliases that never reach an AST node. The asymmetry is real and
has to be named, not averaged away.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.pql import ast
from prama.pql.parser import PRECEDENCE


def test_every_operator_the_parser_reads_can_be_rendered() -> None:
    """The defect, stated as the thing that must be true.

    An operator the parser groups but the renderer cannot score is one the
    formatter will bracket wrongly — silently, because `.get(..., ATOM_BINDING)`
    has no failure mode.
    """
    aliases = getattr(ast, "OPERATOR_ALIASES", {})
    missing = [
        operator
        for level in PRECEDENCE
        for operator in level
        if operator not in ast.BINDING and aliases.get(operator) not in ast.BINDING
    ]
    assert not missing, (
        f"the parser accepts {missing} and the renderer cannot score them, so "
        "BINDING.get falls back to ATOM_BINDING and they bracket as if they bound "
        "tighter than multiplication"
    )


def test_the_two_tables_induce_the_same_ordering() -> None:
    """`PQL-198` itself: not merely present, but ordered the same way.

    Two tables can both contain every operator and still disagree about which
    binds tighter, which is the failure that actually changes a control's
    meaning.
    """
    aliases = getattr(ast, "OPERATOR_ALIASES", {})

    def canonical(operator: str) -> str:
        return aliases.get(operator, operator)

    # Tightest last in PRECEDENCE; higher is tighter in BINDING. So the index of
    # a level must order the same way as the binding of the operators in it.
    for earlier_index, earlier in enumerate(PRECEDENCE):
        for later_index, later in enumerate(PRECEDENCE):
            if earlier_index >= later_index:
                continue
            for loose in earlier:
                for tight in later:
                    loose_binding = ast.BINDING[canonical(loose)]
                    tight_binding = ast.BINDING[canonical(tight)]
                    assert loose_binding < tight_binding, (
                        f"the parser binds {tight!r} tighter than {loose!r}, and the "
                        f"renderer scores them {tight_binding} and {loose_binding}. "
                        "Reading and writing a control would group it differently."
                    )


def test_the_tables_are_derived_from_one_source() -> None:
    """Asserted on the wiring, because agreeing today is not the property.

    Both tests above pass on two hand-maintained lists that happen to match. The
    point of the repair is that they cannot stop matching, which is a statement
    about where the operators are written down — once — rather than about their
    current contents.
    """
    assert hasattr(ast, "PRECEDENCE_LEVELS"), (
        "there is no single source for the operator ordering; BINDING and "
        "PRECEDENCE are two hand-maintained lists again"
    )

    import inspect

    from prama.pql import parser

    parser_source = inspect.getsource(parser)
    head = parser_source.split("class Parser", 1)[0]
    assert "PRECEDENCE_LEVELS" in head, (
        "parser.PRECEDENCE no longer derives from the shared ordering, so the two "
        "tables can drift apart again"
    )


def test_an_alias_is_declared_rather_than_implied() -> None:
    """`!=` is the reason this was subtle, so it is named rather than inferred.

    The parser accepts `!=` and normalises it to `<>` before building a node.
    That is a real asymmetry between what is *read* and what is *rendered*, and
    leaving it implicit is what made `PQL-199` look like a missing entry rather
    than a deliberate one.
    """
    aliases = getattr(ast, "OPERATOR_ALIASES", {})
    assert aliases.get("!=") == "<>", (
        "the `!=` alias is not declared, so whether BINDING should carry an entry "
        "for it is a question answered by reading the parser rather than by the table"
    )
    assert "!=" not in ast.BINDING, (
        "BINDING has an entry for `!=`, which no AST node can carry — the parser "
        "normalises it away. An unreachable entry is a claim that it is reachable."
    )
