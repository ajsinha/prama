"""Domain packs: the parts of Prama that know about one industry.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

_installed = False


def install_shipped() -> None:
    """Install everything the shipped packs contribute to the core registries.

    Called from `prama.plugins.bootstrap`, which the CLI (`Application.run`)
    and `create_app` both call —
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

    # Third-party validators used to be loaded here, and were the only plugin
    # group anything loaded (QA findings CFG-036 and BE-179 were about that
    # loader having no caller at all). Every group now has its loader in
    # `prama.plugins.LOADERS`, called from the same bootstrap as this, so a
    # pack and a plugin are installed at the same moment in both processes.
    _installed = True


def _reset_for_tests() -> None:
    """Forget that installation happened. For tests of the bootstrap itself."""
    global _installed
    _installed = False


__all__ = ["install_shipped"]
