"""The plugin registry.

Every extension point in Prama — connectors, execution backends, monitors,
notifiers, scorers, lease providers, semantic-type validators — is an abstract
base class whose implementations are discovered rather than imported by name.
Two consequences, both required by NFR-MNT-002:

* adding a connector never edits core code;
* a concrete implementation class is never referenced outside its own package,
  which is checked by an architecture test.

Each plugin declares a **capability manifest**: what it is, what it can do, and
which conformance suite proves it. A plugin that does not declare one is not
loadable, because an undeclared capability is the thing the compiler would
otherwise have to guess at.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from importlib.metadata import EntryPoint, entry_points
from typing import Any, ClassVar, Generic, TypeVar

from prama.core.errors import RegistryError
from prama.core.log import get_logger

T = TypeVar("T", bound="Plugin")

_log = get_logger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class Capability:
    """One declared ability, with the arguments that qualify it.

    Example: ``Capability("pushdown.sql", {"dialect": "postgres", "window": True})``.
    The compiler consults capabilities; it never guesses and never probes.
    """

    name: str
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __str__(self) -> str:
        if not self.attributes:
            return self.name
        rendered = ",".join(f"{k}={v}" for k, v in sorted(self.attributes.items()))
        return f"{self.name}[{rendered}]"


@dataclasses.dataclass(frozen=True, slots=True)
class PluginManifest:
    """What a plugin is and what it claims to do."""

    key: str
    kind: str
    display_name: str
    version: str
    capabilities: tuple[Capability, ...] = ()
    description: str = ""
    vendor: str = ""
    conformance_suite: str = ""

    def has(self, capability: str) -> bool:
        return any(c.name == capability for c in self.capabilities)

    def attribute(self, capability: str, attribute: str, default: Any = None) -> Any:
        for cap in self.capabilities:
            if cap.name == capability:
                return cap.attributes.get(attribute, default)
        return default


class Plugin(ABC):
    """Base of every discovered implementation."""

    #: Set by the subclass. Unique within its kind.
    plugin_key: ClassVar[str] = ""

    @classmethod
    @abstractmethod
    def manifest(cls) -> PluginManifest:
        """Describe this plugin. Called without instantiating it."""


class Registry(Generic[T]):
    """A registry for one kind of plugin.

    Implementations may be registered directly (used by first-party code and by
    tests) or discovered from an entry-point group (used by third-party
    packages). Both paths validate the manifest, so an ill-formed plugin fails
    at registration with a message naming it — never at first use, deep inside
    an execution.
    """

    def __init__(self, kind: str, base: type[T], *, entry_point_group: str | None = None) -> None:
        self._kind = kind
        self._base = base
        self._group = entry_point_group
        self._plugins: dict[str, type[T]] = {}
        self._disabled: set[str] = set()
        self._discovered = False

    @property
    def kind(self) -> str:
        return self._kind

    def register(self, implementation: type[T], *, replace: bool = False) -> None:
        manifest = self._validate(implementation)
        if manifest.key in self._plugins and not replace:
            raise RegistryError(
                f"{self._kind} plugin {manifest.key!r} is already registered",
                remedy="Choose a different plugin_key, or pass replace=True deliberately.",
                context={"kind": self._kind, "key": manifest.key},
            )
        self._plugins[manifest.key] = implementation

    def disable(self, keys: list[str]) -> None:
        self._disabled.update(keys)

    def discover(self, group: str | None = None) -> int:
        """Load implementations advertised on an entry-point group.

        A plugin that fails to import is logged and skipped rather than taking
        the process down: one broken third-party connector must not prevent the
        platform from starting, and the failure is visible in health output.
        """
        group_name = group or self._group
        if not group_name:
            return 0
        loaded = 0
        for ep in _entry_points_for(group_name):
            try:
                implementation = ep.load()
                self.register(implementation)
                loaded += 1
            except Exception as exc:  # noqa: BLE001 - deliberate isolation boundary
                _log.warning(
                    "plugin %r from group %r failed to load: %s", ep.name, group_name, exc
                )
        self._discovered = True
        return loaded

    def get(self, key: str) -> type[T]:
        if key in self._disabled:
            raise RegistryError(
                f"{self._kind} plugin {key!r} is disabled by configuration",
                remedy=f"Remove {key!r} from plugins.disabled to use it.",
                context={"kind": self._kind, "key": key},
            )
        try:
            return self._plugins[key]
        except KeyError:
            raise RegistryError(
                f"no {self._kind} plugin registered for {key!r}",
                remedy=(
                    f"Available: {', '.join(sorted(self.keys())) or '(none)'}. "
                    f"Install the package providing it, or correct the key."
                ),
                context={"kind": self._kind, "key": key, "available": sorted(self.keys())},
            ) from None

    def manifest(self, key: str) -> PluginManifest:
        return self.get(key).manifest()

    def keys(self) -> list[str]:
        return [k for k in self._plugins if k not in self._disabled]

    def manifests(self) -> list[PluginManifest]:
        return [self._plugins[k].manifest() for k in sorted(self.keys())]

    def with_capability(self, capability: str) -> list[PluginManifest]:
        return [m for m in self.manifests() if m.has(capability)]

    def __contains__(self, key: str) -> bool:
        return key in self._plugins and key not in self._disabled

    def __len__(self) -> int:
        return len(self.keys())

    # -- internals ---------------------------------------------------------

    def _validate(self, implementation: type[T]) -> PluginManifest:
        if not isinstance(implementation, type) or not issubclass(implementation, self._base):
            raise RegistryError(
                f"{getattr(implementation, '__name__', implementation)!r} is not a "
                f"{self._base.__name__}",
                remedy=f"Make the plugin subclass {self._base.__name__}.",
                context={"kind": self._kind},
            )
        try:
            manifest = implementation.manifest()
        except Exception as exc:  # noqa: BLE001
            raise RegistryError(
                f"{implementation.__name__}.manifest() raised {type(exc).__name__}",
                remedy="manifest() must be a pure classmethod returning a PluginManifest.",
                context={"kind": self._kind, "plugin": implementation.__name__},
                cause=exc,
            ) from exc
        if not isinstance(manifest, PluginManifest):
            raise RegistryError(
                f"{implementation.__name__}.manifest() did not return a PluginManifest",
                remedy="Return a PluginManifest describing the plugin.",
                context={"kind": self._kind, "plugin": implementation.__name__},
            )
        if not manifest.key:
            raise RegistryError(
                f"{implementation.__name__} declares an empty plugin key",
                remedy="Give the plugin a stable, unique key.",
                context={"kind": self._kind},
            )
        if manifest.kind != self._kind:
            raise RegistryError(
                f"{implementation.__name__} declares kind {manifest.kind!r} but was "
                f"registered as {self._kind!r}",
                remedy="Correct the manifest's kind, or register it with the right registry.",
                context={"kind": self._kind, "declared": manifest.kind},
            )
        return manifest


def _entry_points_for(group: str) -> list[EntryPoint]:
    try:
        return list(entry_points(group=group))
    except Exception:  # noqa: BLE001 - importlib.metadata differs across environments
        return []


class RegistryCatalogue:
    """All registries, addressed by kind.

    Held as a single object rather than module globals so that a test can build
    an isolated catalogue, and so that a multi-tenant process could in principle
    hold more than one.
    """

    def __init__(self) -> None:
        self._registries: dict[str, Registry[Any]] = {}

    def create(
        self, kind: str, base: type[T], *, entry_point_group: str | None = None
    ) -> Registry[T]:
        if kind in self._registries:
            raise RegistryError(
                f"registry {kind!r} already exists",
                remedy="Use catalogue.of(kind) to fetch the existing registry.",
                context={"kind": kind},
            )
        registry: Registry[T] = Registry(kind, base, entry_point_group=entry_point_group)
        self._registries[kind] = registry
        return registry

    def of(self, kind: str) -> Registry[Any]:
        try:
            return self._registries[kind]
        except KeyError:
            raise RegistryError(
                f"no registry named {kind!r}",
                remedy=f"Known registries: {', '.join(sorted(self._registries)) or '(none)'}.",
                context={"kind": kind},
            ) from None

    def kinds(self) -> list[str]:
        return sorted(self._registries)

    def discover_all(self, groups: list[str] | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for kind, registry in self._registries.items():
            if groups is not None and registry._group not in groups:
                continue
            counts[kind] = registry.discover()
        return counts
