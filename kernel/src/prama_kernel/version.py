"""The kernel's version: a copy of ``src/prama/version.py``, policed.

``scripts/check_version_source.py`` fails the build if it disagrees.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Final

VERSION: Final[str] = "0.1.0"
