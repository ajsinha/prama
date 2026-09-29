"""Vet delegates in a subprocess, never in the server.

    python -m prama.delegates.vet DIR       one upload: the conformance kit, and its description
    python -m prama.delegates.vet --admit   configured delegates (the request on stdin)

Started through `prama.delegates.sandbox.run_isolated`: resource limits, a
clean environment, a network namespace where the host allows one, and the
audit hook sealed before any delegate is imported. Delegate code is imported
here, in a process that can be killed, and never in the server.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import sys


def admit() -> int:
    """Load the configured delegates here, not in the server, and describe them.

    The configuration arrives on stdin (``paths``, ``disabled``,
    ``entry_points``). Each file is scanned, imported and probed in this
    process, sealed by the audit hook first; the server receives only the
    descriptions and the refusals, and never imports the code.
    """
    from prama.delegates.registry import DelegateRegistry
    from prama.delegates.worker import seal

    request = json.loads(sys.stdin.read() or "{}")
    seal()
    registry = DelegateRegistry()
    disabled = list(request.get("disabled") or [])
    registry.load_paths(
        list(request.get("paths") or []), disabled=disabled, only=str(request.get("only") or "")
    )
    if request.get("entry_points"):
        registry.load_entry_points(disabled=disabled)
    admitted = [
        {**a.describe(), "source_hash": a.source_hash} for a in registry.all() if not a.sandbox_only
    ]
    json.dump({"admitted": admitted, "refused": registry.refused}, sys.stdout, default=str)
    return 0


def main() -> int:
    if sys.argv[1:2] == ["--admit"]:
        try:
            return admit()
        except Exception as exc:
            json.dump({"admitted": [], "refused": {}, "error": str(exc)}, sys.stdout)
            return 1
    from prama.delegates.registry import DelegateRegistry
    from prama.delegates.testkit import check_delegate
    from prama.delegates.worker import seal

    directory = sys.argv[1]
    try:
        # Sealed before the uploaded file is imported: its top-level code runs
        # under the same refusals as a run.
        seal()
        report = check_delegate(directory, sandbox=False, large_rows=10_000, time_limit_s=60)
        registry = DelegateRegistry()
        registry.load_paths([directory])
        described = [a.describe() for a in registry.all()]
        json.dump({**report.to_dict(), "described": described}, sys.stdout, default=str)
    except Exception as exc:
        json.dump({"ok": False, "checks": [], "described": [], "error": str(exc)}, sys.stdout)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
