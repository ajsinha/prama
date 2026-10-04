"""The one place third-party plugins are loaded: `bootstrap`.

``plugins.entry_point_groups`` advertised six groups and one was read. The
connector registry had a ``discover()`` nothing called, three groups had no
registry behind them at all, and notifiers had no interface — so a third-party
package that relied on any of them installed cleanly and did nothing. A
setting read by nothing is a promise the product does not keep.

Now every advertised group has a loader in `LOADERS`, and a group without an
extension seam is not advertised (`tests/architecture/test_plugin_groups.py`
fails the build otherwise):

====================  ================================================
``prama.validators``  semantic-type validators, purity-checked on admission
``prama.connectors``  source connectors, beside the shipped ones
``prama.notifiers``   alert channels (`prama.alert.notify.Notifier`)
``prama.monitors``    monitor detectors (`prama.monitor.detect.Detector`)
====================  ================================================

Two groups were removed rather than wired, because there is nothing for a
plugin to plug into: ``prama.backends`` (a compile dialect must also be named
in the PQL function catalogue's engines and pass the conformance corpus, so an
engine ships in-tree) and ``prama.scorers`` (scoring methods are closed enums,
changed in place, so that a score always names the arithmetic that made it).

`bootstrap` is called from exactly two places — `prama.api.app.create_app`
and `prama.cli.base.Application.run` — after the configuration is known, so
``plugins.disabled`` is honoured identically in the server and the CLI. Each
group is loaded once per process.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from prama.core.log import get_logger

_log = get_logger(__name__)

#: A loader takes ``plugins.disabled`` and returns how many plugins it loaded.
Loader = Callable[[Iterable[str]], int]


def _validators(disabled: Iterable[str]) -> int:
    from prama.classify.plugins import load_entry_points
    from prama.classify.validators import REGISTRY

    return len(load_entry_points(REGISTRY, disabled=disabled))


def _connectors(disabled: Iterable[str]) -> int:
    from prama.connect.builtin import register_builtin

    # The shipped ones first, so a distribution cannot take one of their keys.
    return register_builtin().discover(disabled=disabled)


def _notifiers(disabled: Iterable[str]) -> int:
    from prama.alert.notify import default_registry

    return default_registry().discover(disabled=disabled)


def _detectors(disabled: Iterable[str]) -> int:
    from prama.monitor.registry import default_registry

    return default_registry().discover(disabled=disabled)


#: Every entry-point group Prama reads, and what reads it.
LOADERS: dict[str, Loader] = {
    "prama.validators": _validators,
    "prama.connectors": _connectors,
    "prama.notifiers": _notifiers,
    "prama.monitors": _detectors,
}

_loaded: dict[str, int] = {}


def bootstrap(config: Any) -> dict[str, int]:
    """Install the shipped packs and load every configured plugin group, once.

    Returns group → plugins loaded by this process. A group named in
    ``plugins.entry_point_groups`` that Prama has no loader for is reported in
    the log, not silently ignored: somebody listed it expecting it to work.
    """
    from prama.packs import install_shipped

    disabled = [str(name) for name in config.get_list("plugins.disabled", [])]
    install_shipped()
    groups = [str(g) for g in config.get_list("plugins.entry_point_groups", list(LOADERS))]
    for group in groups:
        if group in _loaded:
            continue
        loader = LOADERS.get(group)
        if loader is None:
            _log.warning(
                "plugins.entry_point_groups names %r, which nothing in Prama reads; "
                "the groups with a loader are %s",
                group,
                ", ".join(sorted(LOADERS)),
            )
            continue
        _loaded[group] = loader(disabled)
    return dict(_loaded)


def _reset_for_tests() -> None:
    """Forget what was loaded. For tests of the bootstrap itself."""
    _loaded.clear()


__all__ = ["LOADERS", "Loader", "bootstrap"]
