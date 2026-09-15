"""`HAS LENGTH BETWEEN` is checked against what a length is.

QA round 4, `PQL-092` (P1) and `BE-160`. `TypeChecker._check_predicate` exempts
`in_codelist`, `is_valid`, `has_format` and `matches` from the
subject-versus-argument type comparison — *"the argument names a thing, not a
value"* — and did not exempt `has_length_between`.

So `CHECK t.isin HAS LENGTH BETWEEN 12 AND 12`, about as ordinary a control as
this language has, was reported as comparing text with a number. **Twice**, once
per bound, on every text column, always.

**The defect is not that it was noisy. It is that it was inverted.** Exempting
the comparison and stopping there would have been the obvious fix and would have
left the other half in place: `CHECK t.notional HAS LENGTH BETWEEN 1 AND 3` —
the character length of a *number* — reported nothing at all, before and after.
The check rejected the correct control and accepted the incorrect one, so a fix
aimed only at the false positive would have made the checker quieter and no more
correct.

`BE-160` is the same defect reached from the other side: type-checking the
corpus generator's own output produced the identical message about a different
column. Two catalogue cases, one cause.

**What a careless version of this test would assert.** `len(findings) < 2` for
the text case — which passes if only one of the two bound comparisons is
exempted by mistake. Or the text case alone, which is the half that would have
been fixed by the obvious repair.

**Found while writing this test.** The first fixture declared columns as
`text` and `number`. `text` is a real SQL type name and resolves; `number` is
not one and resolved to `unknown`, which the checker exempts from everything —
so the number-column case reported zero findings and looked like the defect was
already fixed. `TYPE_FAMILIES` holds actual SQL type names (`varchar`,
`numeric`, `int`…). A fixture that silently types every column `unknown` turns a
type-checking test into one that checks nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.pql.parser import parse_control
from prama.pql.types import Catalogue, Column, DatasetSchema, TypeChecker

SCHEMA = Catalogue(
    datasets={
        "t": DatasetSchema(
            name="t",
            # Real SQL type names: see the module docstring. `number` is not one.
            columns=(Column("isin", "varchar"), Column("notional", "numeric")),
        )
    }
)


def findings(pql: str) -> list:
    return TypeChecker(SCHEMA).check(parse_control(pql))


def test_a_length_check_on_a_text_column_is_clean() -> None:
    """`PQL-092`. Two spurious findings on the most ordinary control there is."""
    found = findings("CHECK t.isin HAS LENGTH BETWEEN 12 AND 12 BECAUSE 'x'")
    assert found == [], f"a length check on a text column reported {[f.message for f in found]}"


def test_a_length_check_on_a_number_is_refused() -> None:
    """The inverted half, and the reason the obvious fix was not enough.

    Exempting the comparison alone would leave this reporting nothing — as it
    did before — and the checker would be quieter without being more correct.
    """
    found = findings("CHECK t.notional HAS LENGTH BETWEEN 1 AND 3 BECAUSE 'x'")
    assert found, "the character length of a number was accepted without comment"
    assert "length" in found[0].message
    assert found[0].remedy, "refused without saying what to write instead"


@pytest.mark.parametrize("bounds", ["'a' AND 'b'", "'12' AND 12"], ids=["both-text", "one-text"])
def test_a_length_bound_that_is_not_a_number_is_refused(bounds: str) -> None:
    """A character count is a number whatever the column holds.

    The exemption says "do not compare the bounds with the *subject*". It does
    not say the bounds are unconstrained, and an exemption that turned into "no
    check at all" is how the number-column case came to pass silently.
    """
    found = findings(f"CHECK t.isin HAS LENGTH BETWEEN {bounds} BECAUSE 'x'")
    assert found, f"HAS LENGTH BETWEEN {bounds} was accepted"
    # "a length bound must be a number", not the old subject-comparison message
    # — which also contained the word "number" and let the `one-text` case pass
    # against the unrepaired code, for entirely the wrong reason.
    assert any("length bound" in f.message for f in found), (
        f"the finding is not about the bound: {[f.message for f in found]}"
    )


def test_the_other_exemptions_are_untouched() -> None:
    """The controls. The repair edits a list four other operators depend on."""
    for pql in (
        "CHECK t.isin MATCHES /^[A-Z]{2}/ BECAUSE 'x'",
        "CHECK t.isin IS VALID ISIN BECAUSE 'x'",
        "CHECK t.isin IS NOT NULL BECAUSE 'x'",
        "CHECK t.notional BETWEEN 1 AND 3 BECAUSE 'x'",
    ):
        assert findings(pql) == [], f"{pql!r} now reports a finding"


def test_a_genuine_type_error_is_still_found() -> None:
    """The counterfactual that matters most.

    Every assertion above is about the checker saying *less*. Without this, they
    are all satisfied by a checker that reports nothing at all.
    """
    found = findings("CHECK t.notional > 'not a number' BECAUSE 'x'")
    assert found, "comparing a numeric column with text is no longer a type error"
