"""The sandboxed side of a delegate run: one request on stdin, one answer on stdout.

Started by `prama.delegates.host` as ``python -m prama.delegates.worker`` with
resource limits already set. It loads exactly the delegate it was asked for,
from where the host admitted it — re-scanning a file before importing it,
because the file may have changed since the host looked — runs it once, and
prints the measurement.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _load(name: str, origin: str) -> Any:
    from prama.delegates.registry import DelegateRegistry

    registry = DelegateRegistry()
    kind, _, where = origin.partition(":")
    if kind == "path":
        from pathlib import Path

        path = Path(where)
        registry.load_paths([str(path.parent)])
    else:
        registry.load_entry_points()
    return registry.get(name).delegate


def main() -> int:
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    try:
        delegate = _load(str(request["name"]), str(request.get("origin", "")))
        measurement = delegate.measure(iter(request.get("rows") or []), request.get("params") or {})
        json.dump({"measurement": measurement.to_dict()}, sys.stdout, default=str)
    except Exception as exc:
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
