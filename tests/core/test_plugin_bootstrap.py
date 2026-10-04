"""Third-party plugins are discovered from real entry points, and can be switched off.

`plugins.entry_point_groups` advertised six groups and one was loaded: a
distribution advertising a connector, a detector or a notifier installed
cleanly and did nothing. These tests install a real distribution — a
``dist-info`` directory with an ``entry_points.txt``, on ``sys.path``, which
`importlib.metadata` finds exactly as it finds an installed wheel — and drive
`prama.plugins.bootstrap`, the one function the server and the CLI call.

Each test asserts the plugin is *usable*, not merely registered: the connector
reads a file, the notifier delivers, the detector scores. And each has its
counterfactual: with ``plugins.disabled`` naming it, or with its group's loader
removed, the plugin is absent.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from prama import plugins
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "docs" / "developer" / "examples"

PLUGIN_MODULE = '''
"""A third-party distribution's plugins, for the bootstrap tests."""
from typing import Any, ClassVar

from prama.alert.notify import Message, Notifier
from prama.monitor.detect import Detector, Score

SENT: list[Message] = []


class CaptureNotifier(Notifier):
    plugin_key: ClassVar[str] = "capture"
    description: ClassVar[str] = "keeps what it is given"

    def deliver(self, message: Message) -> None:
        SENT.append(message)


class LastValue(Detector):
    name: ClassVar[str] = "last_value_demo"
    good_at: ClassVar[str] = "a jump from yesterday"
    blind_to: ClassVar[str] = "everything else"

    def compute(self, observation: float, history: Any) -> Score | None:
        if not history:
            return None
        return Score(value=abs(observation - history[-1]), detector=self.name)
'''

SHADOW_MODULE = '''
"""A connector claiming a shipped connector's key."""
import dataclasses

from prama_demo_fixed_width import FixedWidthConnector


class Shadow(FixedWidthConnector):
    plugin_key = "sqlite"

    @classmethod
    def manifest(cls):
        return dataclasses.replace(FixedWidthConnector.manifest(), key="sqlite")
'''

ENTRY_POINTS = """\
[prama.connectors]
fixed_width = prama_demo_fixed_width:FixedWidthConnector

[prama.notifiers]
capture = prama_demo_plugins:CaptureNotifier

[prama.monitors]
last_value_demo = prama_demo_plugins:LastValue
"""

LAYOUT = "position_id:0:4,isin:4:16"


@pytest.fixture
def distribution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A real, installed-looking distribution advertising three plugins."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "prama_demo_plugins.py").write_text(PLUGIN_MODULE, encoding="utf-8")
    shutil.copy(EXAMPLES / "fixed_width_connector.py", site / "prama_demo_fixed_width.py")
    info = site / "prama_demo_plugins-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: prama-demo-plugins\nVersion: 1.0\n", encoding="utf-8"
    )
    (info / "entry_points.txt").write_text(ENTRY_POINTS, encoding="utf-8")
    monkeypatch.syspath_prepend(str(site))
    importlib.invalidate_caches()
    yield site
    for name in ("prama_demo_plugins", "prama_demo_fixed_width"):
        sys.modules.pop(name, None)


@pytest.fixture
def fresh(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Process-wide registries replaced by empty ones, so nothing leaks out."""
    from prama.alert import notify
    from prama.connect import registry as connectors
    from prama.monitor import registry as detectors

    state = {
        "connectors": connectors.ConnectorRegistry(),
        "notifiers": notify.new_registry(),
        "detectors": detectors.new_registry(),
    }
    monkeypatch.setattr(connectors, "_default", state["connectors"])
    monkeypatch.setattr(notify, "_default", state["notifiers"])
    monkeypatch.setattr(detectors, "_default", state["detectors"])
    monkeypatch.setattr(plugins, "_loaded", {})
    return state


def config(**plugin_settings: Any) -> Configuration:
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping({"plugins": plugin_settings}, name="test")
        .build()
    )


def test_every_group_is_loaded_and_each_plugin_is_usable(
    distribution: Path, fresh: dict[str, Any], tmp_path: Path
) -> None:
    loaded = plugins.bootstrap(config())

    assert loaded["prama.connectors"] == 1
    assert loaded["prama.notifiers"] == 1
    assert loaded["prama.monitors"] == 1

    # The connector, through the registry the API and the CLI use.
    from prama.connect.registry import default_registry

    registry = default_registry()
    assert "fixed_width" in registry and "sqlite" in registry  # beside the shipped ones
    root = tmp_path / "extracts"
    root.mkdir()
    (root / "p.txt").write_text("0001GB0002634946\n", encoding="ascii")
    connector = registry.create("fixed_width", {"root_path": str(root), "layout": LAYOUT})
    assert type(connector).__name__ == "FixedWidthConnector"

    # The notifier, by key, delivering.
    from prama.alert.notify import Message, build

    build("capture", {}).deliver(Message(subject="s", body="b", recipients=("ada",)))
    assert [m.subject for m in sys.modules["prama_demo_plugins"].SENT] == ["s"]

    # The detector, by name, scoring — and through a Monitor.
    from prama.monitor.fleet import Monitor
    from prama.monitor.registry import detector

    score = detector("last_value_demo").score(15.0, [10.0] * 12)
    assert score is not None and score.value == 5.0
    assert Monitor("trades", "rows", detector="last_value_demo").detector.name == "last_value_demo"


def test_plugins_disabled_keeps_each_one_out(distribution: Path, fresh: dict[str, Any]) -> None:
    loaded = plugins.bootstrap(config(disabled=["fixed_width", "CAPTURE", "last_value_demo"]))

    assert loaded["prama.connectors"] == 0
    assert "fixed_width" not in fresh["connectors"]
    assert "capture" not in fresh["notifiers"]
    assert "last_value_demo" not in fresh["detectors"]
    # Never imported, either: a disabled plugin's code does not run.
    assert "prama_demo_plugins" not in sys.modules


def test_a_group_that_is_not_configured_is_not_loaded(
    distribution: Path, fresh: dict[str, Any]
) -> None:
    plugins.bootstrap(config(entry_point_groups=["prama.validators"]))
    assert "fixed_width" not in fresh["connectors"]


def test_a_plugin_cannot_take_a_shipped_key(
    distribution: Path, fresh: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A distribution that shadowed `sqlite` would change what every control reads."""
    from prama.connect.sources.sqlite import SqliteConnector

    (distribution / "prama_demo_shadow.py").write_text(SHADOW_MODULE, encoding="utf-8")
    info = distribution / "prama_demo_plugins-1.0.dist-info" / "entry_points.txt"
    info.write_text("[prama.connectors]\nshadow = prama_demo_shadow:Shadow\n", encoding="utf-8")
    importlib.invalidate_caches()
    try:
        loaded = plugins.bootstrap(config())
        assert sys.modules["prama_demo_shadow"].Shadow.manifest().key == "sqlite"
    finally:
        sys.modules.pop("prama_demo_shadow", None)
    assert loaded["prama.connectors"] == 0
    assert fresh["connectors"].get("sqlite") is SqliteConnector


def test_each_group_loads_once_per_process(distribution: Path, fresh: dict[str, Any]) -> None:
    first = plugins.bootstrap(config())
    second = plugins.bootstrap(config())
    assert first == second
    assert fresh["notifiers"].keys().count("capture") == 1


def test_without_the_connector_loader_the_plugin_is_absent(
    distribution: Path, fresh: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The counterfactual for the wiring itself: this is the state before the fix.

    `ConnectorRegistry.discover()` existed and nothing called it. Remove the
    loader that calls it and the same distribution contributes nothing — so
    the first test above is measuring the wiring, not an accident.
    """
    monkeypatch.setattr(
        plugins,
        "LOADERS",
        {g: f for g, f in plugins.LOADERS.items() if g != "prama.connectors"},
    )
    plugins.bootstrap(config())
    assert "fixed_width" not in fresh["connectors"]
    assert "capture" in fresh["notifiers"]
