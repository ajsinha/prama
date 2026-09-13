"""Domain packs: the parts of Prama that know about one industry.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Iterable

_installed = False


def install_shipped(*, disabled_plugins: Iterable[str] = ()) -> None:
    """Install everything the shipped packs contribute to the core registries.

    Called from exactly two places — the CLI entry point and `create_app` —
    because the alternative is installing on import, and a function that exists
    because a module happened to be imported is one whose availability depends
    on import order. A control that compiles in one process and refuses in
    another is the worst kind of intermittent.

    This exists because there were previously *zero* such places. `install()`
    was written, tested, and called only from `tests/`, so
    `prama pack list` advertised eight cross-field checks that
    `prama control check` then refused as unknown functions — finding H1.
    Documentation and behaviour can drift; an advertisement and a refusal in
    the same CLI is not drift, it is two halves of one product disagreeing.

    Idempotent: safe to call from an entry point that may be re-entered, and
    from a test that has already run another.
    """
    global _installed
    if _installed:
        return
    from prama.packs.banking.calendars import install as install_calendars
    from prama.packs.banking.crossfield import install as install_functions

    install_functions()
    # The calendars too, and for the same reason. `prama.schedule.spec` refuses
    # `'06:30 TARGET2'` — an example its *own* remedy tells the user to copy —
    # because the registry is seeded with `always` and `weekdays` and nothing
    # in `src/` ever materialised the rest (finding H7). A remedy whose example
    # the code rejects is worse than no remedy: the reader follows it exactly
    # and is told they are wrong.
    from prama.core.calendars import default_calendars

    # Into the *default* registry, which is what `prama.schedule.spec.parse`
    # resolves through. `install()` defaults to a fresh registry and returns
    # it, so calling it without one materialises every calendar into an object
    # nobody holds — which is indistinguishable from not calling it at all.
    install_calendars(default_calendars(), replace=True)

    # Third-party validators, from the entry points a distribution advertises.
    #
    # `load_entry_points` had *no caller anywhere* — not in src, not in tests —
    # so the whole plugin mechanism was inert: `plugins.entry_point_groups` and
    # `plugins.disabled` were read by nothing, and the implementation-hash
    # freeze that stops a validator's code changing under a sealed plan could
    # never fire, because PLUGINS was always empty (QA findings CFG-036 and
    # BE-179).
    #
    # That is the same defect this function's own docstring was written about,
    # one layer along: `install()` was written, tested, and called only from
    # `tests/`. A mechanism nothing calls is indistinguishable from one that
    # does not exist, and both of them pass their unit tests.
    from prama.classify.plugins import load_entry_points
    from prama.classify.validators import REGISTRY

    load_entry_points(REGISTRY, disabled=disabled_plugins)
    _installed = True


def _reset_for_tests() -> None:
    """Forget that installation happened. For tests of the bootstrap itself."""
    global _installed
    _installed = False


__all__ = ["install_shipped"]
