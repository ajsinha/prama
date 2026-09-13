"""`plugins.disabled` switches a validator off in the CLI, as it does in the server.

QA round 3, `Q-63`. `create_app` read `plugins.disabled` and passed it to
`install_shipped`; `prama.cli.main` could not, because it installed packs at the
entry point — *before* argparse had run, so `--config` was unknown. Reading a
configuration file the caller was about to override would have been worse than
reading none, so the setting was simply not honoured, and the asymmetry was
documented rather than removed:

    a validator switched off in configuration stays off in the server and loads
    in the CLI

That is the shape this project's doctrine calls out by name — *derive, never
restate* — with the restatement being an operator's expectation. Somebody
disables a validator, sees the server honour it, and reasonably assumes the tool
they run in CI honours it too.

The repair is a move, not a mechanism. `install_shipped` now runs inside
`Application.run`, after the `CommandContext` exists and therefore after
`--config` has been resolved, and still before any command executes — which is
the only ordering requirement it ever had. Nothing in parser construction reads
the registry, so building the parser first costs nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import inspect
from pathlib import Path


def test_the_cli_honours_plugins_disabled_the_way_create_app_does() -> None:
    """Both entry points pass the setting through, from the same key.

    Asserted on the source of both call sites rather than by loading a real
    third-party distribution: installing a plugin package into the test
    environment to prove a config key is read would make this test depend on
    packaging rather than on the behaviour, and it is the *wiring* that was
    missing.
    """
    from prama.api import app as api_app
    from prama.cli import base as cli_base

    api_source = inspect.getsource(api_app)
    cli_source = inspect.getsource(cli_base.Application.run)

    assert 'install_shipped(disabled_plugins=config.get_list("plugins.disabled"' in api_source, (
        "create_app no longer passes plugins.disabled; this test is measuring "
        "the wrong thing and should be rewritten before being trusted"
    )
    assert "install_shipped(" in cli_source, (
        "Application.run no longer installs packs. If installation moved again, "
        "it must still happen somewhere the effective configuration is known — "
        "moving it back to the entry point reintroduces Q-63."
    )
    assert 'plugins.disabled' in cli_source, (
        "Application.run installs packs without passing plugins.disabled, so a "
        "validator switched off in configuration still loads in the CLI while "
        "being off in the server"
    )


def test_packs_are_not_installed_before_the_configuration_is_known() -> None:
    """The entry point must not install; that is what made the setting unreadable.

    Stated as its own assertion because the defect is a matter of *ordering*,
    and an ordering mistake is invisible in any test that only checks the end
    state: install at the entry point and install in `run` both leave the
    registry populated.
    """
    main_source = Path(
        inspect.getsourcefile(__import__("prama.cli.main", fromlist=["main"]))  # type: ignore[arg-type]
    ).read_text()

    body = main_source.split("def main(", 1)[1]
    active = [
        line
        for line in body.splitlines()
        if "install_shipped(" in line and not line.strip().startswith("#")
    ]
    assert not active, (
        "prama.cli.main installs packs before argparse has run, so --config is "
        f"unknown and plugins.disabled cannot be read: {active}"
    )


def test_a_disabled_validator_is_absent_from_the_registry() -> None:
    """The behaviour itself, driven through `install_shipped`'s own parameter.

    `load_entry_points` is what filters, and it is reached only through
    `install_shipped`. Driving that function directly with and without the
    disabled list proves the parameter is honoured; the two tests above prove
    the CLI actually supplies it.
    """
    from prama.classify.plugins import load_entry_points
    from prama.classify.validators import REGISTRY

    loaded = load_entry_points(REGISTRY, disabled=())
    names = {provenance.name for provenance in loaded} if loaded else set()
    if not names:
        # No third-party validator is installed in this environment, so there is
        # nothing to switch off. Said out loud rather than passing quietly: a
        # green result here would otherwise mean "the filter works" when it
        # means "there was nothing to filter".
        import pytest

        pytest.skip("no third-party validators are installed; nothing to disable")

    one = sorted(names)[0]
    remaining = load_entry_points(REGISTRY, disabled=(one,))
    assert one not in {provenance.name for provenance in remaining}
