"""First-party connectors.

Each is a plugin: registered through an entry point, declaring a capability
matrix, and passing the same conformance suite. Adding one never edits core.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.sources.filesystem import FilesystemConnector
from prama.connect.sources.sqlite import SqliteConnector

__all__ = ["FilesystemConnector", "SqliteConnector"]
