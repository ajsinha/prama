"""What an SDK method accepts where the server wants an uploaded file.

A path (its suffix says the format, as it does for the CLI), Python rows or a
document (sent as JSON), bytes (taken as JSON), or ``(filename, bytes)`` when
the bytes are CSV, JSON Lines or YAML and the name has to say so.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: A file for an upload: a path, rows, a document, bytes, or (name, bytes).
Upload = str | os.PathLike[str] | list[Any] | dict[str, Any] | bytes | tuple[str, bytes]


def upload(value: Upload, default_name: str) -> tuple[str, bytes, str]:
    """``(filename, content, content type)`` for one multipart field."""
    if isinstance(value, tuple):
        name, content = value
        return name, content, "application/octet-stream"
    if isinstance(value, bytes):
        return default_name, value, "application/json"
    if isinstance(value, list | dict):
        return default_name, json.dumps(value, default=str).encode(), "application/json"
    path = Path(value)
    return path.name, path.read_bytes(), "application/octet-stream"


__all__ = ["Upload", "upload"]
