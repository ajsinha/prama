"""Shared plumbing for the knowledge-and-code routes: reading an upload within a cap.

Not a route module (the leading underscore keeps discovery away from it).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from prama.core.errors import ValidationError

#: The largest text document (SQL, a vendor export, a manifest) accepted in one upload.
MAX_TEXT = 32 * 1024 * 1024


async def read_capped(upload: UploadFile, cap: int, *, what: str = "the upload") -> bytes:
    """The upload's bytes, refused as soon as it passes *cap* rather than after."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(1 << 16):
        size += len(chunk)
        if size > cap:
            raise ValidationError(
                f"{what} is larger than {cap // (1024 * 1024)} MB",
                remedy="Send a smaller file, or split it.",
                context={"file": upload.filename or ""},
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def read_text(upload: UploadFile, *, what: str = "the upload") -> str:
    return (await read_capped(upload, MAX_TEXT, what=what)).decode("utf-8", errors="replace")


async def read_json(upload: UploadFile, *, what: str = "the export") -> Any:
    try:
        return json.loads(await read_text(upload, what=what))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{upload.filename or what} is not JSON: {exc.msg} at line {exc.lineno}",
            remedy="Upload the JSON the vendor's API returned, unmodified.",
        ) from exc


async def spool(upload: UploadFile, target: Path, cap: int, *, what: str) -> Path:
    """Stream an upload to *target*, refusing it past *cap*; a huge one never lands whole."""
    written = 0
    with target.open("wb") as sink:
        while chunk := await upload.read(1 << 16):
            written += len(chunk)
            if written > cap:
                raise ValidationError(
                    f"{what} is larger than the intake limit",
                    remedy="Send a smaller archive, or use a git location.",
                )
            sink.write(chunk)
    return target
