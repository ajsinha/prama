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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from prama.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PramaError,
    SchemaDriftError,
    UnauthorisedError,
    ValidationError,
)
from prama.core.log import correlation_id, get_logger
from prama.llm.budget import BudgetExhausted

_log = get_logger(__name__)

#: Which HTTP status each error family deserves. Anything unmapped is a 500,
#: which is correct: an unmapped error is one we did not anticipate.
STATUS_BY_TYPE: list[tuple[type[PramaError], int]] = [
    (UnauthorisedError, 401),
    (ForbiddenError, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (ValidationError, 422),
    (SchemaDriftError, 503),
    (BudgetExhausted, 429),
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


async def router_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A 404 or a 405 from the router itself, as a problem document.

    Starlette raises `HTTPException` before any Prama code runs — an unknown
    path, a method the route does not accept — and answers it with its own
    handler, producing `{"detail": "Not Found"}` and `content-type:
    application/json`. Every other error this API emits is `problem+json` with a
    `code` an integrator can branch on; these two, the ones a caller hits most
    often, were the exceptions. QA round 4, cluster B1.

    The `code` is synthesised rather than taken from the taxonomy: there is no
    `PramaError` here to ask, and inventing one would put a made-up remedy in
    front of somebody who mistyped a URL. `type`, `title`, `status` and `code`
    are real; `remedy` is omitted rather than guessed, because a remedy that
    does not help is worse than none.
    """
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    code = "HTTP.NOT_FOUND" if status == 404 else f"HTTP.{status}"
    document: dict[str, Any] = {
        "type": PROBLEM_TYPE_BASE + code.lower().replace(".", "-"),
        "title": str(exc.detail),
        "status": status,
        "code": code,
        "instance": str(request.url.path),
    }
    if cid := correlation_id.get():
        document["correlation_id"] = cid
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=status,
        content=document,
        media_type="application/problem+json",
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A malformed query or body, as a problem document.

    FastAPI raises `RequestValidationError` before the handler runs, and its
    `.errors()` already names the offending field and why. That detail is kept
    verbatim in `context`: a problem document that cannot say *which* parameter
    was wrong is prose with a schema, and the field name is the only part a
    caller can act on.
    """
    assert isinstance(exc, RequestValidationError)
    document: dict[str, Any] = {
        "type": PROBLEM_TYPE_BASE + "input-invalid",
        "title": "the request could not be understood",
        "status": 422,
        "code": "INPUT.INVALID",
        "remedy": "Correct the fields listed in context and send the request again.",
        # `str()` per error: `.errors()` may carry an exception object under
        # `ctx`, which is not JSON-serialisable and would turn a 422 into a 500.
        "context": {"errors": [{k: str(v) for k, v in e.items()} for e in exc.errors()]},
        "instance": str(request.url.path),
    }
    if cid := correlation_id.get():
        document["correlation_id"] = cid
    return JSONResponse(status_code=422, content=document, media_type="application/problem+json")


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
