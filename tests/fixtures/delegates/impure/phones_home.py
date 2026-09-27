"""Refused before import. If it were imported, the SystemExit would stop the test run.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

import socket  # noqa: F401

raise SystemExit("imported a delegate the gate should have refused")
