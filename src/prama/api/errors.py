"""Turning Prama errors into HTTP problem documents.

Every failure leaves the API as an RFC 9457 problem document carrying the same
three things the error carried internally: **what happened, why, and what to do
next**. The remedy is not decoration — it is the field that lets an integrator
fix their call without reading our source.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from prama.core.errors import (
    ConflictError,
    NotFoundError,
    PramaError,
    SchemaDriftError,
    ValidationError,
)
from prama.core.log import correlation_id, get_logger

_log = get_logger(__name__)

#: Which HTTP status each error family deserves. Anything unmapped is a 500,
#: which is correct: an unmapped error is one we did not anticipate.
STATUS_BY_TYPE: list[tuple[type[PramaError], int]] = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (ValidationError, 422),
    (SchemaDriftError, 503),
]

PROBLEM_TYPE_BASE = "https://prama.dev/problems/"


def status_for(error: PramaError) -> int:
    for error_type, status in STATUS_BY_TYPE:
        if isinstance(error, error_type):
            return status
    return 500


def problem_document(
    error: PramaError, *, status: int, instance: str | None = None
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "type": PROBLEM_TYPE_BASE + error.code.lower().replace(".", "-"),
        "title": error.message,
        "status": status,
        "code": error.code,
        # The field that distinguishes a useful error from a rude one.
        "remedy": error.remedy,
    }
    if error.context:
        document["context"] = error.context
    if instance:
        document["instance"] = instance
    if cid := correlation_id.get():
        document["correlation_id"] = cid
    return document


async def prama_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render a Prama error. Server-side failures are logged; client ones are not.

    A 4xx is the caller's business and logging it at error level turns a typo in
    somebody's script into a page for somebody else.
    """
    assert isinstance(exc, PramaError)
    status = status_for(exc)
    if status >= 500:
        _log.error("%s", exc, exc_info=exc)
    document = problem_document(exc, status=status, instance=str(request.url.path))
    return JSONResponse(status_code=status, content=document, media_type="application/problem+json")


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything not in the taxonomy.

    The message is deliberately generic: an unanticipated exception's text may
    contain anything, including a fragment of customer data, and an API response
    is the wrong place to find out.
    """
    _log.error("unhandled %s on %s", type(exc).__name__, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        media_type="application/problem+json",
        content={
            "type": PROBLEM_TYPE_BASE + "internal",
            "title": "an unexpected error occurred",
            "status": 500,
            "code": "PRAMA.INTERNAL",
            "remedy": (
                "Retry; if it persists, quote the correlation id to support. The detail "
                "has been logged server-side."
            ),
            "correlation_id": correlation_id.get(),
            "instance": str(request.url.path),
        },
    )
