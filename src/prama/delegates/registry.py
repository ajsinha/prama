"""Which delegates this host may run, and the gate each one passed to get here.

Two ways in, both from configuration (`delegates:` in application.yaml), so a
control-plane server and an agent beside the data can each be given exactly
the delegates they should run:

* **Entry points** (`prama.delegates`), from an installed distribution. The
  way a reviewed, versioned package arrives.
* **Paths** (`delegates.paths`): directories of `.py` files. Every file is
  scanned *before* it is imported, because importing runs its top-level code,
  and a gate that had to import the thing it was gating would already have run
  it. The same scan the validator plugins pass (`prama.classify.plugins`).

Admission then runs each delegate twice on probe rows and requires the same
answer, and hashes its source. The hash goes on every evidence record the
delegate produces, so what ran is always knowable.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from prama.core.errors import NotFoundError, ValidationError
from prama.core.log import get_logger
from prama.delegates.spi import UNITS, DqDelegate

_log = get_logger(__name__)

ENTRY_POINT_GROUP = "prama.delegates"


@dataclasses.dataclass(frozen=True, slots=True)
class Admitted:
    """A delegate that passed the gate, and what it was when it did."""

    delegate: DqDelegate
    origin: str
    implementation_hash: str

    @property
    def name(self) -> str:
        return self.delegate.name

    @property
    def version(self) -> str:
        return str(self.delegate.version)

    def describe(self) -> dict[str, Any]:
        d = self.delegate
        return {
            "name": d.name,
            "version": self.version,
            "unit": d.unit,
            "requires": list(d.requires),
            "parameters": [dataclasses.asdict(p) for p in d.parameters],
            "summary": d.summary,
            "origin": self.origin,
            "implementation_hash": self.implementation_hash,
        }


def _probes(delegate: DqDelegate) -> list[list[dict[str, Any]]]:
    columns = list(delegate.requires) or ["value"]
    odd: list[Any] = [None, "", " ", 0, -1, 1.5, "2026-02-30", "x" * 64, "é"]
    return [
        [],
        [dict.fromkeys(columns)],
        [{c: odd[(i + j) % len(odd)] for j, c in enumerate(columns)} for i in range(len(odd))],
    ]


def check(delegate: DqDelegate) -> None:
    """Shape, determinism and robustness. Raises with the guarantee it tripped."""
    from prama.delegates.spi import Measurement

    if not delegate.name or " " in delegate.name or "@" in delegate.name:
        raise ValidationError(
            f"{type(delegate).__name__} has no usable name ({delegate.name!r})",
            remedy="Set `name` to a dotted identifier such as 'acme.settlement_cycle'.",
        )
    if delegate.unit not in UNITS:
        raise ValidationError(f"{delegate.name}: unit must be one of {UNITS}", remedy="Set `unit`.")
    params = delegate.resolve({})
    for probe in _probes(delegate):
        try:
            first = delegate.measure(iter(probe), params)
            second = delegate.measure(iter(probe), params)
        except Exception as exc:
            raise ValidationError(
                f"{delegate.name} raised on probe rows ({type(exc).__name__}: {exc})",
                remedy=(
                    "A delegate must count odd input, not raise on it: a null, a blank or "
                    "an empty dataset is data. Raising takes the control down instead of "
                    "failing the row."
                ),
            ) from exc
        if not isinstance(first, Measurement):
            raise ValidationError(
                f"{delegate.name}.measure returned {type(first).__name__}",
                remedy="Return a prama.delegates.Measurement.",
            )
        if first.to_dict() != second.to_dict():
            raise ValidationError(
                f"{delegate.name} gave two answers for the same rows",
                remedy=(
                    "A control has to replay. Remove the clock, the random source, the "
                    "mutable state or the set iteration order."
                ),
            )
        problems = first.problems(unit=delegate.unit)
        if problems:
            raise ValidationError(
                f"{delegate.name} returned a measurement that cannot be judged: {problems[0]}",
                remedy="Counts are whole numbers, violating never exceeds scanned rows.",
            )


class DelegateRegistry:
    """The delegates this host admitted, by name."""

    def __init__(self) -> None:
        self._admitted: dict[str, Admitted] = {}
        #: Refusals, kept so `prama delegate list` can say why one is missing.
        self.refused: dict[str, str] = {}

    def admit(self, delegate: DqDelegate, *, origin: str = "") -> Admitted:
        from prama.classify.plugins import forbidden_imports, implementation_hash

        banned = forbidden_imports(delegate)
        if banned:
            listed = "; ".join(f"{m} — {why}" for m, why in sorted(set(banned)))
            raise ValidationError(
                f"{delegate.name or type(delegate).__name__} imports something a delegate "
                f"may not: {listed}",
                remedy=(
                    "A delegate is a function of the rows it is given. Reference data it "
                    "needs belongs in its parameters or in a code list."
                ),
            )
        check(delegate)
        if delegate.name in self._admitted:
            raise ValidationError(
                f"two delegates are called {delegate.name}",
                remedy="Rename one, or disable the other in delegates.disabled.",
            )
        admitted = Admitted(delegate, origin, implementation_hash(delegate))
        self._admitted[delegate.name] = admitted
        _log.info(
            "admitted delegate %s@%s from %s (%s)",
            delegate.name,
            admitted.version,
            origin,
            admitted.implementation_hash[:12],
        )
        return admitted

    def get(self, name: str, *, version: str = "") -> Admitted:
        admitted = self._admitted.get(name)
        if admitted is None:
            why = self.refused.get(name)
            raise NotFoundError(
                f"the delegate {name} is not installed on this host"
                + (f" (it was refused: {why})" if why else ""),
                remedy=(
                    "Install it here (delegates.paths or a distribution advertising the "
                    "prama.delegates entry point), or run the control on an agent that "
                    "has it."
                ),
            )
        if version and version != admitted.version:
            raise ValidationError(
                f"the control pins {name}@{version} and this host has @{admitted.version}",
                remedy="Upgrade the control's pin, or install the version it names.",
            )
        return admitted

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._admitted))

    def pinned(self) -> tuple[str, ...]:
        """`name@version` for each, as an agent advertises them."""
        return tuple(f"{a.name}@{a.version}" for _, a in sorted(self._admitted.items()))

    def all(self) -> list[Admitted]:
        return [a for _, a in sorted(self._admitted.items())]

    # -- loading ------------------------------------------------------------

    def _try(self, delegate: DqDelegate, origin: str) -> None:
        try:
            self.admit(delegate, origin=origin)
        except Exception as exc:
            # Loud, and the others still load: one bad delegate must not take an
            # estate's delegates down with it.
            self.refused[getattr(delegate, "name", "") or origin] = str(exc)
            _log.error("refused delegate from %s: %s", origin, exc)

    def load_paths(self, paths: Iterable[str], *, disabled: Iterable[str] = ()) -> None:
        from prama.classify.plugins import scan_source

        off = {d.strip() for d in disabled}
        for directory in paths:
            root = Path(directory).expanduser().resolve()
            files = sorted(root.glob("*.py")) if root.is_dir() else []
            if not root.is_dir():
                self.refused[str(root)] = "not a directory"
                _log.error("delegates.paths: %s is not a directory", root)
            for path in files:
                if path.name.startswith("_"):
                    continue
                banned = scan_source(str(path))
                if banned:
                    listed = "; ".join(f"{m} — {why}" for m, why in sorted(set(banned)))
                    # Refused before import: its top-level code never ran.
                    self.refused[path.name] = f"not imported: {listed}"
                    _log.error("refused delegate file %s before import: %s", path, listed)
                    continue
                module_name = f"prama_delegate_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module  # so inspect can find the source
                try:
                    spec.loader.exec_module(module)
                except Exception as exc:
                    self.refused[path.name] = f"import failed: {exc}"
                    continue
                for _, cls in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(cls, DqDelegate)
                        and cls is not DqDelegate
                        and cls.__module__ == module_name
                        and not inspect.isabstract(cls)
                        and cls.name not in off
                    ):
                        self._try(cls(), f"path:{path}")

    def load_entry_points(self, *, disabled: Iterable[str] = ()) -> None:
        from importlib.metadata import entry_points

        off = {d.strip() for d in disabled}
        for entry in entry_points(group=ENTRY_POINT_GROUP):
            if entry.name in off:
                continue
            try:
                delegate = entry.load()()
            except Exception as exc:
                self.refused[entry.name] = f"import failed: {exc}"
                continue
            self._try(delegate, f"entry_point:{entry.dist.name if entry.dist else entry.name}")


def from_config(config: Any) -> DelegateRegistry:
    """The registry `delegates:` in configuration describes."""
    registry = DelegateRegistry()
    section = _section(config)
    if not section.get("enabled", True):
        return registry
    disabled = section.get("disabled") or []
    registry.load_paths(section.get("paths") or [], disabled=disabled)
    if section.get("entry_points", True):
        registry.load_entry_points(disabled=disabled)
    return registry


def _section(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config.get("delegates") or {})
    getter = getattr(config, "get", None)
    value = getter("delegates") if callable(getter) else getattr(config, "delegates", None)
    return dict(value or {})
