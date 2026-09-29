"""An uploaded text file — a contract, rows, a query-history export — as a name and text.

The name matters as much as the text: every reader in Prama that accepts rows
chooses JSON, JSON Lines, CSV or YAML by the file's suffix, exactly as the CLI
does from a path. Refused rather than guessed when the bytes are not text or
are larger than a request should carry.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from fastapi import UploadFile

from prama.core.errors import ValidationError

#: The most an uploaded text file may hold. A contract or a day's query
#: history is kilobytes to tens of megabytes; beyond this, the data belongs in
#: a connector the server reads from, not in a request body held in memory.
MAX_BYTES = 64 * 1024 * 1024


async def text_of(upload: UploadFile, default_name: str) -> tuple[str, str]:
    """``(filename, text)`` of an upload, decoded as UTF-8."""
    name = upload.filename or default_name
    content = await upload.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValidationError(
            f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB",
            remedy="Send a smaller file, or register the data as a source and read it there.",
            context={"file": name},
        )
    try:
        return name, content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"{name} is not UTF-8 text",
            remedy="Send JSON, JSON Lines, CSV or YAML, encoded as UTF-8.",
            context={"file": name, "offset": exc.start},
        ) from None
