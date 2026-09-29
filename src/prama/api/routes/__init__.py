"""API route modules.

Each module that defines a module-level ``router`` is part of the versioned API
at ``/api/v1``, except ``probes``, which is mounted at the root because every
orchestrator looks for ``/livez`` there. Modules are found rather than listed,
so an area of the API is added by adding a file, and the SDK parity test
(``tests/sdk/test_parity.py``) then requires an SDK method for every endpoint.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

#: Mounted at the root, not under /api/v1.
UNVERSIONED = frozenset({"probes"})


def discover() -> list[ModuleType]:
    """Every versioned route module, in name order so the routing table is stable."""
    modules = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_") or info.name in UNVERSIONED:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(module, "router"):
            modules.append(module)
    return modules
