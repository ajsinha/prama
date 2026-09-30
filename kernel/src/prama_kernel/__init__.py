"""Prama's kernel: the deterministic code that must run beside the data.

Shared by the server (``prama``) and the standalone agent (``prama-agent``), so a
verdict judged on a remote agent is the verdict the server would have judged:
one copy of the code, not two that agree by intention.

What is here, and nothing else: the plan model (`plan`), the judge (`judge`),
the evidence record (`record`) and sample store (`samples`), the
reconciliation engine (`recon`), business calendars (`calendars`,
`banking_calendars`, `holidays`), the agent protocol with residency and the
spool (`agent`), the delegate runtime and its sandbox (`delegates`), the
static vetting scanner (`plugins`), and the primitives they share (`errors`,
`clock`, `pjson`, `log`). No compiler, no database, no API, no server.

The kernel depends on the standard library alone (``orjson`` if present).
``tests/architecture/test_packages_standalone.py`` fails the build if it
imports ``prama``, ``prama_sdk`` or ``prama_agent``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama_kernel.version import VERSION

__version__ = VERSION
