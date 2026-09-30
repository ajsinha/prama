"""The SDK's version.

A copy of the server's ``src/prama/version.py``, because the SDK ships on its own
and cannot import the server. It is a *policed* copy:
``scripts/check_version_source.py`` fails the build if it ever disagrees, so a
client can read which server release an SDK was built against.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Final

VERSION: Final[str] = "0.1.0"
