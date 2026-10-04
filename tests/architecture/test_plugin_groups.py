"""Every advertised plugin group has a loader.

`plugins.entry_point_groups` listed six groups for four releases while one was
read. A group in that list is a promise to a third-party author — "advertise
your class here and Prama will load it" — and a group nothing reads is a
promise broken silently: the package installs, the entry point is valid, and
nothing happens.

So the list is checked against `prama.plugins.LOADERS`, both in the defaults
(the authority) and in the shipped `config/application.yaml` (what an operator
reads), and each loader is checked to read the group it is filed under.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from pathlib import Path

import yaml

from prama import plugins
from prama.core.config.defaults import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parents[2]


def unloaded(groups: Iterable[str]) -> list[str]:
    """The advertised groups nothing loads."""
    return sorted(set(groups) - set(plugins.LOADERS))


def test_every_default_group_has_a_loader() -> None:
    groups = DEFAULTS["plugins"]["entry_point_groups"]
    assert groups, "anti-vacuity: no groups were found"
    assert not unloaded(groups), (
        f"advertised in plugins.entry_point_groups and read by nothing: {unloaded(groups)}. "
        "Give the group a loader in prama.plugins.LOADERS, or stop advertising it."
    )


def test_every_shipped_yaml_group_has_a_loader() -> None:
    shipped = yaml.safe_load((REPO_ROOT / "config" / "application.yaml").read_text())
    groups = shipped["plugins"]["entry_point_groups"]
    assert groups, "anti-vacuity: no groups were found"
    assert not unloaded(groups), unloaded(groups)
    assert sorted(groups) == sorted(DEFAULTS["plugins"]["entry_point_groups"])


def test_every_loader_is_advertised() -> None:
    """A loader for a group nobody lists is a plugin nobody can turn on."""
    assert sorted(plugins.LOADERS) == sorted(DEFAULTS["plugins"]["entry_point_groups"])


def test_each_loader_reads_the_group_it_is_filed_under() -> None:
    """A loader filed under one group that discovers another is a broken promise
    that this table would otherwise hide."""
    from prama_kernel import plugins as validators

    from prama.alert import notify
    from prama.connect import registry as connectors
    from prama.monitor import registry as detectors

    owners = {
        "prama.connectors": (connectors.ENTRY_POINT_GROUP, "register_builtin"),
        "prama.notifiers": (notify.ENTRY_POINT_GROUP, "notify"),
        "prama.monitors": (detectors.ENTRY_POINT_GROUP, "monitor.registry"),
        "prama.validators": (validators.ENTRY_POINT_GROUP, "load_entry_points"),
    }
    assert sorted(owners) == sorted(plugins.LOADERS)
    for group, (declared, reached) in owners.items():
        assert declared == group
        assert reached in inspect.getsource(plugins.LOADERS[group]), group


def test_the_check_would_notice_a_group_with_no_loader() -> None:
    """The counterfactual: the two groups that were advertised and read by
    nothing, put back, are caught."""
    with_old = [*DEFAULTS["plugins"]["entry_point_groups"], "prama.backends", "prama.scorers"]
    assert unloaded(with_old) == ["prama.backends", "prama.scorers"]
