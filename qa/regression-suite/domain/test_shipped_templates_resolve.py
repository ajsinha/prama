"""Every shipped template must name a function the pack registers.

QA round 2, `PCK-184` and `PCK-185`. The EMIR notional-sign template called
`NOTIONAL_SIGN_MATCHES_SIDE(notional, side)`. The pack registers
`SIGN_MATCHES_SIDE`, declared `(TEXT, NUMBER)` — so the template was wrong in
its name *and* in its argument order, and could never resolve.

This is finding `H1` one wave later, in the templates instead of the CLI:
`prama pack list` advertised eight cross-field checks that `prama control check`
then refused as unknown. An advertisement and a refusal in the same product are
not drift; they are two halves of one thing disagreeing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re

import pytest

from prama.packs import install_shipped

#: Placeholders a template leaves for an estate to fill.
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@pytest.fixture(scope="module", autouse=True)
def _installed() -> None:
    install_shipped()


def _templates():
    from prama.packs.banking.regimes import REGIME_OBLIGATIONS

    for obligation in REGIME_OBLIGATIONS:
        yield from getattr(obligation, "templates", ())


def test_there_are_templates_to_check() -> None:
    """Anti-vacuity. A generator that stopped yielding would pass everything."""
    assert len(list(_templates())) >= 10


#: Templates known to be unresolvable, with the reason. Each is a strict
#: xfail below rather than an exclusion, so fixing one breaks this file and
#: forces the entry out.
KNOWN_BROKEN: dict[str, str] = {
    "gdpr-retention-floor": (
        "names DATE_SUB, which no pack registers. The obvious repair — "
        "IS FRESH WITHIN {retention_days} DAYS — would move it from 'cannot "
        "compile' to 'can never produce a verdict', because freshness has no "
        "execution strategy at all (QA findings PQL-083 and Q-64)"
    ),
}

#: Placeholders whose value is not a column name. Substituting `col` for a
#: duration produces `IS FRESH WITHIN col`, which is a syntax error about the
#: test rather than about the template.
SUBSTITUTIONS: dict[str, str] = {
    "dataset": "trades",
    "window": "4 HOURS",
    "retention_days": "2555",
}


def _fill(pql: str) -> str:
    filled = PLACEHOLDER.sub(lambda m: SUBSTITUTIONS.get(m.group(1), "col"), pql)
    return filled if "OWNER" in filled else filled + " OWNER 'ops'"


def test_every_function_a_template_names_is_registered() -> None:
    """Derived from the catalogue rather than from a list somebody maintains.

    A list would rot in exactly the way the template did.
    """
    from prama.pql.library import FUNCTIONS

    known = {name.upper() for name in FUNCTIONS.names()}
    missing: list[tuple[str, str]] = []
    for template in _templates():
        if template.identity in KNOWN_BROKEN:
            continue
        for call in re.findall(r"\b([A-Z][A-Z0-9_]{2,})\s*\(", template.pql):
            if call in known or call in {"BETWEEN", "IN", "VALUES", "CHECK"}:
                continue
            missing.append((template.identity, call))
    assert not missing, f"templates naming functions the pack does not register: {missing}"


def test_every_template_compiles_once_its_placeholders_are_filled() -> None:
    """Compiled, not merely resolved — that is where the truth is.

    `resolved()` does not check that a function exists; the SQL compiler does,
    and `gdpr-retention-floor` lowers to a perfectly good plan and then refuses
    with "there is no function called DATE_SUB". A template that resolves and
    cannot compile is a control somebody would bind to an estate before
    discovering it can never run.

    It also catches the other half: a template can name only registered
    functions and still pass them in the wrong order, which is what
    `emir-notional-sign` did against a signature declared (TEXT, NUMBER).
    """
    from prama.backend.sql import compile_for
    from prama.ir.resolve import resolved
    from prama.pql.parser import parse

    failures: list[tuple[str, str]] = []
    for template in _templates():
        if template.identity in KNOWN_BROKEN:
            continue
        try:
            compile_for(resolved(parse(_fill(template.pql)).all_controls[0]), "postgresql")
        except Exception as exc:
            failures.append((template.identity, f"{type(exc).__name__}: {exc}"[:140]))
    assert not failures, failures


@pytest.mark.parametrize("identity", sorted(KNOWN_BROKEN))
@pytest.mark.xfail(strict=True, reason="QA-2 Q-64: DATE_SUB is registered by no pack")
def test_the_known_broken_templates_are_still_broken(identity: str) -> None:
    """Pinned, not excluded.

    A template nobody can run is a defect whether or not anybody is working on
    it, and an exclusion list quietly becomes the place defects go to be
    forgotten. Strict xfail means the day freshness is implemented and this
    template is repaired, this test starts failing and the entry has to come
    out — which is the only way a known-broken list stays true.
    """
    from prama.backend.sql import compile_for
    from prama.ir.resolve import resolved
    from prama.pql.parser import parse

    template = next(t for t in _templates() if t.identity == identity)
    compile_for(resolved(parse(_fill(template.pql)).all_controls[0]), "postgresql")
