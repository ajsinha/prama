"""Response headers the browser needs in order to defend the console.

QA round 2, `UI-045`, and finding `Q-45` before it: no response of any kind
carried a Content-Security-Policy, X-Content-Type-Options, Referrer-Policy or
X-Frame-Options. The console renders user-supplied estate names, control text
and evidence samples, so the absence is not theoretical.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

#: Where the nonce for this request is kept, so a template can read it.
NONCE_STATE = "csp_nonce"

#: Headers with no policy decision in them. Every one is a plain statement of
#: something already true about this application, so none can break a page.
STATIC_HEADERS: dict[str, str] = {
    # Never let a browser second-guess a declared content type. The console
    # serves user-supplied text; a response sniffed as HTML is stored XSS.
    "X-Content-Type-Options": "nosniff",
    # A control's URL carries dataset and control identifiers, which are an
    # estate's private vocabulary. They do not belong in a third party's logs.
    "Referrer-Policy": "same-origin",
    # X-Frame-Options for browsers that predate frame-ancestors, which is also
    # set in the policy below. Both, because the older header is the one an
    # old corporate browser understands and banks run old corporate browsers.
    "X-Frame-Options": "DENY",
}


def content_security_policy(nonce: str) -> str:
    """The policy, built around a per-response nonce.

    A nonce rather than `'unsafe-inline'`. The console has inline `<script>`
    blocks in six templates, and the easy policy — allowing all inline script —
    would leave the header present and its main protection absent. A CSP that
    permits the thing it exists to prevent is worse than none, because it reads
    as protection in an audit.

    `style-src` does allow inline: four templates set `style=` attributes for
    computed positions in the estate map, a nonce cannot cover an attribute,
    and style injection is a much smaller prize than script injection.
    """
    return "; ".join(
        (
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            # No third party may be contacted, so an injected script cannot
            # send an estate's data anywhere even if one runs.
            "connect-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "object-src 'none'",
        )
    )


async def security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Mint a nonce, let the page render with it, then state the policy."""
    nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = nonce
    response = await call_next(request)
    for name, value in STATIC_HEADERS.items():
        response.headers.setdefault(name, value)
    response.headers.setdefault("Content-Security-Policy", content_security_policy(nonce))
    return response


def install(app: ASGIApp) -> None:
    """Attach the middleware to an application."""
    app.middleware("http")(security_headers)  # type: ignore[attr-defined]
