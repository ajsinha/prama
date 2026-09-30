"""What an SDK method accepts as a file: a path, or bytes or text with a name.

Not a namespace (the leading underscore keeps the clients from loading it as one).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: A file for upload: a path on disk, or its content (bytes, text, or a JSON-able object).
FileLike = str | Path | bytes | dict[str, Any] | list[Any]


def upload(value: Any, default_name: str, content_type: str) -> tuple[str, bytes, str]:
    """``(filename, body, content type)`` for httpx, from a path or from content.

    A ``str`` is a path when a file exists there, and content otherwise; pass a
    ``Path`` to insist on a path.
    """
    if isinstance(value, Path) or (
        isinstance(value, str) and "\n" not in value and len(value) < 4096 and Path(value).is_file()
    ):
        path = Path(value)
        return path.name, path.read_bytes(), content_type
    if isinstance(value, bytes):
        return default_name, value, content_type
    if isinstance(value, str):
        return default_name, value.encode("utf-8"), content_type
    return default_name, json.dumps(value).encode("utf-8"), "application/json"
