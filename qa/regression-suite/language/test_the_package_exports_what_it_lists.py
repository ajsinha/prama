"""`__all__` is a promise, and it was naming five things that did not exist.

QA round 4, `PQL-402` and `PQL-403`. `prama/pql/__init__.py` listed
`Attribute`, `AttributeCatalogue`, `Drift`, `Expander` and `Expansion` in
`__all__` and imported none of them, so `from prama.pql import *` raised
`AttributeError` and `getattr(prama.pql, "Expander")` failed.

The state was neither "exported" nor "not listed" but both at once, which is
why nothing caught it: every ordinary import of the package worked, and only the
two forms nobody uses in this codebase — a star import and a `getattr` over
`__all__` — could see it.

All five live in `prama/pql/expand.py`, a sibling module. So this was not a
question of what should be public: the names were chosen, written into the
contract, and the import line was never added.

**What a careless version of this test would assert.** That one of the five
imports. The whole failure mode is a list drifting away from the module one
entry at a time, so the test has to be over the list, derived from `__all__`
itself rather than from a copy of it here — a hand-written list of expected
names is the same defect in a new place.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib
import pkgutil

import prama


def public_packages() -> list[str]:
    """Every `prama.*` module, found rather than listed."""
    found: list[str] = []
    for module in pkgutil.walk_packages(prama.__path__, prefix="prama."):
        if ".ui." in module.name or module.name.endswith(".ui"):
            continue
        found.append(module.name)
    return found


def test_every_name_prama_pql_advertises_resolves() -> None:
    import prama.pql

    missing = [name for name in prama.pql.__all__ if not hasattr(prama.pql, name)]
    assert not missing, (
        f"prama.pql.__all__ names {missing}, which the module does not import. "
        "`from prama.pql import *` raises AttributeError on the first of them."
    )


def test_the_star_import_that_used_to_fail() -> None:
    """The form the defect was originally found through, kept as the record."""
    namespace: dict[str, object] = {}
    exec("from prama.pql import *", namespace)

    for name in ("Attribute", "AttributeCatalogue", "Drift", "Expander", "Expansion"):
        assert name in namespace, f"{name} is advertised and did not arrive"


def test_prama_pql_still_exports_what_it_always_did() -> None:
    """The counterfactual.

    Emptying `__all__` would satisfy both tests above and silently remove the
    package's public surface.
    """
    import prama.pql

    for name in ("parse", "parse_control", "Control", "Linter", "tokenise"):
        assert hasattr(prama.pql, name), f"{name} is no longer exported"
    assert len(prama.pql.__all__) >= 38


def test_no_module_advertises_a_name_it_does_not_have() -> None:
    """The same check over every package, because one was never the point.

    `prama.pql` is where it was found. A list that can drift in one module can
    drift in any of them, and the cost of asking all of them is one import each.

    One test rather than one per module, deliberately. Parametrising over ~350
    modules gives prettier isolation and adds 350 entries to a suite count the
    README publishes — a lot of noise for a single invariant. The assertion
    message names every offender, which is the information the isolation would
    have given.
    """
    offenders: dict[str, list[str]] = {}
    for module_name in public_packages():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        declared = getattr(module, "__all__", ())
        missing = [name for name in declared if not hasattr(module, name)]
        if missing:
            offenders[module_name] = missing

    assert not offenders, f"modules advertising names they do not define: {offenders}"
