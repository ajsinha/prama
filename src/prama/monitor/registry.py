"""Detectors by name: the shipped five, and any a distribution advertises.

A detector was only ever passed by hand to the `Monitor` or `Ensemble` that
used it, which left the ``prama.monitors`` entry-point group in configuration
with nothing behind it. This registry is what that group loads into
(`prama.plugins.bootstrap`, honouring ``plugins.disabled``), and what
``Monitor(detector="trimmed_deviation")`` resolves a name through.

Registering a detector makes it *available*; it does not make it a default.
The default for a metric kind is still `prama.monitor.fleet`'s choice, and an
ensemble still names its members — a third-party package changing what every
monitor in an estate runs, merely by being installed, would be a change nobody
decided.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.core.registry import Registry
from prama.monitor.detect import (
    Detector,
    ForecastResidual,
    LocalOutlierFactor,
    QuantileDistance,
    RobustDeviation,
    ShapeDistance,
)

#: The entry-point group a distribution advertises detectors under.
ENTRY_POINT_GROUP = "prama.monitors"

BUILTIN: tuple[type[Detector], ...] = (
    RobustDeviation,
    QuantileDistance,
    LocalOutlierFactor,
    ForecastResidual,
    ShapeDistance,
)


def new_registry() -> Registry[Detector]:
    """A registry holding the shipped detectors and nothing else."""
    registry: Registry[Detector] = Registry(
        "detector",
        Detector,  # type: ignore[type-abstract]
        entry_point_group=ENTRY_POINT_GROUP,
    )
    for detector in BUILTIN:
        registry.register(detector)
    return registry


_default: Registry[Detector] | None = None


def default_registry() -> Registry[Detector]:
    """The process-wide detector registry."""
    global _default
    if _default is None:
        _default = new_registry()
    return _default


def detector(name: str, registry: Registry[Detector] | None = None) -> Detector:
    """A fresh detector by name, with its default parameters."""
    return (registry or default_registry()).get(name)()


__all__ = ["BUILTIN", "ENTRY_POINT_GROUP", "default_registry", "detector", "new_registry"]
