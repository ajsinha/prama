"""The layer every template sits on.

Jinja needs three things from the application that FastAPI does not give it:
a way to name a route rather than hard-code its path, a place for one-shot
messages that survive a redirect, and the navigation state. This module is all
three, and it is deliberately the same shape as DishtaYantra's
``web/fastapi_compat`` so a template moves between the two unchanged.

One difference, on purpose: the templates directory is resolved from the
package, not from the working directory. A UI that renders when started from
the repository root and 500s when started from anywhere else is a defect that
only shows up in the deployment nobody tested.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from prama.core.log import get_logger
from prama.version import PRODUCT_TAGLINE, VERSION

_log = get_logger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"

#: The message categories a template knows how to style. A category outside
#: this set renders as ``info`` rather than as an unstyled bare string, so a
#: typo degrades to a visible message instead of an invisible one.
CATEGORIES = ("success", "info", "warning", "error")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@dataclasses.dataclass(frozen=True, slots=True)
class NavItem:
    """One entry in the primary navigation.

    ``prefix`` rather than an exact path, because /controls/abc must still light
    the Controls tab: a user who has drilled three levels down and can no longer
    see where they are is the commonest way a console feels like a maze.
    """

    label: str
    endpoint: str
    prefix: str
    icon: str = ""

    def active_for(self, path: str) -> bool:
        return path == self.prefix or path.startswith(self.prefix.rstrip("/") + "/")


#: Order is the reading order of the work: see the estate, say what it means,
#: state the controls, look at what broke, agree the numbers, report.
NAVIGATION: tuple[NavItem, ...] = (
    NavItem("Estate", "estate_map", "/estate", "bi-diagram-3"),
    NavItem("Declarations", "declaration_list", "/declarations", "bi-journal-text"),
    NavItem("Controls", "control_studio", "/controls", "bi-shield-check"),
    NavItem("Proposals", "proposal_queue", "/proposals", "bi-lightbulb"),
    NavItem("Incidents", "incident_list", "/incidents", "bi-exclamation-triangle"),
    NavItem("Reconciliation", "reconciliation_list", "/reconciliation", "bi-arrow-left-right"),
    NavItem("Scorecards", "scorecard_list", "/scorecards", "bi-clipboard-data"),
)


def url_for(request: Request, name: str, **params: Any) -> str:
    """Resolve a route name to a URL, with Flask's semantics.

    ``url_for('static', filename='css/prama.css')`` hits the mounted static
    app; anything matching a path parameter is substituted; whatever is left
    becomes the query string.
    """
    app = request.app
    if name == "static":
        filename = params.pop("filename", "")
        url = app.url_path_for("static", path=filename)
        return f"{url}?{urlencode(params)}" if params else url

    path_params: set[str] = set()
    for route in app.routes:
        if getattr(route, "name", None) == name:
            path_params = set(getattr(route, "param_convertors", {}))
            break
    in_path = {k: v for k, v in params.items() if k in path_params}
    in_query = {k: v for k, v in params.items() if k not in path_params}
    url = app.url_path_for(name, **in_path)
    return f"{url}?{urlencode(in_query)}" if in_query else url


def flash(request: Request, message: str, category: str = "success") -> None:
    """Queue a message for the next rendered page."""
    if category not in CATEGORIES:
        _log.warning("unknown flash category %r, showing as info", category)
        category = "info"
    request.session.setdefault("_flashes", []).append([category, message])


def get_flashed_messages(request: Request, *, with_categories: bool = False) -> list[Any]:
    """Drain the queue. Reading consumes, as Flask does."""
    flashes = request.session.pop("_flashes", [])
    if with_categories:
        return [(category, message) for category, message in flashes]
    return [message for _, message in flashes]


def render(request: Request, template: str, status_code: int = 200, **context: Any) -> Any:
    """Render a template with the shell's context already supplied."""
    path = request.url.path
    context.setdefault(
        "nav",
        [
            {
                "label": item.label,
                "href": url_for(request, item.endpoint),
                "icon": item.icon,
                "active": item.active_for(path),
            }
            for item in NAVIGATION
        ],
    )
    context.setdefault("app_version", VERSION)
    context.setdefault("app_tagline", PRODUCT_TAGLINE)
    return templates.TemplateResponse(
        request=request, name=template, context=context, status_code=status_code
    )


def redirect_to(
    request: Request,
    endpoint: str,
    *,
    flash_message: str | None = None,
    flash_category: str = "success",
    **params: Any,
) -> RedirectResponse:
    """Redirect to a named route. 303, so a POST handler lands on a GET."""
    if flash_message:
        flash(request, flash_message, flash_category)
    return RedirectResponse(url=url_for(request, endpoint, **params), status_code=303)


def flash_error_and_log(request: Request, user_message: str, exc: Exception) -> None:
    """Show the failure and record it in full.

    Both, always. A flash without a log leaves nothing to diagnose from; a log
    without a flash leaves the user staring at a page that silently did nothing.
    """
    _log.exception("%s", user_message, exc_info=exc)
    flash(request, f"{user_message}: {exc}", "error")


def install_globals() -> None:
    """Make the helpers callable from inside a template.

    ``url_for`` and ``get_flashed_messages`` are declared as context functions
    so Jinja passes the request through automatically and a template writes
    ``url_for('estate_map')`` — the form every template in DishtaYantra already
    uses.
    """
    import jinja2

    @jinja2.pass_context
    def _url_for(context: Any, name: str, **params: Any) -> str:
        return url_for(context["request"], name, **params)

    @jinja2.pass_context
    def _flashed(context: Any, with_categories: bool = False) -> list[Any]:
        return get_flashed_messages(context["request"], with_categories=with_categories)

    templates.env.globals["url_for"] = _url_for
    templates.env.globals["get_flashed_messages"] = _flashed
    templates.env.globals["app_version"] = VERSION
    templates.env.globals["app_tagline"] = PRODUCT_TAGLINE
