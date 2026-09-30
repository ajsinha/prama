"""The errors a client sees: Prama's error taxonomy, as the SDK's own classes.

The server answers every failure with a problem document carrying a stable
``code`` (``ENTITY.NOT_FOUND``, ``AUTH.FORBIDDEN``…), a message and a remedy.
The SDK cannot import the server, so it defines the classes a caller catches
and maps each code to one; a code it does not know falls back to the class for
its HTTP status, so a new server-side error is still caught by the right
``except``. The server's test suite checks every server code against this map.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any


class PramaError(Exception):
    """Any failure Prama reported, with what happened and what to do next."""

    code = "PRAMA.ERROR"

    def __init__(
        self,
        message: str,
        *,
        remedy: str = "",
        code: str | None = None,
        context: dict[str, Any] | None = None,
        status: int = 0,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.remedy = remedy
        self.code = code or type(self).code
        self.context: dict[str, Any] = dict(context or {})
        #: The HTTP status the server answered with; 0 when nothing answered.
        self.status = status

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.remedy:
            parts.append(f"Next: {self.remedy}")
        if self.context:
            parts.append(
                "Context: " + ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
            )
        return " | ".join(parts)


class UnauthorisedError(PramaError):
    """401: no credential, or one that is not usable."""

    code = "AUTH.UNAUTHORISED"


class ForbiddenError(PramaError):
    """403: the credential is fine and does not permit this."""

    code = "AUTH.FORBIDDEN"


class NotFoundError(PramaError):
    """404: nothing by that name in this estate."""

    code = "ENTITY.NOT_FOUND"


class ConflictError(PramaError):
    """409: it already exists, or is not in a state that allows this."""

    code = "ENTITY.CONFLICT"


class ValidationError(PramaError):
    """422: the request could not be accepted as it stands."""

    code = "INPUT.INVALID"


class RateLimitedError(PramaError):
    """429: a budget or rate was exhausted."""

    code = "PRAMA.RATE_LIMITED"


class ServerError(PramaError):
    """5xx: the server failed; the correlation id in the context finds it in its log."""

    code = "PRAMA.SERVER_ERROR"


class ServerUnavailable(PramaError):
    """No Prama server answered at all: a question of where it is, not of the call."""

    code = "SDK.SERVER_UNAVAILABLE"


#: The classes a caller catches, by the status the server answers with.
BY_STATUS: dict[int, type[PramaError]] = {
    401: UnauthorisedError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitedError,
}

#: The codes that name one of those classes exactly.
BY_CODE: dict[str, type[PramaError]] = {
    cls.code: cls
    for cls in (UnauthorisedError, ForbiddenError, NotFoundError, ConflictError, ValidationError)
}


def error_for(code: str, status: int) -> type[PramaError]:
    """The class for a server error *code*, or for its HTTP *status* when the code is new."""
    if code in BY_CODE:
        return BY_CODE[code]
    if status in BY_STATUS:
        return BY_STATUS[status]
    return ServerError if status >= 500 else PramaError
