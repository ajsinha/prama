"""The Prama HTTP API.

The console, the CLI and the conversational assistant are all clients of this
surface; there is no privileged internal path (docs/corpus/06 A6). If a capability is
not here, it does not exist.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.api.app import API_PREFIX, create_app

__all__ = ["API_PREFIX", "create_app"]
