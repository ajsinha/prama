"""Vet an uploaded delegate in a subprocess: ``python -m prama.delegates.vet DIR``.

Runs the conformance kit over the one file in DIR and prints the report and
each admitted delegate's description as JSON. Started by
`prama.delegates.uploads.vet` with resource limits set, so uploaded code is
imported here, in a process that can be killed, and never in the server.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    from prama.delegates.registry import DelegateRegistry
    from prama.delegates.testkit import check_delegate

    directory = sys.argv[1]
    try:
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
